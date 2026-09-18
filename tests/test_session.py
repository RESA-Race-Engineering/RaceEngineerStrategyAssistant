"""
Prove della sessione di gara: l'adapter fra feed e motore di gara.

Una gara simulata di un'ora passa dalla sessione come passerebbe in
diretta, mentre un "operatore" conferma i pit in momenti diversi: alla
fine giri e stint devono essere gli stessi in ogni caso.
"""

import unittest

from app.session import RaceSession
from core.models import RaceConfig
from core.rules import RuleStatus, validate_race
from livetiming.simulate import RaceSimulator


TEAM = "Scuderia Dante"
DRIVERS = ["Marco", "Luca", "Andrea"]
HOUR_MS = 60 * 60 * 1000
START_MS = 1_800_000_000_000

CONFIG = RaceConfig(
    duration_ms=HOUR_MS,
    drivers_per_team=3,
    min_stints=3,
    min_pit_stops=2,
)


def run_race(operator=None, auto_pit=False) -> RaceSession:
    """Fa passare una gara simulata di un'ora dalla sessione."""

    simulator = RaceSimulator(
        team_name=TEAM,
        team_count=6,
        duration_ms=HOUR_MS,
        min_pit_stops=2,
        seed=3,
    )

    session = RaceSession.create(
        team_name=TEAM,
        driver_names=DRIVERS,
        config=CONFIG,
        auto_pit=auto_pit,
    )

    for race_time_ms, payload in simulator.payloads():
        session.process_payload(
            payload,
            received_at_ms=START_MS + race_time_ms,
        )

        if operator is not None:
            operator(session)

    return session


def start_when_bound(session: RaceSession) -> None:
    """L'operatore avvia la gara appena la squadra è agganciata."""

    state = session.tracker.state

    if not session.race.stints and state.row_id and state.kart_number:
        session.start_race(
            driver_id=session.race.drivers[0].id,
            kart_number=state.kart_number,
        )


def stint_shape(session: RaceSession) -> list:
    return [
        (stint.stint_number, stint.driver_id, stint.start_lap, stint.end_lap)
        for stint in session.race.stints
    ]


def lap_shape(session: RaceSession) -> list:
    return [
        (lap.lap_number, lap.lap_time_ms, lap.driver_id)
        for lap in session.race.laps
    ]


def alerts(session: RaceSession, level: str) -> list[str]:
    return [
        alert.message
        for alert in session.alerts
        if alert.level == level
    ]


