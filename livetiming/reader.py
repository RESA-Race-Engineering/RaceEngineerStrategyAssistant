"""
Aggancio della squadra sul feed Apex.

Una riga della griglia è un'iscrizione, non un kart: il numero di
kart è un attributo della riga e cambia quando la squadra cambia
kart al pit. Per questo l'aggancio avviene sul nome della squadra
e non sul numero, mentre il numero inserito dalla GUI serve come
verifica incrociata.
"""

from dataclasses import dataclass, field
import re
import time
from typing import Optional

from livetiming.clock import RaceClock
from livetiming.protocol import (
    CellUpdate,
    Crossing,
    FieldUpdate,
    GridReplaced,
    GridRow,
    Sector,
    SessionReset,
    parse_payload,
    parse_time_to_ms,
)


# Colonne in cui cercare il nome della squadra, in ordine di preferenza.
TEAM_NAME_COLUMNS = ("dr", "grp")


def normalize(text: str) -> str:
    """Normalizza un nome per il confronto: spazi e maiuscole."""

    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


# ==============================
# EVENTI PER IL MOTORE DI GARA
# ==============================


@dataclass
class TeamBound:
    """La squadra è stata individuata nella griglia."""

    row_id: str
    team_label: str
    kart_number: str


@dataclass
class TeamLost:
    """La squadra non è più presente nella griglia."""

    row_id: str


@dataclass
class LapCompleted:
    """La squadra ha completato un giro."""

    lap_number: Optional[int]
    lap_time_ms: Optional[int]
    kart_number: str

    # Etichetta della riga in griglia: in una gara a squadre è il nome
    # della squadra, non del pilota al volante. Il pilota corrente lo
    # dichiara l'operatore a ogni cambio.
    team_label: str

    # Momento della gara, ricostruito dal cronometro del feed.
    # È il riferimento usato da Lap.race_time_ms.
    race_time_ms: Optional[int]

    received_at_ms: int
    clock_text: str


@dataclass
class PitIn:
    """La squadra è entrata ai box: lo stint si chiude qui."""

    lap_number: Optional[int]
    kart_number: str
    race_time_ms: Optional[int]
    received_at_ms: int


@dataclass
class PitOut:
    """La squadra è uscita dai box: inizia lo stint successivo."""

    lap_number: Optional[int]
    kart_number: str
    race_time_ms: Optional[int]
    received_at_ms: int


@dataclass
class KartNumberChanged:
    """Il feed segnala un numero di kart diverso dal precedente."""

    previous: str
    current: str


@dataclass
class KartNumberMismatch:
    """
    Il numero inserito dall'operatore non coincide con quello del feed.

    È la rete di sicurezza sull'aggancio: se scatta, o l'operatore ha
    sbagliato a digitare oppure stiamo seguendo la riga sbagliata.
    """

    operator_value: str
    feed_value: str


@dataclass
class SessionChanged:
    """Il server ha ricaricato la sessione: l'aggancio va rifatto."""

    mode: str


# ==============================
# STATO DELLA SQUADRA
# ==============================


@dataclass
class TeamState:
    """Ultimi valori noti della squadra seguita."""

    row_id: Optional[str] = None
    team_label: str = ""
    kart_number: str = ""

    position: Optional[int] = None
    lap_number: Optional[int] = None
    last_lap_ms: Optional[int] = None
    best_lap_ms: Optional[int] = None
    gap: str = ""
    pit_count: Optional[int] = None

    clock_text: str = ""
    race_time_ms: Optional[int] = None
    session_title: str = ""
    track_name: str = ""
    flag: str = ""

    # Numero di kart dichiarato dall'operatore nella GUI.
    operator_kart_number: str = ""

    in_pit: bool = False


