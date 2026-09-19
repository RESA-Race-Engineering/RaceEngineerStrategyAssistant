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


class TestPitKartAndGo(unittest.TestCase):
    """
    Sequenza di un pit vera, registrata a Kart&Go il 19/09/2026.

    L'uscita dai box fa salire il conto dei giri (con il tempo di
    sosta come "Ultimo T.") senza passare dal traguardo: il primo giro
    registrato dello stint nuovo non è start_lap + 1.
    """

    GRID = (
        f"init|p|\ndyn1|countdown|{HOUR_MS}\ngrid||<tbody>"
        '<tr data-id="r0" class="head" data-pos="0">'
        '<td data-id="c2" data-type="sta"></td>'
        '<td data-id="c3" data-type="rk">Cla</td>'
        '<td data-id="c4" data-type="no">Kart</td>'
        '<td data-id="c5" data-type="dr">Pilota</td>'
        '<td data-id="c6" data-type="llp">Ultimo T.</td>'
        '<td data-id="c9" data-type="tlp">Giri</td>'
        '<td data-id="c10" data-type="">Tempo Pit</td>'
        '<td data-id="c12" data-type="pit">Pit stop</td></tr>'
        '<tr data-id="r7" data-pos="1">'
        '<td data-id="r7c2" class="in"></td>'
        '<td class="rk"><div><p data-id="r7c3" class="">1</p></div></td>'
        '<td class="no"><div data-id="r7c4" class="no1">11</div></td>'
        '<td data-id="r7c5" class="dr">Scuderia Dante</td>'
        '<td data-id="r7c6" class="ti">36.886</td>'
        '<td data-id="r7c9" class="in">4</td>'
        '<td data-id="r7c10" class="to">00:00</td>'
        '<td data-id="r7c12" class="in"></td></tr></tbody>'
    )

    # (istante, payload); il valore di "*" è il miglior giro, non
    # il giro appena fatto.
    PAYLOADS = [
        (37_000, "r7c6|tn|36.831\nr7c9|in|5\nr7|*|36831|"),
        (74_000, "r7c6|tn|36.958\nr7c9|in|6\nr7|*|36831|"),
        (110_000, "r7c2|si|\nr7c12|in|1\nr7|*in|0"),
        (124_000, "r7c4|no1|7"),
        (
            141_000,
            "r7c2|so|\nr7c6|tn|31.342\nr7c9|in|7\n"
            "r7c10|to|00:31\nr7|*out|0",
        ),
        (182_000, "r7c2|sr|\nr7c6|tn|40.565\nr7c9|in|8\nr7|*|36831|"),
        (219_000, "r7c6|tn|37.159\nr7c9|in|9\nr7|*|36831|"),
    ]

    def run_pit(self, auto_pit=False, confirm_at=None, kart_number=None):
        """
        confirm_at è l'istante dopo il quale l'operatore conferma il
        pit: 110_000 appena entrato ai box (il feed ha ancora il kart
        vecchio), 124_000 dopo il cambio kart, 182_000 dopo l'uscita.
        """

        session = RaceSession.create(
            team_name=TEAM,
            driver_names=DRIVERS,
            config=CONFIG,
            auto_pit=auto_pit,
        )

        session.process_payload(self.GRID, received_at_ms=START_MS)

        # Con auto_pit la gara parte da sola all'aggancio; a mano
        # il kart di partenza si prende dal feed.
        if not session.race.stints:
            session.start_race(driver_id=1)

        for at_ms, payload in self.PAYLOADS:
            session.process_payload(
                payload,
                received_at_ms=START_MS + at_ms,
            )

            if at_ms == confirm_at:
                session.confirm_pit(
                    driver_id=2,
                    kart_number=kart_number,
                )

        return session

    def check(self, session):
        self.assertEqual(
            [(lap.lap_number, lap.lap_time_ms) for lap in session.race.laps],
            [(5, 36831), (6, 36958), (8, 40565), (9, 37159)],
        )

        first, second = session.race.stints

        self.assertEqual(session.kart_number(first.kart_id), 11)
        self.assertEqual(session.kart_number(second.kart_id), 7)

        self.assertEqual(second.start_lap, 6)
        self.assertEqual(second.start_time_ms, 141_000)

        self.assertEqual(session.race.pit_stops[0].duration_ms, 31_000)
        self.assertIsNone(session.pending_pit)

    def test_kart_dal_feed_confermando_appena_entrato(self):
        self.check(self.run_pit(confirm_at=110_000))

    def test_kart_dal_feed_confermando_dopo_il_cambio(self):
        self.check(self.run_pit(confirm_at=124_000))

    def test_kart_dal_feed_confermando_dopo_l_uscita(self):
        self.check(self.run_pit(confirm_at=182_000))

    def test_kart_a_mano_mentre_il_kart_e_ai_box(self):
        self.check(self.run_pit(confirm_at=124_000, kart_number=7))

    def test_conferma_all_uscita_dai_box(self):
        self.check(self.run_pit(auto_pit=True))



