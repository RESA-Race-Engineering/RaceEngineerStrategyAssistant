"""
Sessione di gara: il ponte fra live timing, motore di gara e GUI.

Qui vive l'adapter previsto dal piano: gli eventi di TeamTracker
diventano chiamate a core.race_logic. La GUI parla soltanto con
RaceSession, mai con il feed o con il database.

Regole:
- kart e pilota li conferma l'operatore; il feed li controlla e
  basta. Un KartNumberMismatch produce un avviso, mai una correzione;
- al PitIn lo stint non si chiude: si aspetta la conferma
  dell'operatore (nuovo kart, nuovo pilota). Nel frattempo i giri in
  arrivo restano in sospeso e vengono attribuiti dopo la conferma,
  altrimenti finirebbero sullo stint vecchio senza alcun errore;
- tutto funziona anche senza feed: avvio, giri, pit ed eventi si
  inseriscono a mano.

Semantica ancora da verificare su un registro reale: si assume che
LapCompleted.lap_number sia il giro appena chiuso e che
PitIn.lap_number sia l'ultimo giro completato prima del pit.

Il feed e la GUI girano su thread diversi: ogni metodo pubblico
prende self.lock, che la GUI usa anche per leggere lo stato.
"""

from dataclasses import dataclass
from datetime import datetime
import threading
import time
from pathlib import Path
from typing import Optional

from core.models import (
    Driver,
    Kart,
    Race,
    RaceConfig,
    RaceEvent,
    Stint,
    Team,
)
from core.race_logic import (
    register_lap,
    register_pit_stop,
    start_stint,
)
from core.rules import RuleStatus, check_pit_duration
from core.time_utils import format_time
from database.csv_export import export_race_csv
from database.db import RaceDatabase
from livetiming.reader import (
    KartNumberChanged,
    KartNumberMismatch,
    LapCompleted,
    PitIn,
    PitOut,
    SessionChanged,
    TeamBound,
    TeamLost,
    TeamTracker,
)
from livetiming.standings import Standings


# Avvisi conservati per la GUI.
MAX_ALERTS = 200

# Scarto massimo fra il tempo sul giro dichiarato dal feed e il tempo
# trascorso fra due passaggi consecutivi. Oltre, il feed aggiorna
# "Ultimo T." in un momento diverso da quello che supponiamo e ogni
# giro rischia di ricevere il tempo del giro prima.
LAP_TIME_CHECK_MS = 3000


@dataclass
class Alert:
    """Messaggio per l'operatore."""

    time_ms: int
    race_time_ms: Optional[int]

    # "info", "warning" oppure "error".
    level: str
    message: str


@dataclass
class PendingLap:
    """Giro arrivato dal feed e non ancora attribuito a uno stint."""

    lap_number: int
    lap_time_ms: int
    race_time_ms: Optional[int]


@dataclass
class PendingPit:
    """Pit segnalato dal feed, in attesa della conferma."""

    lap_before: int
    in_race_time_ms: Optional[int]
    out_race_time_ms: Optional[int] = None

    @property
    def measured_ms(self) -> Optional[int]:
        """Durata misurata fra ingresso e uscita dai box."""

        if (
            self.in_race_time_ms is None
            or self.out_race_time_ms is None
        ):
            return None

        return self.out_race_time_ms - self.in_race_time_ms


