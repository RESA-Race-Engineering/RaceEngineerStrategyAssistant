"""
Esportazione della gara in file CSV, per le analisi successive.

Una gara diventa una cartella con un file per tabella:

    gara.csv    nome della squadra e configurazione
    giri.csv    ogni giro, con pilota, kart e stint
    stint.csv   ogni stint, con durata e numero di giri
    pit.csv     ogni pit stop, con cambio di kart e di pilota
    eventi.csv  eventi e penalità

Piloti e kart compaiono per nome e per numero, non per ID: i file si
leggono da soli, senza il database. I tempi restano in millisecondi
interi, come nel resto del programma. Separatore ";" e codifica UTF-8
con BOM: così Excel in italiano li apre correttamente con un doppio
clic.

import_race_csv() ricostruisce la stessa Race usata durante la gara,
quindi grafici e analisi funzionano allo stesso modo sui dati dal
vivo e sui file salvati.

Da riga di comando esporta una gara dal database:

    python -m database.csv_export
    python -m database.csv_export --race-id 3 --out data/export/prova
"""

import argparse
import csv
from dataclasses import fields
from pathlib import Path
from typing import Optional

from core.analytics import get_stint_laps
from core.models import (
    Driver,
    Kart,
    Lap,
    PitStop,
    Race,
    RaceConfig,
    RaceEvent,
    Stint,
    Team,
)
from database.db import RaceDatabase


DELIMITER = ";"
ENCODING = "utf-8-sig"

RACE_FILE = "gara.csv"
LAPS_FILE = "giri.csv"
STINTS_FILE = "stint.csv"
PITS_FILE = "pit.csv"
EVENTS_FILE = "eventi.csv"

RACE_COLUMNS = [
    "campo",
    "valore",
]

LAP_COLUMNS = [
    "giro",
    "tempo_giro_ms",
    "tempo_gara_ms",
    "stint",
    "pilota",
    "kart",
]

STINT_COLUMNS = [
    "stint",
    "pilota",
    "kart",
    "giro_inizio",
    "giro_fine",
    "inizio_ms",
    "fine_ms",
    "durata_ms",
    "giri",
]

PIT_COLUMNS = [
    "giro",
    "kart_precedente",
    "kart_nuovo",
    "pilota_precedente",
    "pilota_nuovo",
    "durata_ms",
    "rifornimento",
    "cambio_gomme",
]

EVENT_COLUMNS = [
    "tempo_ms",
    "descrizione",
    "penalita_ms",
]

# Chiave di gara.csv per il nome della squadra; le altre chiavi
# sono i campi di RaceConfig.
TEAM_KEY = "squadra"


# ==============================
# SCRITTURA
# ==============================


def _cell(value) -> str:
    """Rende un valore come cella: None diventa una cella vuota."""

    if value is None:
        return ""

    if isinstance(value, bool):
        return "1" if value else "0"

    return str(value)


def _write(
    path: Path,
    columns: list[str],
    rows: list[list],
) -> None:
    """Scrive un file CSV con intestazione."""

    with path.open("w", encoding=ENCODING, newline="") as handle:
        writer = csv.writer(
            handle,
            delimiter=DELIMITER,
        )

        writer.writerow(columns)

        for row in rows:
            writer.writerow([_cell(value) for value in row])