class TestAvvioAutomatico(unittest.TestCase):
    """La gara parte da sola, con kart, giro e tempo presi dal feed."""

    SIX_HOURS_MS = 6 * HOUR_MS

    def grid(self, title, clock, laps="", pits="", on_track="0:00", kart="18"):
        return (
            f"init|p|\ntitle2||{title}\ndyn1|{clock}\ngrid||<tbody>"
            '<tr data-id="r0" class="head" data-pos="0">'
            '<td data-id="c3" data-type="rk">Cla</td>'
            '<td data-id="c4" data-type="no">Kart</td>'
            '<td data-id="c5" data-type="dr">Pilota</td>'
            '<td data-id="c6" data-type="llp">Ultimo T.</td>'
            '<td data-id="c9" data-type="tlp">Giri</td>'
            '<td data-id="c11" data-type="otr">In pista</td>'
            '<td data-id="c12" data-type="pit">Pit stop</td></tr>'
            '<tr data-id="r1" data-pos="1">'
            f'<td data-id="r1c3">1</td><td data-id="r1c4">{kart}</td>'
            f'<td data-id="r1c5">{TEAM}</td><td data-id="r1c6">36.500</td>'
            f'<td data-id="r1c9">{laps}</td><td data-id="r1c11">{on_track}</td>'
            f'<td data-id="r1c12">{pits}</td></tr></tbody>'
        )

    def session(self, start_driver=""):
        session = RaceSession.create(
            team_name=TEAM,
            driver_names=DRIVERS,
            config=RaceConfig(duration_ms=self.SIX_HOURS_MS),
        )

        session.enable_auto_start(start_driver)

        return session

    def feed(self, session, payload, at_ms):
        session.process_payload(
            payload,
            received_at_ms=START_MS + at_ms,
        )

    def lap(self, session, number, at_ms):
        self.feed(
            session,
            f"r1c6||36.500\nr1c9||{number}\nr1|*|36500|",
            at_ms,
        )

    def test_prove_poi_partenza(self):
        session = self.session(start_driver="luca")

        # Prove: il cronometro corre ma la gara non parte, e i giri
        # delle prove non finiscono nella gara.
        self.feed(session, self.grid("Prove", "countdown|1800000", laps="3"), 0)
        self.lap(session, 4, 36_500)
        self.assertEqual(session.race.stints, [])

        # Sessione di gara ferma in griglia: si aspetta il via.
        start_ms = 600_000
        self.feed(session, self.grid("Gara", "text|06:00:00"), start_ms)
        self.assertEqual(session.race.stints, [])

        # Via.
        self.feed(session, f"dyn1|countdown|{self.SIX_HOURS_MS}", start_ms + 1_000)

        (stint,) = session.race.stints
        self.assertEqual(session.current_driver().name, "Luca")
        self.assertEqual(session.kart_number(stint.kart_id), 18)
        self.assertEqual((stint.start_lap, stint.start_time_ms), (0, 0))

        self.lap(session, 1, start_ms + 40_000)
        self.lap(session, 2, start_ms + 76_500)

        self.assertEqual(
            [lap.lap_number for lap in session.race.laps],
            [1, 2],
        )

    def test_gui_aperta_a_gara_iniziata_senza_pit(self):
        session = self.session()

        remaining_ms = 4 * HOUR_MS
        self.feed(session, self.grid("Gara", f"countdown|{remaining_ms}", laps="190", on_track="2:00"), 0)

        (stint,) = session.race.stints
        self.assertEqual(session.current_driver().name, DRIVERS[0])
        self.assertEqual((stint.start_lap, stint.start_time_ms), (0, 0))

        self.lap(session, 191, 36_500)
        self.assertEqual(session.race.laps[0].race_time_ms, 2 * HOUR_MS + 36_500)

    def test_gui_aperta_a_gara_iniziata_dopo_i_pit(self):
        session = self.session()

        remaining_ms = 4 * HOUR_MS
        self.feed(
            session,
            self.grid("Gara", f"countdown|{remaining_ms}", laps="190", pits="3", on_track="0:12"),
            0,
        )

        (stint,) = session.race.stints
        self.assertEqual(stint.start_lap, 190)
        self.assertEqual(stint.start_time_ms, 2 * HOUR_MS - 12 * 60_000)

    def test_gui_aperta_con_il_kart_ai_box(self):
        session = self.session()

        remaining_ms = 4 * HOUR_MS
        self.feed(
            session,
            self.grid("Gara", f"countdown|{remaining_ms}", laps="190", pits="3", on_track="12."),
            0,
        )
        self.assertEqual(session.race.stints, [])

        # Uscita dai box con il kart nuovo: lo stint parte adesso.
        self.feed(session, "r1c4||7\nr1c11||0:00\nr1|*out|0", 20_000)

        (stint,) = session.race.stints
        self.assertEqual(session.kart_number(stint.kart_id), 7)
        self.assertEqual(stint.start_time_ms, 2 * HOUR_MS + 20_000)
        self.assertIsNone(session.pending_pit)

    def test_pilota_di_partenza_sconosciuto(self):
        with self.assertRaises(ValueError):
            self.session(start_driver="Nessuno")

if __name__ == "__main__":
    unittest.main()