class TeamTracker:
    """
    Segue una squadra sul feed e produce eventi di alto livello.

    Non conosce il modello di gara: si limita a dire cosa è successo,
    lasciando al motore la creazione di stint, giri e pit stop.
    """

    def __init__(
        self,
        team_name: str,
        race_duration_ms: Optional[int] = None,
    ):
        self.team_name = team_name
        self.state = TeamState()

        # La durata prevista serve a collocare un conto alla rovescia
        # anche quando ci si aggancia a gara già iniziata.
        self.clock = RaceClock(total_duration_ms=race_duration_ms)

        self._columns: dict[str, str] = {}
        self._labels: dict[str, str] = {}
        self._rows: dict[str, GridRow] = {}

    # ----- configurazione dalla GUI -----

    def set_operator_kart_number(self, kart_number: str) -> list:
        """
        Registra il numero di kart indicato dall'operatore.

        Va richiamato a ogni pit stop, quando la squadra cambia kart.
        """

        self.state.operator_kart_number = str(kart_number).strip()

        return self._check_kart_number()

    def _check_kart_number(self) -> list:
        """Confronta il numero dell'operatore con quello del feed."""

        declared = self.state.operator_kart_number
        actual = self.state.kart_number

        if not declared or not actual:
            return []

        if normalize(declared) == normalize(actual):
            return []

        return [
            KartNumberMismatch(
                operator_value=declared,
                feed_value=actual,
            )
        ]

    # ----- ingresso del feed -----

    def process(self, payload: str) -> list:
        """
        Applica un payload del feed e restituisce gli eventi rilevanti.

        Il payload viene trattato come un blocco unico: prima si
        aggiornano le celle, poi si interpretano gli attraversamenti,
        così un giro viene riportato con il tempo già aggiornato.
        """

        events = []
        crossings = []

        for message in parse_payload(payload):

            if isinstance(message, SessionReset):
                self._reset()
                events.append(SessionChanged(mode=message.mode.value))

            elif isinstance(message, GridReplaced):
                events.extend(self._apply_grid(message))

            elif isinstance(message, CellUpdate):
                self._apply_cell(message)

            elif isinstance(message, FieldUpdate):
                self._apply_field(message)

            elif isinstance(message, Crossing):
                if message.row_id == self.state.row_id:
                    crossings.append(message)

        events.extend(self._refresh_from_row())

        for crossing in crossings:
            events.extend(self._handle_crossing(crossing))

        return events

    def _reset(self) -> None:
        """Azzera l'aggancio mantenendo la scelta dell'operatore."""

        declared = self.state.operator_kart_number

        self.state = TeamState(operator_kart_number=declared)

        # Il cronometro non si azzera: una riconnessione ricarica la
        # sessione ma la gara sta continuando.

        self._columns = {}
        self._labels = {}
        self._rows = {}

    def _apply_grid(self, message: GridReplaced) -> list:
        """La griglia è stata reinviata: si rifà l'aggancio."""

        self._columns = message.columns
        self._labels = message.labels
        self._rows = message.rows

        previous_row_id = self.state.row_id

        row_id = self._find_team_row()

        if row_id is None:
            self.state.row_id = None

            if previous_row_id is not None:
                return [TeamLost(row_id=previous_row_id)]

            return []

        self.state.row_id = row_id

        events = []

        if row_id != previous_row_id:
            events.append(
                TeamBound(
                    row_id=row_id,
                    team_label=self._cell_by_type(row_id, "dr"),
                    kart_number=self._cell_by_type(row_id, "no"),
                )
            )

        return events

    def _find_team_row(self) -> Optional[str]:
        """
        Cerca la squadra nella griglia.

        Si guarda prima nelle colonne più probabili, poi in tutte le
        celle: non sappiamo in anticipo dove il cronometraggio scriva
        il nome della squadra.
        """

        wanted = normalize(self.team_name)

        if not wanted:
            return None

        for column in TEAM_NAME_COLUMNS:
            cell_id = self._columns.get(column)

            if cell_id is None:
                continue

            for row_id, row in self._rows.items():
                if normalize(row.cells.get(cell_id, "")) == wanted:
                    return row_id

        # Ripiego: confronto su tutte le celle, anche parziale.
        for row_id, row in self._rows.items():
            for value in row.cells.values():
                if wanted in normalize(value):
                    return row_id

        return None

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

    def _apply_field(self, message: FieldUpdate) -> None:
        """Aggiorna i campi generali della sessione."""

        if message.field_id == "dyn1":
            self.state.clock_text = message.value

            self.clock.update(
                css_class=message.css_class,
                text=message.value,
                now_ms=int(time.time() * 1000),
            )

        elif message.field_id == "title2":
            self.state.session_title = message.value

        elif message.field_id == "track":
            self.state.track_name = message.value

        elif message.field_id == "light":
            self.state.flag = message.css_class

    def _cell_by_type(self, row_id: str, column_type: str) -> str:
        """Legge una cella della riga indicata per tipo di colonna."""

        cell_id = self._columns.get(column_type)

        if cell_id is None:
            return ""

        row = self._rows.get(row_id)

        if row is None:
            return ""

        # Il feed inserisce markup nelle celle: si tiene il solo testo.
        return re.sub(r"<[^>]+>", " ", row.cells.get(cell_id, "")).strip()

    def _refresh_from_row(self) -> list:
        """Riallinea lo stato con i valori correnti della riga."""

        row_id = self.state.row_id

        if row_id is None:
            return []

        events = []

        kart_number = self._cell_by_type(row_id, "no")

        if kart_number and kart_number != self.state.kart_number:
            previous = self.state.kart_number
            self.state.kart_number = kart_number

            if previous:
                events.append(
                    KartNumberChanged(
                        previous=previous,
                        current=kart_number,
                    )
                )

            events.extend(self._check_kart_number())

        self.state.team_label = (
            self._cell_by_type(row_id, "dr")
            or self.state.team_label
        )

        self.state.gap = self._cell_by_type(row_id, "gap")

        self.state.last_lap_ms = parse_time_to_ms(
            self._cell_by_type(row_id, "llp")
        )

        self.state.best_lap_ms = parse_time_to_ms(
            self._cell_by_type(row_id, "blp")
        )

        self.state.lap_number = _to_int(
            self._cell_by_type(row_id, "tlp")
        )

        self.state.pit_count = _to_int(
            self._cell_by_type(row_id, "pit")
        )

        self.state.position = _to_int(
            self._cell_by_type(row_id, "rk")
        )

        return events

    def _handle_crossing(self, crossing: Crossing) -> list:
        """Traduce un attraversamento in un evento di gara."""

        now_ms = int(time.time() * 1000)

        race_time_ms = self.clock.race_time_ms(now_ms)
        self.state.race_time_ms = race_time_ms

        if crossing.sector == Sector.FINISH_LINE:
            return [
                LapCompleted(
                    lap_number=self.state.lap_number,
                    lap_time_ms=self.state.last_lap_ms,
                    kart_number=self.state.kart_number,
                    team_label=self.state.team_label,
                    race_time_ms=race_time_ms,
                    received_at_ms=now_ms,
                    clock_text=self.state.clock_text,
                )
            ]

        if crossing.sector == Sector.PIT_IN:
            self.state.in_pit = True

            return [
                PitIn(
                    lap_number=self.state.lap_number,
                    kart_number=self.state.kart_number,
                    race_time_ms=race_time_ms,
                    received_at_ms=now_ms,
                )
            ]

        if crossing.sector == Sector.PIT_OUT:
            self.state.in_pit = False

            return [
                PitOut(
                    lap_number=self.state.lap_number,
                    kart_number=self.state.kart_number,
                    race_time_ms=race_time_ms,
                    received_at_ms=now_ms,
                )
            ]

        return []


def _to_int(text: str) -> Optional[int]:
    """Converte in intero il contenuto di una cella, se possibile."""

    digits = re.sub(r"[^0-9-]", "", text or "")

    if not digits or digits == "-":
        return None

    try:
        return int(digits)
    except ValueError:
        return None
