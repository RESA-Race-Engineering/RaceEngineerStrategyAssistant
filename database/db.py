import sqlite3
from pathlib import Path

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


class RaceDatabase:
    """Gestisce il database SQLite della gara."""

    def __init__(
        self,
        db_path: str = "data/race_engineer.db",
        check_same_thread: bool = True,
    ):
        self.db_path = Path(db_path)

        # Crea la cartella data se non esiste
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False permette l'uso da più thread (GUI):
        # chi lo sceglie deve serializzare gli accessi con un lock.
        self.connection = sqlite3.connect(
            self.db_path,
            check_same_thread=check_same_thread,
        )
        self.create_tables()

        # Permette di leggere le colonne tramite nome
        self.connection.row_factory = sqlite3.Row

    def create_tables(self):
        """Crea tutte le tabelle necessarie alla V1."""

        cursor = self.connection.cursor()

        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS races (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                FOREIGN KEY (race_id) REFERENCES races(id)
            );

            CREATE TABLE IF NOT EXISTS karts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                number INTEGER NOT NULL,
                FOREIGN KEY (race_id) REFERENCES races(id)
            );

            CREATE TABLE IF NOT EXISTS drivers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                team_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                FOREIGN KEY (race_id) REFERENCES races(id),
                FOREIGN KEY (team_id) REFERENCES teams(id)
            );

            CREATE TABLE IF NOT EXISTS laps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                kart_id INTEGER NOT NULL,
                driver_id INTEGER,
                team_id INTEGER,
                lap_number INTEGER NOT NULL,
                lap_time_ms INTEGER NOT NULL,
                race_time_ms INTEGER,
                FOREIGN KEY (race_id) REFERENCES races(id),
                FOREIGN KEY (kart_id) REFERENCES karts(id),
                FOREIGN KEY (driver_id) REFERENCES drivers(id),
                FOREIGN KEY (team_id) REFERENCES teams(id)
            );

            CREATE TABLE IF NOT EXISTS stints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                stint_number INTEGER NOT NULL,
                kart_id INTEGER NOT NULL,
                driver_id INTEGER NOT NULL,
                start_time_ms INTEGER,
                end_time_ms INTEGER,
                start_lap INTEGER,
                end_lap INTEGER,
                FOREIGN KEY (race_id) REFERENCES races(id),
                FOREIGN KEY (kart_id) REFERENCES karts(id),
                FOREIGN KEY (driver_id) REFERENCES drivers(id)
            );

            CREATE TABLE IF NOT EXISTS pit_stops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                kart_out_id INTEGER NOT NULL,
                kart_in_id INTEGER NOT NULL,
                lap_before INTEGER NOT NULL,
                driver_out INTEGER,
                driver_in INTEGER,
                duration_ms INTEGER,
                refuel INTEGER NOT NULL DEFAULT 0,
                tire_change INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (race_id) REFERENCES races(id),
                FOREIGN KEY (kart_out_id) REFERENCES karts(id),
                FOREIGN KEY (kart_in_id) REFERENCES karts(id),
                FOREIGN KEY (driver_out) REFERENCES drivers(id),
                FOREIGN KEY (driver_in) REFERENCES drivers(id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                race_id INTEGER NOT NULL,
                time_ms INTEGER NOT NULL,
                description TEXT NOT NULL,
                penalty_ms INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (race_id) REFERENCES races(id)
            );
            """
        )

        self.connection.commit()

    def create_race(
        self,
        name: str,
        duration_ms: int,
        created_at: str,
    ) -> int:
        """Crea una nuova gara e restituisce il suo ID."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO races (
                name,
                duration_ms,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            (
                name,
                duration_ms,
                created_at,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid

    def create_team(
        self,
        race_id: int,
        name: str,
    ) -> int:
        """Crea un team associato a una gara."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO teams (
                race_id,
                name
            )
            VALUES (?, ?)
            """,
            (
                race_id,
                name,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid

    def create_kart(
        self,
        race_id: int,
        number: int,
    ) -> int:
        """Crea un kart associato a una gara."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO karts (
                race_id,
                number
            )
            VALUES (?, ?)
            """,
            (
                race_id,
                number,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid

    def create_driver(
        self,
        race_id: int,
        team_id: int,
        name: str,
    ) -> int:
        """Crea un pilota associato a una gara e a un team."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO drivers (
                race_id,
                team_id,
                name
            )
            VALUES (?, ?, ?)
            """,
            (
                race_id,
                team_id,
                name,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid

    def get_race(self, race_id: int):
        """Recupera una gara tramite il suo ID."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM races
            WHERE id = ?
            """,
            (race_id,),
        )

        return cursor.fetchone()

    def create_lap(
        self,
        race_id: int,
        kart_id: int,
        driver_id: int | None,
        team_id: int | None,
        lap_number: int,
        lap_time_ms: int,
        race_time_ms: int | None,
    ) -> int:
        """Salva un giro nel database."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO laps (
                race_id,
                kart_id,
                driver_id,
                team_id,
                lap_number,
                lap_time_ms,
                race_time_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                race_id,
                kart_id,
                driver_id,
                team_id,
                lap_number,
                lap_time_ms,
                race_time_ms,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid

    def get_laps(
        self,
        race_id: int,
        kart_id: int | None = None,
    ):
        """Recupera i giri di una gara."""

        cursor = self.connection.cursor()

        if kart_id is None:
            cursor.execute(
                """
                SELECT *
                FROM laps
                WHERE race_id = ?
                ORDER BY lap_number
                """,
                (race_id,),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM laps
                WHERE race_id = ?
                AND kart_id = ?
                ORDER BY lap_number
                """,
                (
                    race_id,
                    kart_id,
                ),
            )

        return cursor.fetchall()

    def create_stint(
        self,
        race_id: int,
        stint_number: int,
        kart_id: int,
        driver_id: int,
        start_time_ms: int | None,
        end_time_ms: int | None,
        start_lap: int | None,
        end_lap: int | None,
    ) -> int:
        """Salva uno stint nel database."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO stints (
                race_id,
                stint_number,
                kart_id,
                driver_id,
                start_time_ms,
                end_time_ms,
                start_lap,
                end_lap
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                race_id,
                stint_number,
                kart_id,
                driver_id,
                start_time_ms,
                end_time_ms,
                start_lap,
                end_lap,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid

    def get_stints(
        self,
        race_id: int,
        kart_id: int | None = None,
    ):
        """Recupera gli stint di una gara."""

        cursor = self.connection.cursor()

        if kart_id is None:
            cursor.execute(
                """
                SELECT *
                FROM stints
                WHERE race_id = ?
                ORDER BY kart_id, stint_number
                """,
                (race_id,),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM stints
                WHERE race_id = ?
                AND kart_id = ?
                ORDER BY stint_number
                """,
                (
                    race_id,
                    kart_id,
                ),
            )

        return cursor.fetchall()

    def create_pit_stop(
        self,
        race_id: int,
        kart_out_id: int,
        kart_in_id: int,
        lap_before: int,
        driver_out: int | None,
        driver_in: int | None,
        duration_ms: int | None,
        refuel: bool,
        tire_change: bool,
    ) -> int:
        """Salva un pit stop nel database."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO pit_stops (
                race_id,
                kart_out_id,
                kart_in_id,
                lap_before,
                driver_out,
                driver_in,
                duration_ms,
                refuel,
                tire_change
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                race_id,
                kart_out_id,
                kart_in_id,
                lap_before,
                driver_out,
                driver_in,
                duration_ms,
                int(refuel),
                int(tire_change),
            ),
        )

        self.connection.commit()

        return cursor.lastrowid

    def update_pit_stop_duration(
        self,
        race_id: int,
        lap_before: int,
        duration_ms: int,
    ):
        """
        Aggiorna la durata di un pit confermato prima dell'uscita
        dai box.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            """
            UPDATE pit_stops
            SET duration_ms = ?
            WHERE race_id = ?
            AND lap_before = ?
            AND duration_ms IS NULL
            """,
            (
                duration_ms,
                race_id,
                lap_before,
            ),
        )

        self.connection.commit()

    def get_pit_stops(
        self,
        race_id: int,
        kart_id: int | None = None,
    ):
        """Recupera i pit stop di una gara."""

        cursor = self.connection.cursor()

        if kart_id is None:
            cursor.execute(
                """
                SELECT *
                FROM pit_stops
                WHERE race_id = ?
                ORDER BY lap_before
                """,
                (race_id,),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM pit_stops
                WHERE race_id = ?
                AND (
                    kart_out_id = ?
                    OR kart_in_id = ?
                )
                ORDER BY lap_before
                """,
                (
                    race_id,
                    kart_id,
                    kart_id,
                ),
            )

        return cursor.fetchall()

    def create_event(
        self,
        race_id: int,
        time_ms: int,
        description: str,
        penalty_ms: int = 0,
    ) -> int:
        """Salva un evento o una penalità."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT INTO events (
                race_id,
                time_ms,
                description,
                penalty_ms
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                race_id,
                time_ms,
                description,
                penalty_ms,
            ),
        )

        self.connection.commit()

        return cursor.lastrowid

    def get_events(
        self,
        race_id: int,
    ):
        """Recupera tutti gli eventi di una gara."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM events
            WHERE race_id = ?
            ORDER BY time_ms
            """,
            (race_id,),
        )

        return cursor.fetchall()

    def update_stint_start(
        self,
        race_id: int,
        kart_id: int,
        stint_number: int,
        start_time_ms: int,
    ):
        """Aggiorna il tempo di inizio di uno stint."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            UPDATE stints
            SET start_time_ms = ?
            WHERE race_id = ?
            AND kart_id = ?
            AND stint_number = ?
            """,
            (
                start_time_ms,
                race_id,
                kart_id,
                stint_number,
            ),
        )

        self.connection.commit()

    def update_stint_end(
        self,
        race_id: int,
        kart_id: int,
        stint_number: int,
        end_time_ms: int | None,
        end_lap: int | None,
    ):
        """Aggiorna la fine di uno stint."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            UPDATE stints
            SET end_time_ms = ?,
                end_lap = ?
            WHERE race_id = ?
            AND kart_id = ?
            AND stint_number = ?
            """,
            (
                end_time_ms,
                end_lap,
                race_id,
                kart_id,
                stint_number,
            ),
        )

        self.connection.commit()

    def get_last_race_id(self) -> int | None:
        """Restituisce l'ID dell'ultima gara creata."""

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT MAX(id) AS id
            FROM races
            """
        )

        return cursor.fetchone()["id"]

    def _race_rows(
        self,
        table: str,
        race_id: int,
        order_by: str,
    ):
        """
        Legge tutte le righe di una tabella relative a una gara.

        Tabella e ordinamento arrivano solo da load_race(), mai da
        dati esterni.
        """

        cursor = self.connection.cursor()

        cursor.execute(
            f"""
            SELECT *
            FROM {table}
            WHERE race_id = ?
            ORDER BY {order_by}
            """,
            (race_id,),
        )

        return cursor.fetchall()

    def load_race(self, race_id: int) -> Race:
        """
        Ricostruisce una gara dal database.

        Gli oggetti usano gli ID del database, come durante la gara.
        Serve a riaprire una gara dopo la chiusura del programma e a
        esportarla. Della configurazione il database conserva solo la
        durata: il resto prende i valori predefiniti di RaceConfig.
        """

        race_row = self.get_race(race_id)

        if race_row is None:
            raise ValueError(
                f"La gara {race_id} non esiste nel database."
            )

        race = Race(
            config=RaceConfig(
                duration_ms=race_row["duration_ms"],
            )
        )

        race.teams = [
            Team(
                id=row["id"],
                name=row["name"],
            )
            for row in self._race_rows("teams", race_id, "id")
        ]

        race.karts = [
            Kart(
                id=row["id"],
                number=row["number"],
            )
            for row in self._race_rows("karts", race_id, "id")
        ]

        race.drivers = [
            Driver(
                id=row["id"],
                name=row["name"],
                team_id=row["team_id"],
            )
            for row in self._race_rows("drivers", race_id, "id")
        ]

        race.laps = [
            Lap(
                lap_number=row["lap_number"],
                lap_time_ms=row["lap_time_ms"],
                race_time_ms=row["race_time_ms"],
                driver_id=row["driver_id"],
                team_id=row["team_id"],
                kart_id=row["kart_id"],
            )
            for row in self._race_rows("laps", race_id, "lap_number")
        ]

        race.stints = [
            Stint(
                stint_number=row["stint_number"],
                driver_id=row["driver_id"],
                kart_id=row["kart_id"],
                start_time_ms=row["start_time_ms"],
                end_time_ms=row["end_time_ms"],
                start_lap=row["start_lap"],
                end_lap=row["end_lap"],
            )
            for row in self._race_rows("stints", race_id, "stint_number")
        ]

        race.pit_stops = [
            PitStop(
                kart_out_id=row["kart_out_id"],
                kart_in_id=row["kart_in_id"],
                lap_before=row["lap_before"],
                driver_out=row["driver_out"],
                driver_in=row["driver_in"],
                duration_ms=row["duration_ms"],
                refuel=bool(row["refuel"]),
                tire_change=bool(row["tire_change"]),
            )
            for row in self._race_rows("pit_stops", race_id, "lap_before")
        ]

        race.events = [
            RaceEvent(
                time_ms=row["time_ms"],
                description=row["description"],
                penalty_ms=row["penalty_ms"],
            )
            for row in self._race_rows("events", race_id, "time_ms")
        ]

        return race

    def close(self):
        """Chiude la connessione al database."""

        self.connection.close()
