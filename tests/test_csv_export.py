"""
Prove dell'esportazione CSV.

Il requisito è che una gara riletta dai file sia indistinguibile, per
grafici e analisi, dalla gara registrata dal vivo.
"""

import tempfile
import unittest
from pathlib import Path

from core.analytics import ANALYSIS_WINDOWS, analyze_window
from core.models import (
    Driver,
    Kart,
    Race,
    RaceConfig,
    RaceEvent,
    Team,
)
from core.race_logic import (
    register_lap,
    register_pit_stop,
    start_stint,
)
from database.csv_export import (
    LAPS_FILE,
    STINTS_FILE,
    export_race_csv,
    import_race_csv,
)
from database.db import RaceDatabase


def registra_gara(race: Race, db=None, race_id=None) -> Race:
    """
    Tre giri di Marco sul kart 18, pit, due giri di Niccolò sul 7.

    Il tempo gara è la somma dei giri più il pit, così lo stint 1
    parte da zero. Kart e piloti devono già essere nella gara.
    """

    kart_1, kart_2 = race.karts
    driver_1, driver_2 = race.drivers

    race_time_ms = 0

    start_stint(
        race=race,
        kart_id=kart_1.id,
        driver_id=driver_1.id,
        db=db,
        race_id=race_id,
    )

    for lap_number in (1, 2, 3):
        race_time_ms += 60_000 + lap_number

        register_lap(
            race=race,
            kart_id=kart_1.id,
            lap_number=lap_number,
            lap_time_ms=60_000 + lap_number,
            race_time_ms=race_time_ms,
            db=db,
            race_id=race_id,
        )

    register_pit_stop(
        race=race,
        kart_id=kart_1.id,
        new_kart_id=kart_2.id,
        lap_before=3,
        driver_in=driver_2.id,
        duration_ms=91_000,
        refuel=True,
        db=db,
        race_id=race_id,
    )

    race_time_ms += 91_000

    for lap_number in (4, 5):
        race_time_ms += 60_000 + lap_number

        register_lap(
            race=race,
            kart_id=kart_2.id,
            lap_number=lap_number,
            lap_time_ms=60_000 + lap_number,
            race_time_ms=race_time_ms,
            db=db,
            race_id=race_id,
        )

    return race


def gara_in_memoria() -> Race:
    race = Race(
        config=RaceConfig(min_stints=12),
        teams=[Team(id=1, name="Scuderia Dante")],
        karts=[
            Kart(id=1, number=18),
            Kart(id=2, number=7),
        ],
        drivers=[
            Driver(id=1, name="Marco", team_id=1),
            Driver(id=2, name="Niccolò", team_id=1),
        ],
        events=[
            RaceEvent(
                time_ms=150_000,
                description="Track limits; curva 3",
                penalty_ms=5_000,
            ),
        ],
    )

    return registra_gara(race)


def piloti_dei_giri(race: Race) -> list[str]:
    names = {driver.id: driver.name for driver in race.drivers}

    return [names[lap.driver_id] for lap in race.laps]


def kart_dei_giri(race: Race) -> list[int]:
    numbers = {kart.id: kart.number for kart in race.karts}

    return [numbers[lap.kart_id] for lap in race.laps]


class TestAndataRitorno(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name) / "gara"

        self.race = gara_in_memoria()
        export_race_csv(self.race, self.folder)
        self.loaded = import_race_csv(self.folder)

    def tearDown(self):
        self.temp.cleanup()

    def test_giri(self):
        self.assertEqual(
            [(l.lap_number, l.lap_time_ms, l.race_time_ms) for l in self.loaded.laps],
            [(l.lap_number, l.lap_time_ms, l.race_time_ms) for l in self.race.laps],
        )

        self.assertEqual(
            piloti_dei_giri(self.loaded),
            ["Marco"] * 3 + ["Niccolò"] * 2,
        )

        self.assertEqual(kart_dei_giri(self.loaded), [18, 18, 18, 7, 7])

    def test_stint_e_pit(self):
        stints = self.loaded.stints

        self.assertEqual(
            [(s.stint_number, s.start_lap, s.end_lap) for s in stints],
            [(1, 0, 3), (2, 3, None)],
        )

        pit_stop = self.loaded.pit_stops[0]
        karts = {kart.id: kart.number for kart in self.loaded.karts}

        self.assertEqual(pit_stop.lap_before, 3)
        self.assertEqual(pit_stop.duration_ms, 91_000)
        self.assertEqual(karts[pit_stop.kart_out_id], 18)
        self.assertEqual(karts[pit_stop.kart_in_id], 7)
        self.assertTrue(pit_stop.refuel)
        self.assertFalse(pit_stop.tire_change)

    def test_configurazione_ed_eventi(self):
        self.assertEqual(self.loaded.config, self.race.config)
        self.assertEqual(self.loaded.teams[0].name, "Scuderia Dante")

        # Il ";" nella descrizione non deve spezzare la riga.
        self.assertEqual(self.loaded.events, self.race.events)

    def test_stesse_analisi_dal_vivo_e_dai_file(self):
        for label, window in ANALYSIS_WINDOWS.items():
            with self.subTest(finestra=label):
                self.assertEqual(
                    analyze_window(
                        self.loaded.laps,
                        self.loaded.stints,
                        window,
                    ),
                    analyze_window(
                        self.race.laps,
                        self.race.stints,
                        window,
                    ),
                )

    def test_formato_per_excel(self):
        raw = (self.folder / LAPS_FILE).read_bytes()

        # BOM UTF-8 e separatore ";".
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(
            "giro;tempo_giro_ms;tempo_gara_ms;stint;pilota;kart",
            raw.decode("utf-8-sig").splitlines()[0],
        )

        self.assertIn(
            "5;60005;391015;2;Niccolò;7",
            raw.decode("utf-8-sig"),
        )


