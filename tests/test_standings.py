"""
Prove della classifica completa.

I giri dei concorrenti si analizzano con le stesse finestre della
nostra squadra, quindi le prove passano anche da core.analytics.
"""

import unittest

from core.analytics import (
    ANALYSIS_WINDOWS,
    analyze_window,
    get_laps_for_window,
)
from livetiming.standings import Standings, parse_gap_ms


HEADER = (
    '<tr data-id="r0" class="head" data-pos="0">'
    '<td data-id="c3" data-type="rk">Cla</td>'
    '<td data-id="c4" data-type="no">Kart</td>'
    '<td data-id="c5" data-type="dr">Squadra</td>'
    '<td data-id="c6" data-type="llp">Ultimo T.</td>'
    '<td data-id="c7" data-type="gap">Distacco</td>'
    '<td data-id="c8" data-type="pit">Pit</td>'
    '<td data-id="c9" data-type="tlp">Giri</td></tr>'
)


def riga(row_id, pos, kart, squadra, ultimo, distacco, giri):
    return (
        f'<tr data-id="{row_id}" data-pos="{pos}">'
        f"<td>{pos}</td><td>{kart}</td><td>{squadra}</td>"
        f"<td>{ultimo}</td><td>{distacco}</td><td>0</td>"
        f"<td>{giri}</td></tr>"
    )


GRID = (
    "init|r|\ngrid||<tbody>"
    + HEADER
    + riga("r1", 1, 18, "Scuderia Dante", "53.200", "", 40)
    + riga("r2", 2, 7, "Kart Rossi", "53.900", "+4.500", 40)
    + riga("r3", 3, 23, "Team Verdi", "54.100", "+6.000", 40)
    + riga("r4", 4, 11, "Lenti", "58.000", "1 Giro", 39)
    + "</tbody>"
)


def giro(standings, row_id, numero, tempo):
    """Il concorrente passa sul traguardo."""

    standings.process(
        f"{row_id}c6||{tempo}\n{row_id}c9||{numero}\n{row_id}|*|"
    )


class TestClassifica(unittest.TestCase):

    def setUp(self):
        self.standings = Standings()
        self.standings.process(GRID)

    def test_ordine_e_colonne(self):
        classifica = self.standings.competitors()

        self.assertEqual(
            [c.row_id for c in classifica],
            ["r1", "r2", "r3", "r4"],
        )

        self.assertEqual(classifica[1].kart_number, "7")
        self.assertEqual(classifica[1].team_label, "Kart Rossi")
        self.assertEqual(classifica[1].last_lap_ms, 53_900)

    def test_distacchi_e_intervalli(self):
        rossi = self.standings.get("r2")
        verdi = self.standings.get("r3")
        lenti = self.standings.get("r4")

        self.assertEqual(rossi.gap_ms, 4_500)
        self.assertEqual(rossi.interval_ms, 4_500)
        self.assertEqual(verdi.interval_ms, 1_500)

        # Un doppiato non ha un distacco in tempo.
        self.assertIsNone(lenti.gap_ms)
        self.assertIsNone(lenti.interval_ms)

    def test_cambio_di_posizione(self):
        self.standings.process("r3c3||2\nr2c3||3")

        self.assertEqual(
            [c.row_id for c in self.standings.competitors()],
            ["r1", "r3", "r2", "r4"],
        )

    def test_giri_registrati(self):
        giro(self.standings, "r2", 41, "53.500")
        giro(self.standings, "r2", 42, "53.400")

        laps = self.standings.get("r2").laps

        self.assertEqual([lap.lap_number for lap in laps], [41, 42])
        self.assertEqual(laps[-1].lap_time_ms, 53_400)

    def test_passaggio_ripetuto_non_duplica(self):
        giro(self.standings, "r2", 41, "53.500")
        self.standings.process("r2|*|")

        self.assertEqual(len(self.standings.get("r2").laps), 1)

    def test_stint_dopo_il_pit(self):
        """
        Il giro prima del pit resta nello stint vecchio, il primo
        giro dopo l'uscita apre quello nuovo.
        """

        giro(self.standings, "r2", 41, "53.500")
        giro(self.standings, "r2", 42, "53.400")

        self.standings.process("r2|*in|")
        self.assertTrue(self.standings.get("r2").in_pit)

        self.standings.process("r2|*out|")
        giro(self.standings, "r2", 43, "58.000")
        giro(self.standings, "r2", 44, "53.100")

        rossi = self.standings.get("r2")

        self.assertFalse(rossi.in_pit)
        self.assertEqual(len(rossi.stints), 2)
        self.assertEqual(rossi.stints[0].end_lap, 42)

        corrente = get_laps_for_window(
            rossi.laps,
            rossi.stints,
            ANALYSIS_WINDOWS["Stint corrente"],
        )

        self.assertEqual([lap.lap_number for lap in corrente], [43, 44])

    def test_stessa_analisi_della_squadra(self):
        giro(self.standings, "r3", 41, "54.000")
        giro(self.standings, "r3", 42, "54.200")

        verdi = self.standings.get("r3")

        analysis = analyze_window(
            verdi.laps,
            verdi.stints,
            ANALYSIS_WINDOWS["Ultimi 5"],
        )

        self.assertEqual(analysis.lap_count, 2)
        self.assertEqual(analysis.best_lap_ms, 54_000)
        self.assertEqual(analysis.last_lap_ms, 54_200)

    def test_riconnessione_conserva_la_storia(self):
        giro(self.standings, "r2", 41, "53.500")

        # Alla riconnessione il server rinvia sessione e griglia.
        self.standings.process(GRID)
        giro(self.standings, "r2", 42, "53.400")

        laps = self.standings.get("r2").laps

        self.assertEqual([lap.lap_number for lap in laps], [41, 42])

    def test_sessione_nuova_azzera_la_storia(self):
        giro(self.standings, "r2", 41, "53.500")
        giro(self.standings, "r2", 1, "55.000")

        laps = self.standings.get("r2").laps

        self.assertEqual([lap.lap_number for lap in laps], [1])


class TestColonnaIntervallo(unittest.TestCase):
    """Su circuito-di-pomposa il feed pubblica anche l'intervallo."""

    def test_intervallo_dal_feed(self):
        header = HEADER.replace(
            '<td data-id="c8" data-type="pit">Pit</td>',
            '<td data-id="c8" data-type="int">Interv.</td>',
        )

        standings = Standings()
        standings.process(
            "init|r|\ngrid||<tbody>"
            + header
            + riga("r1", 1, 18, "Scuderia Dante", "53.200", "", 40)
            + riga("r2", 2, 7, "Kart Rossi", "53.900", "+4.500", 40)
            + "</tbody>"
        )

        # riga() scrive "0" nella colonna ex pit: è l'intervallo.
        standings.process("r2c8||+1.250")

        self.assertEqual(standings.get("r2").interval_ms, 1_250)


class TestDistacchi(unittest.TestCase):

    def test_formati(self):
        self.assertEqual(parse_gap_ms("+12.345"), 12_345)
        self.assertEqual(parse_gap_ms("1:02.500"), 62_500)
        self.assertIsNone(parse_gap_ms("1 Giro"))
        self.assertIsNone(parse_gap_ms(""))


if __name__ == "__main__":
    unittest.main()