class TestGaraSimulata(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.auto = run_race(auto_pit=True)

    def test_gara_completa_e_regolare(self):
        race = self.auto.race

        self.assertEqual(len(race.stints), 3)
        self.assertEqual(len(race.pit_stops), 2)

        violations = [
            result.message
            for result in validate_race(race)
            if result.status == RuleStatus.VIOLATION
        ]

        self.assertEqual(violations, [])
        self.assertEqual(alerts(self.auto, "error"), [])

        # Tempi del feed coerenti con i passaggi: nessun allarme.
        self.assertFalse(
            [m for m in alerts(self.auto, "warning") if "sfasati" in m]
        )

    def test_giri_senza_buchi(self):
        numbers = [lap.lap_number for lap in self.auto.race.laps]

        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_conferma_all_uscita_dai_box(self):
        def operator(session):
            start_when_bound(session)
            pending = session.pending_pit

            if pending is not None and pending.out_race_time_ms is not None:
                session.confirm_pit(
                    kart_number=session.tracker.state.kart_number,
                    driver_id=session.next_driver_id(),
                )

        manual = run_race(operator)

        self.assertEqual(stint_shape(manual), stint_shape(self.auto))
        self.assertEqual(lap_shape(manual), lap_shape(self.auto))

        # Durata del pit presa dalla misura del feed.
        self.assertTrue(all(pit.duration_ms for pit in manual.race.pit_stops))

    def test_conferma_mentre_il_kart_e_ai_box(self):
        """
        L'operatore conferma prima dell'uscita, con il kart che vede.

        Qui il numero è volutamente diverso da quello che il feed
        mostrerà all'uscita: deve arrivare un avviso, non una
        correzione, e l'uscita non deve aprire un altro pit.
        """

        def operator(session):
            start_when_bound(session)
            pending = session.pending_pit

            if pending is not None and pending.out_race_time_ms is None:
                session.confirm_pit(
                    kart_number=99,
                    driver_id=session.next_driver_id(),
                    duration_ms=95_000,
                )

        manual = run_race(operator)

        self.assertEqual(stint_shape(manual), stint_shape(self.auto))
        self.assertEqual(lap_shape(manual), lap_shape(self.auto))
        self.assertIsNone(manual.pending_pit)

        self.assertTrue(
            [m for m in alerts(manual, "warning") if "Kart diverso" in m]
        )

        # Il kart resta quello dichiarato dall'operatore.
        self.assertEqual(manual.current_kart().number, 99)

    def test_conferma_in_ritardo(self):
        """Un giro arriva prima della conferma: resta in sospeso."""

        buffered = []

        def operator(session):
            start_when_bound(session)

            if session.pending_pit is not None and session.pending_laps:
                buffered.append(len(session.pending_laps))

                session.confirm_pit(
                    kart_number=session.tracker.state.kart_number,
                    driver_id=session.next_driver_id(),
                )

        manual = run_race(operator)

        self.assertTrue(buffered)
        self.assertEqual(stint_shape(manual), stint_shape(self.auto))
        self.assertEqual(lap_shape(manual), lap_shape(self.auto))

    def test_avvio_in_ritardo(self):
        """La gara parte prima che l'operatore la avvii."""

        def operator(session):
            state = session.tracker.state

            if not session.race.stints and len(session.pending_laps) >= 3:
                session.start_race(
                    driver_id=session.race.drivers[0].id,
                    kart_number=state.kart_number,
                )

            pending = session.pending_pit

            if pending is not None and pending.out_race_time_ms is not None:
                session.confirm_pit(
                    kart_number=state.kart_number,
                    driver_id=session.next_driver_id(),
                )

        manual = run_race(operator)

        self.assertEqual(lap_shape(manual), lap_shape(self.auto))

    def test_falso_allarme(self):
        """Pit annullato: i giri in sospeso vanno allo stint in corso."""

        discarded = []

        def operator(session):
            start_when_bound(session)

            if (
                session.pending_pit is not None
                and session.pending_laps
                and not discarded
            ):
                discarded.append(session.pending_laps[0].lap_number)
                session.discard_pit()

        manual = run_race(operator)

        first_stint = manual.race.stints[0]

        self.assertIsNone(first_stint.end_lap)
        self.assertIn(
            discarded[0],
            [lap.lap_number for lap in manual.race.laps],
        )


class TestControlloTempiGiro(unittest.TestCase):
    """Il tempo del feed deve tornare con il tempo fra i passaggi."""

    GRID = (
        "init|r|\ngrid||<tbody>"
        '<tr data-id="r0" class="head" data-pos="0">'
        '<td data-id="c3" data-type="rk">Cla</td>'
        '<td data-id="c4" data-type="no">Kart</td>'
        '<td data-id="c5" data-type="dr">Squadra</td>'
        '<td data-id="c6" data-type="llp">Ultimo T.</td>'
        '<td data-id="c9" data-type="tlp">Giri</td></tr>'
        '<tr data-id="r1" data-pos="1">'
        "<td>1</td><td>18</td><td>Scuderia Dante</td>"
        "<td></td><td>0</td></tr></tbody>"
    )

    def setUp(self):
        self.session = RaceSession.create(
            team_name=TEAM,
            driver_names=DRIVERS,
        )

        self.session.process_payload(self.GRID, received_at_ms=0)
        self.session.start_race(driver_id=1, kart_number=18)

    def cross(self, lap_number, lap_time, at_ms):
        self.session.process_payload(
            f"r1c6||{lap_time}\nr1c9||{lap_number}\nr1|*|",
            received_at_ms=at_ms,
        )

    def warnings(self):
        return [m for m in alerts(self.session, "warning") if "sfasati" in m]

    def test_tempi_coerenti(self):
        self.cross(1, "55.000", 55_000)
        self.cross(2, "53.000", 108_000)
        self.cross(3, "1:00.000", 168_000)

        self.assertEqual(self.warnings(), [])

    def test_tempo_del_giro_prima(self):
        """Se "Ultimo T." arrivasse in ritardo, il giro 3 avrebbe 53.000."""

        self.cross(1, "55.000", 55_000)
        self.cross(2, "53.000", 108_000)
        self.cross(3, "53.000", 168_000)

        self.assertEqual(len(self.warnings()), 1)


if __name__ == "__main__":
    unittest.main()
