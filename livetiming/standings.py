"""
Classifica completa dal feed Apex.

reader.py segue soltanto la nostra squadra. Qui si tiene lo stato di
tutte le righe della griglia e, per ciascuna, la storia dei giri e
degli stint, così da applicare ai concorrenti le stesse finestre di
analisi usate per noi (core.analytics).

Questi dati non passano mai dal motore di gara né dal database: i
giri della nostra squadra arrivano da race.laps, quelli dei
concorrenti da qui, e le due fonti non vanno mescolate.

Come per il lettore della squadra, la semantica di giri e pit va
ancora verificata su un registro reale: si assume che le celle
"llp" e "tlp" arrivino aggiornate nello stesso payload del passaggio
sul traguardo.
"""

from dataclasses import dataclass, field
import re
import time
from typing import Optional

from core.models import Lap
from livetiming.clock import RaceClock
from livetiming.protocol import (
    CellUpdate,
    Crossing,
    FieldUpdate,
    GridReplaced,
    GridRow,
    PositionChange,
    Sector,
    parse_int,
    parse_payload,
    parse_time_to_ms,
)
from livetiming.reader import TEAM_NAME_COLUMNS


def parse_gap_ms(text: str) -> Optional[int]:
    """
    Converte un distacco del feed in millisecondi.

    "+12.345" e "12.345" sono tempi. "1 Giro", "2 Laps" e simili
    indicano un kart doppiato e restituiscono None.
    """

    return parse_time_to_ms((text or "").strip().lstrip("+"))


# ==============================
# STATO DEI CONCORRENTI
# ==============================


@dataclass
class CompetitorStint:
    """
    Stint di un concorrente, ricostruito dalle uscite dai box.

    Stessa convenzione di Stint: start_lap è l'ultimo giro completato
    prima dello stint, end_lap l'ultimo giro dello stint, None finché
    è aperto. La numerazione parte dall'aggancio al feed, non
    dall'inizio della gara.
    """

    stint_number: int
    start_lap: int
    end_lap: Optional[int] = None


@dataclass
class CompetitorLap(Lap):
    """
    Giro di un concorrente con il numero del kart usato.

    Il numero è quello del feed, non un Kart.id: serve a confrontare
    i kart fra tutte le squadre.
    """

    kart_number: str = ""


@dataclass
class Competitor:
    """Una riga della classifica con la sua storia."""

    row_id: str
    position: Optional[int] = None
    kart_number: str = ""
    team_label: str = ""

    lap_number: Optional[int] = None
    last_lap_ms: Optional[int] = None
    best_lap_ms: Optional[int] = None
    pit_count: Optional[int] = None
    in_pit: bool = False

    # Distacco così come lo pubblica il feed ("+12.345", "1 Giro"...)
    # e il suo valore quando è un tempo.
    gap: str = ""
    gap_ms: Optional[int] = None

    # Distacco dal kart che precede: dalla colonna "int" quando il
    # circuito la pubblica, altrimenti ricavato dai passaggi sul
    # traguardo. Su circuito-di-pomposa "gap" (Distacco) è il
    # distacco dal primo e "int" (Interv.) quello da chi precede.
    interval_ms: Optional[int] = None

    # Intervallo così come lo pubblica il feed, se c'è la colonna.
    feed_interval_ms: Optional[int] = None

    # Giri senza pilota, squadra e Kart.id: bastano a core.analytics.
    laps: list[CompetitorLap] = field(default_factory=list)
    stints: list[CompetitorStint] = field(default_factory=list)


