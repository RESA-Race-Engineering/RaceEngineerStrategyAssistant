"""
Prove delle finestre di analisi.

La gara di riferimento segue le regole reali: la squadra cambia kart
a ogni pit, quindi ogni finestra deve attraversare i cambi di kart.
"""

import unittest

from core.analytics import (
    ANALYSIS_WINDOWS,
    AnalysisWindow,
    AnalysisWindowType,
    analyze_window,
    get_current_stint,
    get_laps_for_window,
    get_laps_in_last,
)
from core.models import (
    Driver,
    Kart,
    Lap,
    Race,
    RaceConfig,
    Team,
)
from core.race_logic import (
    register_lap,
    register_pit_stop,
    start_stint,
)


def gara_con_cambio_kart() -> Race:
    """
    Tre giri di Marco sul kart 18, pit, due giri di Luca sul kart 7.

    Ogni giro dura un minuto.
    """

    race = Race(
        config=RaceConfig(),
        teams=[Team(id=1, name="Scuderia Dante")],
        karts=[
            Kart(id=1, number=18),
            Kart(id=2, number=7),
        ],
        drivers=[
            Driver(id=1, name="Marco", team_id=1),
            Driver(id=2, name="Luca", team_id=1),
        ],
    )

    start_stint(
        race=race,
        kart_id=1,
        driver_id=1,
    )

    for lap_number in (1, 2, 3):
        register_lap(
            race=race,
            kart_id=1,
            lap_number=lap_number,
            lap_time_ms=60_000 + lap_number,
            race_time_ms=lap_number * 60_000,
        )

    register_pit_stop(
        race=race,
        kart_id=1,
        new_kart_id=2,
        lap_before=3,
        driver_in=2,
        duration_ms=90_000,
    )

    for lap_number in (4, 5):
        register_lap(
            race=race,
            kart_id=2,
            lap_number=lap_number,
            lap_time_ms=60_000 + lap_number,
            race_time_ms=lap_number * 60_000,
        )

    return race


def numeri(laps: list[Lap]) -> list[int]:
    return [lap.lap_number for lap in laps]


class TestFinestreSquadra(unittest.TestCase):

    def setUp(self):
        self.race = gara_con_cambio_kart()

    def finestra(self, window: AnalysisWindow, now_ms=None) -> list[int]:
        return numeri(
            get_laps_for_window(
                self.race.laps,
                self.race.stints,
                window,
                now_ms=now_ms,
            )
        )

    def test_ultimi_giri_attraversano_il_cambio_kart(self):
        self.assertEqual(
            self.finestra(ANALYSIS_WINDOWS["Ultimi 5"]),
            [1, 2, 3, 4, 5],
        )

    def test_stint_corrente_aperto(self):
        # Prima questo restituiva una lista vuota: lo stint aperto
        # non ha ancora end_lap.
        self.assertEqual(
            self.finestra(ANALYSIS_WINDOWS["Stint corrente"]),
            [4, 5],
        )

    def test_stint_selezionato(self):
        window = AnalysisWindow(
            window_type=AnalysisWindowType.STINT,
            value=1,
        )

        self.assertEqual(self.finestra(window), [1, 2, 3])

    def test_stint_inesistente(self):
        window = AnalysisWindow(
            window_type=AnalysisWindowType.STINT,
            value=9,
        )

        self.assertEqual(self.finestra(window), [])

    def test_ultimi_minuti_dall_ultimo_giro(self):
        # Ultimo giro a 5:00: la finestra copre (2:00, 5:00].
        window = AnalysisWindow(
            window_type=AnalysisWindowType.LAST_TIME,
            value=3 * 60_000,
        )

        self.assertEqual(self.finestra(window), [3, 4, 5])

    def test_ultimi_minuti_dal_tempo_attuale(self):
        # A 9:00 di gara, negli ultimi 5 minuti c'è solo il giro 5.
        self.assertEqual(
            self.finestra(
                ANALYSIS_WINDOWS["Ultimi 5 minuti"],
                now_ms=9 * 60_000,
            ),
            [5],
        )

    def test_analisi_con_ultimo_giro(self):
        analysis = analyze_window(
            self.race.laps,
            self.race.stints,
            ANALYSIS_WINDOWS["Ultimi 3"],
        )

        self.assertEqual(analysis.lap_count, 3)
        self.assertEqual(analysis.best_lap_ms, 60_003)
        self.assertEqual(analysis.last_lap_ms, 60_005)

    def test_tutte_le_finestre_del_menu(self):
        for label, window in ANALYSIS_WINDOWS.items():
            with self.subTest(finestra=label):
                self.assertTrue(self.finestra(window))


class TestCasiLimite(unittest.TestCase):

    def test_giri_senza_tempo_gara_esclusi(self):
        laps = [
            Lap(lap_number=1, lap_time_ms=60_000),
            Lap(lap_number=2, lap_time_ms=60_000, race_time_ms=120_000),
        ]

        self.assertEqual(
            numeri(get_laps_in_last(laps, duration_ms=600_000)),
            [2],
        )

    def test_nessun_giro(self):
        analysis = analyze_window(
            [],
            [],
            ANALYSIS_WINDOWS["Stint corrente"],
        )

        self.assertEqual(analysis.lap_count, 0)
        self.assertIsNone(analysis.last_lap_ms)

    def test_stint_corrente_durante_il_pit(self):
        """
        Pit non ancora confermato: nessuno stint aperto.

        Lo stint corrente resta l'ultimo concluso.
        """

        race = gara_con_cambio_kart()
        race.stints[-1].end_lap = 5

        self.assertEqual(
            get_current_stint(race.stints).stint_number,
            2,
        )


if __name__ == "__main__":
    unittest.main()
