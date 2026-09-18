"""
Parser del protocollo Apex Timing.

Il feed è testo: righe separate da "\n", ogni riga nella forma
"campo|classe|valore". Questo modulo non fa rete: trasforma soltanto
il testo in eventi tipizzati, così da poter essere testato offline
sulle catture salvate.
"""

from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser
import re
from typing import Optional


class SessionMode(Enum):
    """Modalità dichiarata dal messaggio "init"."""

    RACE = "r"
    PRACTICE = "p"
    NO_LIVE = "n"


class Sector(Enum):
    """Punto di rilevamento attraversato."""

    FINISH_LINE = "finish"
    SECTOR_1 = "s1"
    SECTOR_2 = "s2"
    PIT_IN = "in"
    PIT_OUT = "out"


# Una cella della griglia ha data-id nella forma "r12c6".
CELL_ID_PATTERN = re.compile(r"^(r\d+)(c\d+)$")


# ==============================
# EVENTI
# ==============================


@dataclass
class SessionReset:
    """Il server ha ricaricato la sessione da zero."""

    mode: SessionMode


@dataclass
class GridReplaced:
    """La griglia è stata inviata per intero."""

    columns: dict[str, str]
    labels: dict[str, str]
    rows: dict[str, "GridRow"]


@dataclass
class CellUpdate:
    """Aggiornamento di una singola cella della griglia."""

    row_id: str
    cell_id: str
    css_class: str
    value: str


@dataclass
class FieldUpdate:
    """Aggiornamento di un campo non appartenente alla griglia."""

    field_id: str
    css_class: str
    value: str


@dataclass
class Crossing:
    """Un kart ha attraversato un punto di rilevamento."""

    row_id: str
    sector: Sector
    raw_value: str


@dataclass
class PositionChange:
    """Un kart ha cambiato posizione in classifica."""

    row_id: str
    position: int


@dataclass
class GridRow:
    """Riga della griglia: corrisponde a un'iscrizione, non a un kart."""

    row_id: str
    position: int
    cells: dict[str, str] = field(default_factory=dict)


# ==============================
# PARSING DELLA GRIGLIA HTML
# ==============================


class _GridParser(HTMLParser):
    """Estrae righe e colonne dal <tbody> inviato dal feed."""

    def __init__(self):
        super().__init__()

        # data-type della colonna -> data-id della cella (es. "no" -> "c4").
        self.columns: dict[str, str] = {}

        # data-id della cella -> intestazione ("c10" -> "Tempo Pit").
        # Serve per le colonne che non dichiarano un data-type.
        self.labels: dict[str, str] = {}

        self.rows: dict[str, GridRow] = {}

        # data-id delle colonne nell'ordine di intestazione. Il client
        # ufficiale assegna il tipo di colonna per posizione, quindi la
        # posizione è il riferimento più affidabile.
        self._column_order: list[str] = []

        self._cell_index = 0
        self._current_row: Optional[GridRow] = None
        self._is_header = False
        self._current_cell: Optional[str] = None
        self._current_type: Optional[str] = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)

        if tag == "tr":
            row_id = attributes.get("data-id", "")
            self._is_header = "head" in (attributes.get("class") or "")

            if self._is_header:
                self._current_row = None
                return

            self._current_row = GridRow(
                row_id=row_id,
                position=int(attributes.get("data-pos") or 0),
            )

            self.rows[row_id] = self._current_row

            self._cell_index = 0

        elif tag == "td":
            self._current_cell = attributes.get("data-id")
            self._current_type = attributes.get("data-type")
            self._text = []

            # Solo la riga di intestazione dichiara i data-type.
            if self._is_header and self._current_cell:
                self._column_order.append(self._current_cell)

                if self._current_type:
                    self.columns[self._current_type] = self._current_cell

    def handle_data(self, data):
        self._text.append(data)

    def _canonical_cell_id(self) -> Optional[str]:
        """Riporta il data-id della cella alla forma usata in intestazione."""

        row = self._current_row

        # La posizione è il riferimento primario.
        if self._cell_index < len(self._column_order):
            return self._column_order[self._cell_index]

        if not self._current_cell:
            return None

        if row is not None and self._current_cell.startswith(row.row_id):
            return self._current_cell[len(row.row_id):]

        return self._current_cell

    def handle_endtag(self, tag):
        if tag == "td":
            if self._is_header and self._current_cell:
                self.labels[self._current_cell] = "".join(self._text).strip()

            if self._current_row is not None:
                text = "".join(self._text).strip()

                # Nelle righe dati il data-id è completo ("r12c4") mentre
                # l'intestazione usa la forma breve ("c4"): si riporta
                # tutto alla forma breve, che è quella usata anche dagli
                # aggiornamenti di cella.
                canonical = self._canonical_cell_id()

                if canonical:
                    self._current_row.cells[canonical] = text

                self._cell_index += 1

            self._current_cell = None
            self._current_type = None
            self._text = []

        elif tag == "tr":
            self._current_row = None
            self._is_header = False