class Standings:
    """
    Tiene la classifica e la storia dei giri di ogni riga.

    La storia sopravvive alle riconnessioni: il server rinvia
    sessione e griglia, ma righe e numeri di giro proseguono. Per una
    riga si azzera quando il suo numero di giro torna indietro, segno
    di una sessione nuova.
    """

    def __init__(self, race_duration_ms: Optional[int] = None):
        # Cronometro proprio: condividere quello di TeamTracker lo
        # farebbe aggiornare due volte con la stessa lettura, e una
        # lettura ripetuta lo dichiara fermo.
        self.clock = RaceClock(total_duration_ms=race_duration_ms)

        self._columns: dict[str, str] = {}
        self._rows: dict[str, GridRow] = {}
        self._competitors: dict[str, Competitor] = {}

    # ----- lettura -----

    def competitors(self) -> list[Competitor]:
        """
        Classifica corrente, dal primo all'ultimo.

        Comprende anche la nostra squadra: la GUI la riconosce dalla
        riga seguita da TeamTracker (state.row_id).
        """

        present = [
            self._competitors[row_id]
            for row_id in self._rows
            if row_id in self._competitors
        ]

        return sorted(
            present,
            key=lambda competitor: (
                competitor.position is None,
                competitor.position or 0,
            ),
        )

    def get(self, row_id: str) -> Optional[Competitor]:
        """Restituisce il concorrente della riga indicata."""

        return self._competitors.get(row_id)

    def reset(self) -> None:
        """Dimentica la storia di tutti: da usare a sessione nuova."""

        self._competitors = {}

    # ----- ingresso del feed -----

    def process(
        self,
        payload: str,
        now_ms: Optional[int] = None,
    ) -> None:
        """
        Applica un payload del feed.

        Come in TeamTracker, prima si aggiornano le celle e poi si
        interpretano gli attraversamenti, così un giro viene
        registrato con il tempo già aggiornato. now_ms ha lo stesso
        significato che in TeamTracker.process().
        """

        if now_ms is None:
            now_ms = int(time.time() * 1000)

        crossings = []

        for message in parse_payload(payload):

            if isinstance(message, GridReplaced):
                self._columns = message.columns
                self._rows = message.rows

            elif isinstance(message, CellUpdate):
                self._apply_cell(message)

            elif isinstance(message, PositionChange):
                row = self._rows.get(message.row_id)

                if row is not None:
                    row.position = message.position

            elif isinstance(message, FieldUpdate):
                if message.field_id == "dyn1":
                    self.clock.update(
                        css_class=message.css_class,
                        text=message.value,
                        now_ms=now_ms,
                    )

            elif isinstance(message, Crossing):
                crossings.append(message)

        self._refresh()

        for crossing in crossings:
            self._handle_crossing(
                crossing,
                now_ms=now_ms,
            )

        self._compute_intervals()

    def _apply_cell(self, message: CellUpdate) -> None:
        """Aggiorna una cella della griglia."""

        row = self._rows.get(message.row_id)

        if row is None:
            row = GridRow(
                row_id=message.row_id,
                position=0,
            )

            self._rows[message.row_id] = row

        row.cells[message.cell_id] = message.value

    def _cell(self, row_id: str, column_type: str) -> str:
        """Legge una cella della riga indicata per tipo di colonna."""

        cell_id = self._columns.get(column_type)
        row = self._rows.get(row_id)

        if cell_id is None or row is None:
            return ""

        # Il feed inserisce markup nelle celle: si tiene il solo testo.
        return re.sub(r"<[^>]+>", " ", row.cells.get(cell_id, "")).strip()

    # ----- aggiornamento dei concorrenti -----

    def _refresh(self) -> None:
        """Riallinea ogni concorrente con la propria riga."""

        for row_id, row in self._rows.items():

            competitor = self._competitors.get(row_id)

            if competitor is None:
                competitor = Competitor(row_id=row_id)
                self._competitors[row_id] = competitor

            label = ""

            for column in TEAM_NAME_COLUMNS:
                label = self._cell(row_id, column)

                if label:
                    break

            competitor.team_label = label or competitor.team_label
            competitor.kart_number = self._cell(row_id, "no")

            competitor.position = (
                parse_int(self._cell(row_id, "rk"))
                or row.position
                or None
            )

            competitor.lap_number = parse_int(
                self._cell(row_id, "tlp")
            )

            competitor.last_lap_ms = parse_time_to_ms(
                self._cell(row_id, "llp")
            )

            competitor.best_lap_ms = parse_time_to_ms(
                self._cell(row_id, "blp")
            )

            competitor.pit_count = parse_int(
                self._cell(row_id, "pit")
            )

            competitor.gap = self._cell(row_id, "gap")
            competitor.gap_ms = parse_gap_ms(competitor.gap)

            competitor.feed_interval_ms = parse_gap_ms(
                self._cell(row_id, "int")
            )

    def _compute_intervals(self) -> None:
        """
        Ricava il distacco da chi precede.

        Prima la colonna "int" del feed, se il circuito la pubblica.
        Poi i passaggi sul traguardo: l'ultimo giro di una squadra
        contro lo stesso giro di chi la precede, che vale anche fra
        doppiati, per i quali il feed scrive "1 Giro" invece di un
        tempo. Infine la differenza dei distacchi dal primo.
        """

        ordered = self.competitors()

        for index, competitor in enumerate(ordered):

            if index == 0:
                competitor.interval_ms = None
                continue

            ahead = ordered[index - 1]

            interval_ms = competitor.feed_interval_ms

            if interval_ms is None:
                interval_ms = _crossing_interval(competitor, ahead)

            if interval_ms is None:
                # Il primo di solito non ha distacco scritto.
                ahead_gap_ms = (
                    ahead.gap_ms or 0
                    if index == 1
                    else ahead.gap_ms
                )

                if (
                    competitor.gap_ms is not None
                    and ahead_gap_ms is not None
                ):
                    interval_ms = competitor.gap_ms - ahead_gap_ms

            competitor.interval_ms = interval_ms

    def _handle_crossing(
        self,
        crossing: Crossing,
        now_ms: int,
    ) -> None:
        """Traduce un attraversamento nella storia del concorrente."""

        competitor = self._competitors.get(crossing.row_id)

        if competitor is None:
            return

        if crossing.sector == Sector.FINISH_LINE:
            self._record_lap(
                competitor,
                now_ms=now_ms,
            )

        elif crossing.sector == Sector.PIT_IN:
            competitor.in_pit = True

        elif crossing.sector == Sector.PIT_OUT:
            competitor.in_pit = False
            self._open_stint(competitor)

    def _record_lap(
        self,
        competitor: Competitor,
        now_ms: int,
    ) -> None:
        """Aggiunge alla storia il giro appena completato."""

        # Senza un tempo valido il giro non è analizzabile.
        if not competitor.last_lap_ms:
            return

        previous = (
            competitor.laps[-1].lap_number
            if competitor.laps
            else None
        )

        lap_number = competitor.lap_number

        # Circuito senza colonna dei giri: si contano da qui.
        if lap_number is None:
            lap_number = (previous or 0) + 1

        if previous is not None:

            # Stesso giro già registrato.
            if lap_number == previous:
                return

            # Il conto dei giri è ripartito: sessione nuova.
            if lap_number < previous:
                competitor.laps = []
                competitor.stints = []

        if not competitor.stints:
            competitor.stints.append(
                CompetitorStint(
                    stint_number=1,
                    start_lap=lap_number - 1,
                )
            )

        competitor.laps.append(
            CompetitorLap(
                lap_number=lap_number,
                lap_time_ms=competitor.last_lap_ms,
                race_time_ms=self.clock.race_time_ms(now_ms),
                kart_number=competitor.kart_number,
            )
        )

    def _open_stint(self, competitor: Competitor) -> None:
        """
        Chiude lo stint in corso e ne apre uno nuovo.

        Il giro che porta al pit appartiene allo stint concluso, il
        primo giro completato dopo l'uscita a quello nuovo.
        """

        if competitor.laps:
            last_lap = competitor.laps[-1].lap_number
        else:
            last_lap = competitor.lap_number or 0

        current = (
            competitor.stints[-1]
            if competitor.stints
            else None
        )

        if current is not None and current.end_lap is None:

            # Nessun giro nello stint aperto: è lo stesso pit.
            if current.start_lap >= last_lap:
                return

            current.end_lap = last_lap

        competitor.stints.append(
            CompetitorStint(
                stint_number=len(competitor.stints) + 1,
                start_lap=last_lap,
            )
        )


def _crossing_interval(
    competitor: Competitor,
    ahead: Competitor,
) -> Optional[int]:
    """Distacco fra i passaggi sullo stesso giro, se entrambi noti."""

    if not competitor.laps:
        return None

    last = competitor.laps[-1]

    if last.race_time_ms is None:
        return None

    # Il giro corrispondente è fra gli ultimi di chi precede.
    for lap in reversed(ahead.laps):

        if lap.lap_number < last.lap_number:
            return None

        if lap.lap_number == last.lap_number:
            if lap.race_time_ms is None:
                return None

            return last.race_time_ms - lap.race_time_ms

    return None