def export_race_csv(race: Race, folder: str | Path) -> Path:
    """
    Scrive la gara nella cartella indicata.

    Si può richiamare in qualunque momento: i file vengono riscritti
    per intero con lo stato attuale della gara.
    """

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    driver_names = {
        driver.id: driver.name
        for driver in race.drivers
    }

    kart_numbers = {
        kart.id: kart.number
        for kart in race.karts
    }

    # ----- gara -----

    race_rows = [
        [
            TEAM_KEY,
            race.teams[0].name if race.teams else "",
        ]
    ]

    for config_field in fields(RaceConfig):
        race_rows.append(
            [
                config_field.name,
                getattr(race.config, config_field.name),
            ]
        )

    _write(
        folder / RACE_FILE,
        RACE_COLUMNS,
        race_rows,
    )

    # ----- giri -----

    stint_of_lap = {}

    for stint in race.stints:
        for lap in get_stint_laps(race.laps, stint):
            stint_of_lap[lap.lap_number] = stint.stint_number

    _write(
        folder / LAPS_FILE,
        LAP_COLUMNS,
        [
            [
                lap.lap_number,
                lap.lap_time_ms,
                lap.race_time_ms,
                stint_of_lap.get(lap.lap_number),
                driver_names.get(lap.driver_id),
                kart_numbers.get(lap.kart_id),
            ]
            for lap in race.laps
        ],
    )

    # ----- stint -----

    _write(
        folder / STINTS_FILE,
        STINT_COLUMNS,
        [
            [
                stint.stint_number,
                driver_names.get(stint.driver_id),
                kart_numbers.get(stint.kart_id),
                stint.start_lap,
                stint.end_lap,
                stint.start_time_ms,
                stint.end_time_ms,
                stint.duration_ms,
                len(get_stint_laps(race.laps, stint)),
            ]
            for stint in race.stints
        ],
    )

    # ----- pit stop -----

    _write(
        folder / PITS_FILE,
        PIT_COLUMNS,
        [
            [
                pit_stop.lap_before,
                kart_numbers.get(pit_stop.kart_out_id),
                kart_numbers.get(pit_stop.kart_in_id),
                driver_names.get(pit_stop.driver_out),
                driver_names.get(pit_stop.driver_in),
                pit_stop.duration_ms,
                pit_stop.refuel,
                pit_stop.tire_change,
            ]
            for pit_stop in race.pit_stops
        ],
    )

    # ----- eventi -----

    _write(
        folder / EVENTS_FILE,
        EVENT_COLUMNS,
        [
            [
                event.time_ms,
                event.description,
                event.penalty_ms,
            ]
            for event in race.events
        ],
    )

    return folder


# ==============================
# LETTURA
# ==============================


def _read(
    path: Path,
    columns: list[str],
) -> list[tuple[int, dict]]:
    """
    Legge un file CSV e restituisce (numero di riga, valori).

    Controlla che ci siano tutte le colonne attese: le colonne in più
    aggiunte a mano per le analisi vengono ignorate.
    """

    with path.open(encoding=ENCODING, newline="") as handle:
        reader = csv.DictReader(
            handle,
            delimiter=DELIMITER,
        )

        missing = [
            column
            for column in columns
            if column not in (reader.fieldnames or [])
        ]

        if missing:
            raise ValueError(
                f"{path.name}: mancano le colonne "
                f"{', '.join(missing)}."
            )

        # La riga 1 è l'intestazione.
        return [
            (line_number, row)
            for line_number, row in enumerate(reader, start=2)
        ]


def _int(
    value: Optional[str],
    where: str,
    required: bool = True,
) -> Optional[int]:
    """Converte una cella in intero; vuota vale None se ammessa."""

    text = (value or "").strip()

    if not text:
        if required:
            raise ValueError(f"{where}: valore mancante.")

        return None

    try:
        return int(text)
    except ValueError:
        raise ValueError(
            f"{where}: '{text}' non è un numero intero."
        ) from None


class _Registry:
    """Assegna un ID a ogni pilota e kart incontrato nei file."""

    def __init__(self):
        self.driver_ids: dict[str, int] = {}
        self.kart_ids: dict[int, int] = {}

    def driver(self, name: Optional[str]) -> Optional[int]:
        name = (name or "").strip()

        if not name:
            return None

        if name not in self.driver_ids:
            self.driver_ids[name] = len(self.driver_ids) + 1

        return self.driver_ids[name]

    def kart(self, number: Optional[int]) -> Optional[int]:
        if number is None:
            return None

        if number not in self.kart_ids:
            self.kart_ids[number] = len(self.kart_ids) + 1

        return self.kart_ids[number]