class TestFileModificati(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

        export_race_csv(gara_in_memoria(), self.folder)

    def tearDown(self):
        self.temp.cleanup()

    def riscrivi(self, name: str, old: str, new: str) -> None:
        path = self.folder / name
        text = path.read_text(encoding="utf-8-sig")

        path.write_text(
            text.replace(old, new),
            encoding="utf-8-sig",
        )

    def test_colonna_aggiunta_a_mano_ignorata(self):
        self.riscrivi(LAPS_FILE, "pilota;kart\n", "pilota;kart;note\n")

        self.assertEqual(len(import_race_csv(self.folder).laps), 5)

    def test_colonna_mancante(self):
        self.riscrivi(LAPS_FILE, "tempo_giro_ms;", "")

        with self.assertRaisesRegex(ValueError, "tempo_giro_ms"):
            import_race_csv(self.folder)

    def test_numero_non_valido_indica_la_riga(self):
        self.riscrivi(LAPS_FILE, "60002", "1:00.002")

        with self.assertRaisesRegex(ValueError, "giri.csv riga 3"):
            import_race_csv(self.folder)

    def test_solo_i_giri(self):
        for path in self.folder.iterdir():
            if path.name != LAPS_FILE:
                path.unlink()

        race = import_race_csv(self.folder)

        self.assertEqual(len(race.laps), 5)
        self.assertEqual(race.stints, [])
        self.assertEqual(
            sorted(driver.name for driver in race.drivers),
            ["Marco", "Niccolò"],
        )

    def test_cartella_senza_giri(self):
        (self.folder / LAPS_FILE).unlink()

        with self.assertRaisesRegex(ValueError, LAPS_FILE):
            import_race_csv(self.folder)


class TestDalDatabase(unittest.TestCase):
    """La gara si esporta anche dopo la chiusura del programma."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = RaceDatabase(str(Path(self.temp.name) / "gara.db"))

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_ricarica_ed_esporta(self):
        db = self.db

        race_id = db.create_race(
            name="Prova",
            duration_ms=6 * 60 * 60 * 1000,
            created_at="2026-09-18T20:00:00",
        )

        team_id = db.create_team(race_id=race_id, name="Scuderia Dante")

        race = Race(
            config=RaceConfig(),
            teams=[Team(id=team_id, name="Scuderia Dante")],
            karts=[
                Kart(id=db.create_kart(race_id=race_id, number=18), number=18),
                Kart(id=db.create_kart(race_id=race_id, number=7), number=7),
            ],
            drivers=[
                Driver(
                    id=db.create_driver(race_id=race_id, team_id=team_id, name=name),
                    name=name,
                    team_id=team_id,
                )
                for name in ("Marco", "Niccolò")
            ],
        )

        registra_gara(race, db=db, race_id=race_id)

        self.assertEqual(db.get_last_race_id(), race_id)

        loaded = db.load_race(race_id)

        self.assertEqual(loaded.laps, race.laps)
        self.assertEqual(loaded.stints, race.stints)
        self.assertEqual(loaded.pit_stops, race.pit_stops)

        folder = Path(self.temp.name) / "export"
        export_race_csv(loaded, folder)

        text = (folder / STINTS_FILE).read_text(encoding="utf-8-sig")

        self.assertIn("1;Marco;18;0;3;0;180006;180006;3", text)

    def test_gara_inesistente(self):
        with self.assertRaisesRegex(ValueError, "non esiste"):
            self.db.load_race(99)


if __name__ == "__main__":
    unittest.main()