class RaceSession:
    """Stato completo della gara in corso."""

    def __init__(
        self,
        race: Race,
        team_name: str,
        db: Optional[RaceDatabase] = None,
        race_id: Optional[int] = None,
        auto_pit: bool = False,
    ):
        self.race = race
        self.team_name = team_name
        self.db = db
        self.race_id = race_id

        # Solo per simulazioni e riletture: conferma i pit da sola
        # con il kart del feed e il pilota successivo.
        self.auto_pit = auto_pit

        self.tracker = TeamTracker(
            team_name=team_name,
            race_duration_ms=race.config.duration_ms,
        )

        self.standings = Standings(
            race_duration_ms=race.config.duration_ms,
        )

        self.pending_pit: Optional[PendingPit] = None
        self.pending_laps: list[PendingLap] = []
        self.alerts: list[Alert] = []

        self.source_mode = "manuale"
        self.source_status = "nessun feed"
        self.speed = 1.0

        self.lock = threading.RLock()

        self._feed_time_ms: Optional[int] = None
        self._feed_wall_ms: Optional[float] = None
        self._clock_frozen = False

        # Riferimento per il tempo di gara quando manca il feed.
        self._manual_start_ms: Optional[int] = None

        # Pit confermato prima che il kart uscisse dai box.
        self._awaiting_pit_out = False

        # Ingresso ai box del pit confermato in attesa dell'uscita,
        # per misurarne la durata quando il kart esce.
        self._awaiting_pit_in_ms: Optional[int] = None

        # Ultimo giro dal feed: (numero, istante di ricezione).
        self._last_feed_lap: Optional[tuple[int, int]] = None

    # ==============================
    # CREAZIONE
    # ==============================

    @classmethod
    def create(
        cls,
        team_name: str,
        driver_names: list[str],
        db_path: Optional[str] = None,
        race_name: str = "",
        config: Optional[RaceConfig] = None,
        auto_pit: bool = False,
    ) -> "RaceSession":
        """Prepara una gara nuova, salvandola nel database se indicato."""

        config = config or RaceConfig()

        if not driver_names:
            raise ValueError("Indicare almeno un pilota.")

        race = Race(config=config)

        db = None
        race_id = None
        team_id = 1

        if db_path:
            db = RaceDatabase(
                db_path,
                check_same_thread=False,
            )

            race_id = db.create_race(
                name=race_name or f"{team_name} {datetime.now():%Y-%m-%d}",
                duration_ms=config.duration_ms,
                created_at=datetime.now().isoformat(timespec="seconds"),
            )

            team_id = db.create_team(
                race_id=race_id,
                name=team_name,
            )

        race.teams.append(
            Team(
                id=team_id,
                name=team_name,
            )
        )

        for index, name in enumerate(driver_names, start=1):
            driver_id = index

            if db is not None:
                driver_id = db.create_driver(
                    race_id=race_id,
                    team_id=team_id,
                    name=name,
                )

            race.drivers.append(
                Driver(
                    id=driver_id,
                    name=name,
                    team_id=team_id,
                )
            )

        return cls(
            race=race,
            team_name=team_name,
            db=db,
            race_id=race_id,
            auto_pit=auto_pit,
        )

    @classmethod
    def resume(
        cls,
        db_path: str,
        race_id: Optional[int] = None,
        auto_pit: bool = False,
    ) -> "RaceSession":
        """
        Riprende una gara dal database dopo una chiusura.

        Giri, stint e pit tornano come erano; il feed riaggancia la
        squadra alla prima griglia. La storia dei concorrenti non è
        nel database e riparte da zero.
        """

        if not Path(db_path).exists():
            raise ValueError(f"Database non trovato: {db_path}")

        db = RaceDatabase(
            db_path,
            check_same_thread=False,
        )

        race_id = race_id or db.get_last_race_id()

        if race_id is None:
            raise ValueError("Il database non contiene gare da riprendere.")

        race = db.load_race(race_id)

        session = cls(
            race=race,
            team_name=race.teams[0].name if race.teams else "",
            db=db,
            race_id=race_id,
            auto_pit=auto_pit,
        )

        kart = session.current_kart()

        if kart is not None:
            session.tracker.set_operator_kart_number(str(kart.number))

        session._alert(
            "info",
            f"Gara {race_id} ripresa: {len(race.laps)} giri, "
            f"{len(race.stints)} stint.",
        )

        return session

    # ==============================
    # TEMPO
    # ==============================

    def now_ms(self) -> int:
        """
        Istante attuale in millisecondi.

        In rilettura è il tempo del registro, che avanza alla velocità
        di rilettura; in diretta coincide con l'orologio locale.
        """

        wall_ms = time.time() * 1000

        if self._feed_time_ms is None:
            return int(wall_ms)

        if self._clock_frozen:
            return self._feed_time_ms

        return int(
            self._feed_time_ms
            + (wall_ms - self._feed_wall_ms) * self.speed
        )

    def race_time_ms(self) -> Optional[int]:
        """Tempo di gara attuale: dal cronometro del feed, o locale."""

        now_ms = self.now_ms()

        race_time_ms = self.tracker.clock.race_time_ms(now_ms)

        if race_time_ms is not None:
            return race_time_ms

        if self._manual_start_ms is not None:
            return now_ms - self._manual_start_ms

        return None

    # ==============================
    # SORGENTE DEI DATI
    # ==============================

    def set_source(
        self,
        mode: str,
        status: str,
        speed: float = 1.0,
    ) -> None:
        """Dichiara da dove arrivano i dati (diretta o rilettura)."""

        with self.lock:
            self.source_mode = mode
            self.source_status = status
            self.speed = speed
            self._clock_frozen = False

    def source_event(
        self,
        status: str,
        level: str = "",
        finished: bool = False,
    ) -> None:
        """Aggiorna lo stato del collegamento."""

        with self.lock:
            self.source_status = status

            if finished:
                self._clock_frozen = True

            if level:
                self._alert(level, status)

    def process_payload(
        self,
        payload: str,
        received_at_ms: Optional[int] = None,
    ) -> None:
        """Applica un payload del feed."""

        with self.lock:
            now_ms = received_at_ms or int(time.time() * 1000)

            self._feed_time_ms = now_ms
            self._feed_wall_ms = time.time() * 1000

            self.standings.process(
                payload,
                now_ms=now_ms,
            )

            events = self.tracker.process(
                payload,
                now_ms=now_ms,
            )

            for event in events:
                self._handle_event(event)

    # ==============================
    # EVENTI DEL FEED
    # ==============================

    def _handle_event(self, event) -> None:
        """Traduce un evento del lettore in un'azione sulla gara."""

        if isinstance(event, TeamBound):
            self._alert(
                "info",
                f"Squadra agganciata: riga {event.row_id}, "
                f"kart {event.kart_number}.",
            )

            if (
                self.auto_pit
                and not self.race.stints
                and self.race.drivers
                and event.kart_number
            ):
                self._start(
                    driver_id=self.race.drivers[0].id,
                    kart_number=event.kart_number,
                    start_lap=self.tracker.state.lap_number or 0,
                )

        elif isinstance(event, TeamLost):
            self._alert(
                "warning",
                "La squadra non è più nella griglia del feed.",
            )

        elif isinstance(event, SessionChanged):
            self._alert(
                "info",
                f"Il feed ha ricaricato la sessione ({event.mode}).",
            )

        elif isinstance(event, LapCompleted):
            self._on_lap(event)

        elif isinstance(event, PitIn):
            self._on_pit_in(event)

        elif isinstance(event, PitOut):
            self._on_pit_out(event)

        elif isinstance(event, KartNumberChanged):
            self._alert(
                "info",
                f"Il feed segnala il kart {event.current} "
                f"(prima {event.previous}).",
            )

        elif isinstance(event, KartNumberMismatch):
            self._on_mismatch(event)

    def _on_mismatch(self, event: KartNumberMismatch) -> None:
        """Il kart dichiarato non coincide con quello del feed."""

        # Durante un pit non ancora confermato la differenza è attesa.
        if self.pending_pit is not None:
            self._alert(
                "info",
                f"Il feed indica il kart {event.feed_value}: "
                f"confermare il pit.",
            )
            return

        self._alert(
            "warning",
            f"Kart diverso: l'operatore ha indicato "
            f"{event.operator_value}, il feed dice {event.feed_value}.",
        )

    def _on_lap(self, event: LapCompleted) -> None:
        """Un giro chiuso sul traguardo."""

        if not event.lap_time_ms:
            self._alert(
                "warning",
                f"Giro {event.lap_number} senza tempo: non registrato.",
            )
            return

        lap = PendingLap(
            lap_number=event.lap_number or self._last_lap_number() + 1,
            lap_time_ms=event.lap_time_ms,
            race_time_ms=event.race_time_ms,
        )

        self._check_lap_time(
            lap,
            received_at_ms=event.received_at_ms,
        )

        if self.current_stint() is None:
            if not self.pending_laps:
                self._alert(
                    "warning",
                    "Giri in arrivo ma gara non avviata: scegliere "
                    "pilota e kart di partenza.",
                )

            self.pending_laps.append(lap)
            return

        if self.pending_pit is not None:
            self.pending_laps.append(lap)
            return

        self._register(lap)

    def _check_lap_time(
        self,
        lap: PendingLap,
        received_at_ms: int,
    ) -> None:
        """
        Confronta il tempo sul giro con il tempo fra due passaggi.

        È la verifica dal vivo della semantica ancora da confermare:
        se il feed aggiornasse "Ultimo T." dopo il passaggio, ogni
        giro riceverebbe il tempo del giro prima. Uno scarto isolato
        può venire da un ritardo di rete; uno ripetuto no.
        """

        previous = self._last_feed_lap
        self._last_feed_lap = (lap.lap_number, received_at_ms)

        if previous is None or lap.lap_number != previous[0] + 1:
            return

        elapsed_ms = received_at_ms - previous[1]

        if abs(elapsed_ms - lap.lap_time_ms) <= LAP_TIME_CHECK_MS:
            return

        self._alert(
            "warning",
            f"Giro {lap.lap_number}: il feed dice "
            f"{format_time(lap.lap_time_ms)}, ma fra i due passaggi "
            f"sono passati {format_time(elapsed_ms)}. Se si ripete, "
            f"i tempi dei giri sono sfasati: segnalarlo.",
        )

    def _on_pit_in(self, event: PitIn) -> None:
        """Ingresso ai box: si aspetta la conferma dell'operatore."""

        if self.current_stint() is None or self.pending_pit is not None:
            return

        lap_before = event.lap_number

        if lap_before is None:
            lap_before = self._last_registered_lap_number()

        self.pending_pit = PendingPit(
            lap_before=lap_before,
            in_race_time_ms=event.race_time_ms,
        )

        self._awaiting_pit_out = False

        self._alert(
            "warning",
            f"PIT IN dopo il giro {lap_before}: confermare nuovo kart "
            f"e nuovo pilota.",
        )

    def _on_pit_out(self, event: PitOut) -> None:
        """Uscita dai box."""

        if self.current_stint() is None:
            return

        # Pit già confermato mentre il kart era ai box: lo stint
        # nuovo parte adesso.
        if self.pending_pit is None and self._awaiting_pit_out:
            self._awaiting_pit_out = False
            self._set_stint_start(event.race_time_ms)
            self._complete_pit_duration(event.race_time_ms)
            return

        # Uscita senza ingresso: aggancio avvenuto durante il pit.
        if self.pending_pit is None:
            self.pending_pit = PendingPit(
                lap_before=self._last_registered_lap_number(),
                in_race_time_ms=None,
            )

        self.pending_pit.out_race_time_ms = event.race_time_ms

        measured_ms = self.pending_pit.measured_ms

        if self.auto_pit:
            self.confirm_pit(
                kart_number=event.kart_number,
                driver_id=self.next_driver_id(),
                duration_ms=measured_ms,
            )
            return

        if measured_ms is not None:
            self._alert(
                "info",
                f"PIT OUT: sosta di {format_time(measured_ms)}.",
            )

    # ==============================
    # AZIONI DELL'OPERATORE
    # ==============================

    def start_race(
        self,
        driver_id: int,
        kart_number,
        start_lap: Optional[int] = None,
    ) -> None:
        """Apre il primo stint con il pilota e il kart di partenza."""

        with self.lock:
            if self.race.stints:
                raise ValueError("La gara è già avviata.")

            self._start(
                driver_id=driver_id,
                kart_number=kart_number,
                start_lap=start_lap,
            )

    def _start(
        self,
        driver_id: int,
        kart_number,
        start_lap: Optional[int] = None,
    ) -> None:
        kart_number = _parse_kart_number(kart_number)

        if start_lap is None:
            if self.pending_laps:
                start_lap = min(
                    lap.lap_number
                    for lap in self.pending_laps
                ) - 1
            else:
                start_lap = self.tracker.state.lap_number or 0

        race_time_ms = self.race_time_ms()

        if race_time_ms is None:
            self._manual_start_ms = self.now_ms()
            race_time_ms = 0

        start_stint(
            race=self.race,
            kart_id=self._ensure_kart(kart_number),
            driver_id=driver_id,
            start_lap=start_lap,
            # A zero l'inizio si ricava dal primo giro.
            start_time_ms=race_time_ms if start_lap > 0 else 0,
            db=self.db,
            race_id=self.race_id,
        )

        self._declare_kart(kart_number)

        self._alert(
            "info",
            f"Gara avviata: {self._driver_name(driver_id)} "
            f"sul kart {kart_number}.",
        )

        pending = sorted(
            self.pending_laps,
            key=lambda lap: lap.lap_number,
        )

        self.pending_laps = []

        for lap in pending:
            if lap.lap_number > start_lap:
                self._register(lap)

    def confirm_pit(
        self,
        kart_number,
        driver_id: int,
        duration_ms: Optional[int] = None,
        refuel: bool = False,
        tire_change: bool = False,
    ) -> None:
        """
        Registra il pit: chiude lo stint e apre il successivo.

        Senza un PitIn dal feed vale come pit inserito a mano, dopo
        l'ultimo giro registrato.
        """

        with self.lock:
            stint = self.current_stint()

            if stint is None:
                raise ValueError("Nessuno stint aperto: avviare prima la gara.")

            kart_number = _parse_kart_number(kart_number)
            pending = self.pending_pit

            last_registered = self._last_registered_lap_number()

            lap_before = max(
                pending.lap_before if pending else last_registered,
                last_registered,
            )

            if duration_ms is None and pending is not None:
                duration_ms = pending.measured_ms

            laps = sorted(
                self.pending_laps,
                key=lambda lap: lap.lap_number,
            )

            # I giri in sospeso fino al pit vanno ancora allo stint
            # vecchio; gli altri a quello nuovo.
            for lap in laps:
                if lap.lap_number <= lap_before:
                    self._register(lap)

            register_pit_stop(
                race=self.race,
                kart_id=stint.kart_id,
                new_kart_id=self._ensure_kart(kart_number),
                lap_before=lap_before,
                driver_in=driver_id,
                duration_ms=duration_ms,
                refuel=refuel,
                tire_change=tire_change,
                db=self.db,
                race_id=self.race_id,
            )

            self.pending_pit = None
            self.pending_laps = []

            self._awaiting_pit_out = (
                pending is not None
                and pending.out_race_time_ms is None
            )

            self._awaiting_pit_in_ms = (
                pending.in_race_time_ms
                if self._awaiting_pit_out and duration_ms is None
                else None
            )

            # A Kart&Go l'uscita dai box conta come giro senza passare
            # dal traguardo: il primo giro registrato dello stint non è
            # start_lap + 1 e il core non ricaverebbe mai l'inizio.
            # Si usa l'istante di uscita, già misurato.
            if pending is not None:
                self._set_stint_start(pending.out_race_time_ms)

            for lap in laps:
                if lap.lap_number > lap_before:
                    self._register(lap)

            self._declare_kart(kart_number)

            self._alert(
                "info",
                f"Pit confermato dopo il giro {lap_before}: "
                f"{self._driver_name(driver_id)} sul kart {kart_number}.",
            )

            if duration_ms is not None:
                result = check_pit_duration(duration_ms, self.race)

                if result.status == RuleStatus.VIOLATION:
                    self._alert("error", result.message)

    def _set_stint_start(self, race_time_ms: Optional[int]) -> None:
        """Fissa l'inizio dello stint aperto, se non è ancora noto."""

        stint = self.current_stint()

        if (
            stint is None
            or race_time_ms is None
            or stint.start_time_ms
        ):
            return

        stint.start_time_ms = race_time_ms

        if self.db is not None and self.race_id is not None:
            self.db.update_stint_start(
                race_id=self.race_id,
                kart_id=stint.kart_id,
                stint_number=stint.stint_number,
                start_time_ms=race_time_ms,
            )

    def _complete_pit_duration(self, out_race_time_ms: Optional[int]) -> None:
        """
        Registra la durata del pit confermato mentre il kart era ai
        box, ora che l'uscita è nota, e ne verifica il minimo.
        """

        in_race_time_ms = self._awaiting_pit_in_ms
        self._awaiting_pit_in_ms = None

        if (
            in_race_time_ms is None
            or out_race_time_ms is None
            or not self.race.pit_stops
        ):
            return

        pit_stop = self.race.pit_stops[-1]

        if pit_stop.duration_ms is not None:
            return

        pit_stop.duration_ms = out_race_time_ms - in_race_time_ms

        if self.db is not None and self.race_id is not None:
            self.db.update_pit_stop_duration(
                race_id=self.race_id,
                lap_before=pit_stop.lap_before,
                duration_ms=pit_stop.duration_ms,
            )

        self._alert(
            "info",
            f"PIT OUT: sosta di {format_time(pit_stop.duration_ms)}.",
        )

        result = check_pit_duration(pit_stop.duration_ms, self.race)

        if result.status == RuleStatus.VIOLATION:
            self._alert("error", result.message)

    def discard_pit(self) -> None:
        """
        Annulla un pit segnalato dal feed (falso allarme).

        I giri rimasti in sospeso vanno allo stint in corso.
        """

        with self.lock:
            if self.pending_pit is None:
                return

            self.pending_pit = None

            laps = sorted(
                self.pending_laps,
                key=lambda lap: lap.lap_number,
            )

            self.pending_laps = []

            for lap in laps:
                self._register(lap)

            self._alert("info", "Pit segnalato dal feed annullato.")

    def add_manual_lap(
        self,
        lap_time_ms: int,
        lap_number: Optional[int] = None,
    ) -> None:
        """Inserisce un giro a mano, quando il feed manca."""

        with self.lock:
            stint = self.current_stint()

            if stint is None:
                raise ValueError("Nessuno stint aperto: avviare prima la gara.")

            if self.pending_pit is not None:
                raise ValueError("Pit in attesa: confermarlo o annullarlo prima.")

            register_lap(
                race=self.race,
                kart_id=stint.kart_id,
                lap_number=lap_number or self._last_lap_number() + 1,
                lap_time_ms=lap_time_ms,
                race_time_ms=self.race_time_ms(),
                db=self.db,
                race_id=self.race_id,
            )

    def add_event(
        self,
        description: str,
        penalty_ms: int = 0,
    ) -> None:
        """Registra un evento o una penalità al tempo di gara attuale."""

        with self.lock:
            description = description.strip()

            if not description:
                raise ValueError("Descrizione dell'evento mancante.")

            if penalty_ms < 0:
                raise ValueError("La penalità non può essere negativa.")

            event = RaceEvent(
                time_ms=self.race_time_ms() or 0,
                description=description,
                penalty_ms=penalty_ms,
            )

            self.race.events.append(event)

            if self.db is not None and self.race_id is not None:
                self.db.create_event(
                    race_id=self.race_id,
                    time_ms=event.time_ms,
                    description=event.description,
                    penalty_ms=event.penalty_ms,
                )

            self._alert(
                "warning" if penalty_ms else "info",
                f"Evento: {description}"
                + (f" (+{penalty_ms / 1000:g} s)" if penalty_ms else ""),
            )

    def export_csv(self, folder: Optional[str] = None) -> Path:
        """Esporta la gara in CSV."""

        with self.lock:
            if folder is None:
                name = (
                    f"gara_{self.race_id}"
                    if self.race_id is not None
                    else f"gara_{datetime.now():%Y%m%d_%H%M%S}"
                )

                folder = f"data/export/{name}"

            path = export_race_csv(self.race, folder)

            self._alert("info", f"Gara esportata in {path}.")

            return path

    # ==============================
    # LETTURA DELLO STATO
    # ==============================

    def current_stint(self) -> Optional[Stint]:
        """Stint aperto, se c'è."""

        for stint in reversed(self.race.stints):
            if stint.end_lap is None:
                return stint

        return None

    def current_kart(self) -> Optional[Kart]:
        stint = self.current_stint()

        if stint is None:
            return None

        return self._kart_by_id(stint.kart_id)

    def current_driver(self) -> Optional[Driver]:
        stint = self.current_stint()

        if stint is None:
            return None

        for driver in self.race.drivers:
            if driver.id == stint.driver_id:
                return driver

        return None

    def kart_number(self, kart_id: Optional[int]) -> Optional[int]:
        kart = self._kart_by_id(kart_id)

        return kart.number if kart is not None else None

    # ==============================
    # SUPPORTO
    # ==============================

    def _register(self, lap: PendingLap) -> None:
        """Registra un giro sullo stint aperto; un errore diventa avviso."""

        stint = self.current_stint()

        if stint is None:
            self.pending_laps.append(lap)
            return

        try:
            register_lap(
                race=self.race,
                kart_id=stint.kart_id,
                lap_number=lap.lap_number,
                lap_time_ms=lap.lap_time_ms,
                race_time_ms=lap.race_time_ms,
                db=self.db,
                race_id=self.race_id,
            )

        except ValueError as error:
            self._alert(
                "error",
                f"Giro {lap.lap_number} non registrato: {error}",
            )

    def _last_registered_lap_number(self) -> int:
        """Ultimo giro registrato; senza giri, l'inizio dello stint."""

        if self.race.laps:
            return max(
                lap.lap_number
                for lap in self.race.laps
            )

        stint = self.current_stint()

        return (stint.start_lap or 0) if stint is not None else 0

    def _last_lap_number(self) -> int:
        """Ultimo giro noto, registrato o in sospeso."""

        return max(
            [lap.lap_number for lap in self.race.laps]
            + [lap.lap_number for lap in self.pending_laps]
            + [self._last_registered_lap_number()]
        )

    def _ensure_kart(self, kart_number: int) -> int:
        """Restituisce l'ID del kart, creandolo alla prima comparsa."""

        for kart in self.race.karts:
            if kart.number == kart_number:
                return kart.id

        if self.db is not None and self.race_id is not None:
            kart_id = self.db.create_kart(
                race_id=self.race_id,
                number=kart_number,
            )
        else:
            kart_id = max(
                (kart.id for kart in self.race.karts),
                default=0,
            ) + 1

        self.race.karts.append(
            Kart(
                id=kart_id,
                number=kart_number,
            )
        )

        return kart_id

    def _kart_by_id(self, kart_id: Optional[int]) -> Optional[Kart]:
        for kart in self.race.karts:
            if kart.id == kart_id:
                return kart

        return None

    def _driver_name(self, driver_id: Optional[int]) -> str:
        for driver in self.race.drivers:
            if driver.id == driver_id:
                return driver.name

        return f"pilota {driver_id}"

    def _declare_kart(self, kart_number: int) -> None:
        """Comunica al lettore il kart dichiarato dall'operatore."""

        for event in self.tracker.set_operator_kart_number(str(kart_number)):
            self._handle_event(event)

    def next_driver_id(self) -> int:
        """
        Pilota suggerito per il prossimo stint.

        Prima chi non ha ancora guidato, poi a rotazione.
        """

        driven = {
            stint.driver_id
            for stint in self.race.stints
        }

        for driver in self.race.drivers:
            if driver.id not in driven:
                return driver.id

        current = self.current_driver()
        ids = [driver.id for driver in self.race.drivers]

        if current is None or current.id not in ids:
            return ids[0]

        return ids[(ids.index(current.id) + 1) % len(ids)]

    def _alert(self, level: str, message: str) -> None:
        self.alerts.append(
            Alert(
                time_ms=self.now_ms(),
                race_time_ms=self.race_time_ms(),
                level=level,
                message=message,
            )
        )

        del self.alerts[:-MAX_ALERTS]


def _parse_kart_number(value) -> int:
    """Il numero di kart arriva dalla GUI o dal feed come testo."""

    try:
        number = int(str(value).strip())
    except ValueError:
        raise ValueError(f"Numero di kart non valido: '{value}'.") from None

    if number <= 0:
        raise ValueError(f"Numero di kart non valido: '{value}'.")

    return number