def import_race_csv(folder: str | Path) -> Race:
    """
    Ricostruisce una gara da una cartella esportata.

    Serve solo giri.csv: gli altri file, se mancano, lasciano vuote
    le rispettive parti della gara. Piloti e kart ricevono ID nuovi,
    assegnati nell'ordine in cui compaiono.
    """

    folder = Path(folder)

    if not (folder / LAPS_FILE).exists():
        raise ValueError(
            f"{folder}: manca il file {LAPS_FILE}."
        )

    registry = _Registry()

    # ----- gara -----

    config = RaceConfig()
    team_name = ""

    if (folder / RACE_FILE).exists():
        values = {
            row["campo"]: row["valore"]
            for _, row in _read(folder / RACE_FILE, RACE_COLUMNS)
        }

        team_name = values.get(TEAM_KEY, "")

        for config_field in fields(RaceConfig):
            if values.get(config_field.name):
                setattr(
                    config,
                    config_field.name,
                    _int(
                        values[config_field.name],
                        f"{RACE_FILE} {config_field.name}",
                    ),
                )

    team = Team(
        id=1,
        name=team_name or "Squadra",
    )

    race = Race(
        config=config,
        teams=[team],
    )

    # ----- giri -----

    for line, row in _read(folder / LAPS_FILE, LAP_COLUMNS):
        where = f"{LAPS_FILE} riga {line}"

        race.laps.append(
            Lap(
                lap_number=_int(row["giro"], where),
                lap_time_ms=_int(row["tempo_giro_ms"], where),
                race_time_ms=_int(
                    row["tempo_gara_ms"],
                    where,
                    required=False,
                ),
                driver_id=registry.driver(row["pilota"]),
                team_id=team.id,
                kart_id=registry.kart(
                    _int(row["kart"], where, required=False)
                ),
            )
        )

    # ----- stint -----

    if (folder / STINTS_FILE).exists():
        for line, row in _read(folder / STINTS_FILE, STINT_COLUMNS):
            where = f"{STINTS_FILE} riga {line}"

            race.stints.append(
                Stint(
                    stint_number=_int(row["stint"], where),
                    driver_id=registry.driver(row["pilota"]),
                    kart_id=registry.kart(
                        _int(row["kart"], where, required=False)
                    ),
                    start_time_ms=_int(
                        row["inizio_ms"],
                        where,
                        required=False,
                    ),
                    end_time_ms=_int(
                        row["fine_ms"],
                        where,
                        required=False,
                    ),
                    start_lap=_int(
                        row["giro_inizio"],
                        where,
                        required=False,
                    ),
                    end_lap=_int(
                        row["giro_fine"],
                        where,
                        required=False,
                    ),
                )
            )

    # ----- pit stop -----

    if (folder / PITS_FILE).exists():
        for line, row in _read(folder / PITS_FILE, PIT_COLUMNS):
            where = f"{PITS_FILE} riga {line}"

            race.pit_stops.append(
                PitStop(
                    kart_out_id=registry.kart(
                        _int(row["kart_precedente"], where)
                    ),
                    kart_in_id=registry.kart(
                        _int(row["kart_nuovo"], where)
                    ),
                    lap_before=_int(row["giro"], where),
                    driver_out=registry.driver(row["pilota_precedente"]),
                    driver_in=registry.driver(row["pilota_nuovo"]),
                    duration_ms=_int(
                        row["durata_ms"],
                        where,
                        required=False,
                    ),
                    refuel=row["rifornimento"].strip() == "1",
                    tire_change=row["cambio_gomme"].strip() == "1",
                )
            )

    # ----- eventi -----

    if (folder / EVENTS_FILE).exists():
        for line, row in _read(folder / EVENTS_FILE, EVENT_COLUMNS):
            where = f"{EVENTS_FILE} riga {line}"

            race.events.append(
                RaceEvent(
                    time_ms=_int(row["tempo_ms"], where),
                    description=row["descrizione"],
                    penalty_ms=_int(
                        row["penalita_ms"],
                        where,
                        required=False,
                    ) or 0,
                )
            )

    # ----- piloti e kart incontrati -----

    race.drivers = [
        Driver(
            id=driver_id,
            name=name,
            team_id=team.id,
        )
        for name, driver_id in registry.driver_ids.items()
    ]

    race.karts = [
        Kart(
            id=kart_id,
            number=number,
        )
        for number, kart_id in registry.kart_ids.items()
    ]

    return race


# ==============================
# RIGA DI COMANDO
# ==============================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Esporta una gara dal database in file CSV."
    )

    parser.add_argument(
        "--db",
        default="data/race_engineer.db",
        help="Database da cui leggere la gara.",
    )

    parser.add_argument(
        "--race-id",
        type=int,
        default=0,
        help="Gara da esportare: senza indicazione, l'ultima.",
    )

    parser.add_argument(
        "--out",
        default="",
        help="Cartella di destinazione: di serie data/export/gara_<id>.",
    )

    arguments = parser.parse_args()

    # RaceDatabase crea il file se manca: meglio fermarsi prima.
    if not Path(arguments.db).exists():
        raise SystemExit(f"Database non trovato: {arguments.db}")

    db = RaceDatabase(arguments.db)

    try:
        race_id = arguments.race_id or db.get_last_race_id()

        if race_id is None:
            raise SystemExit("Il database non contiene gare.")

        race = db.load_race(race_id)

    finally:
        db.close()

    folder = export_race_csv(
        race,
        arguments.out or f"data/export/gara_{race_id}",
    )

    print(f"Gara {race_id} esportata in {folder}")
    print(f"  giri    : {len(race.laps)}")
    print(f"  stint   : {len(race.stints)}")
    print(f"  pit stop: {len(race.pit_stops)}")
    print(f"  eventi  : {len(race.events)}")


if __name__ == "__main__":
    main()