def parse_grid(
    html: str,
) -> tuple[dict[str, str], dict[str, str], dict[str, GridRow]]:
    """
    Trasforma il <tbody> del feed in colonne e righe.

    Restituisce (colonne, intestazioni, righe) dove colonne mappa il
    data-type della colonna (es. "no", "dr", "llp") sul data-id
    ("c4", "c5"...) e intestazioni mappa il data-id sul testo di
    intestazione, per le colonne prive di data-type.
    """

    parser = _GridParser()
    parser.feed(html)

    return parser.columns, parser.labels, parser.rows


# ==============================
# PARSING DEI MESSAGGI
# ==============================


def parse_payload(payload: str) -> list:
    """
    Trasforma un payload del feed nella lista degli eventi.

    Replica la logica di tzfkz()/tzfjy() del client ufficiale.
    """

    events = []

    for line in payload.split("\n"):

        if not line:
            continue

        parts = line.split("|")

        # Il client ufficiale completa le righe corte con stringhe vuote.
        while len(parts) < 3:
            parts.append("")

        # Un valore può contenere "|": si riuniscono le parti eccedenti.
        field_id = parts[0]
        css_class = parts[1]
        value = "|".join(parts[2:])

        event = _classify(field_id, css_class, value)

        if event is not None:
            events.append(event)

    return events


def _classify(field_id: str, css_class: str, value: str):
    """Riconosce il tipo di un singolo messaggio."""

    if field_id == "init":
        try:
            mode = SessionMode(css_class)
        except ValueError:
            mode = SessionMode.PRACTICE

        return SessionReset(mode=mode)

    if field_id == "grid":
        columns, labels, rows = parse_grid(value)

        return GridReplaced(
            columns=columns,
            labels=labels,
            rows=rows,
        )

    # Il foglio di stile non ci interessa.
    if field_id == "css":
        return None

    if css_class == "#":
        try:
            position = int(value)
        except ValueError:
            return None

        return PositionChange(
            row_id=field_id,
            position=position,
        )

    if css_class == "*":
        return Crossing(
            row_id=field_id,
            sector=Sector.FINISH_LINE,
            raw_value=value,
        )

    if css_class in ("*i1", "*i2", "*in", "*out"):
        sector = {
            "*i1": Sector.SECTOR_1,
            "*i2": Sector.SECTOR_2,
            "*in": Sector.PIT_IN,
            "*out": Sector.PIT_OUT,
        }[css_class]

        return Crossing(
            row_id=field_id,
            sector=sector,
            raw_value=value,
        )

    cell_match = CELL_ID_PATTERN.match(field_id)

    if cell_match:
        return CellUpdate(
            row_id=cell_match.group(1),
            cell_id=cell_match.group(2),
            css_class=css_class,
            value=value,
        )

    return FieldUpdate(
        field_id=field_id,
        css_class=css_class,
        value=value,
    )


# ==============================
# TEMPI
# ==============================

TIME_PATTERN = re.compile(
    r"^(?:(?:(\d+):)?(\d+):)?(\d+)(?:[.,](\d{1,3}))?$"
)


def parse_time_to_ms(text: str) -> Optional[int]:
    """
    Converte un tempo del feed in millisecondi.

    Accetta "53.200", "1:03.421" e "1:02:03.456".
    Restituisce None se il testo non è un tempo.
    """

    if not text:
        return None

    cleaned = text.strip().replace("'", ":").replace('"', ".")

    match = TIME_PATTERN.match(cleaned)

    if match is None:
        return None

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3))

    # "1.2" significa 1 secondo e 200 ms, non 2 ms.
    fraction = match.group(4) or "0"
    milliseconds = int(fraction.ljust(3, "0"))

    return (
        hours * 3_600_000
        + minutes * 60_000
        + seconds * 1_000
        + milliseconds
    )


def parse_int(text: str) -> Optional[int]:
    """Converte in intero il contenuto di una cella, se possibile."""

    digits = re.sub(r"[^0-9-]", "", text or "")

    if not digits or digits == "-":
        return None

    try:
        return int(digits)
    except ValueError:
        return None
