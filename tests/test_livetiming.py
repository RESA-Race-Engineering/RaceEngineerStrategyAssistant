"""
Prove del lettore di live timing.

Si eseguono senza dipendenze esterne:

    python -m unittest discover tests

I frammenti di griglia riproducono le tre forme osservate sui feed
reali di Apex, perché è lì che si nascondeva l'errore più insidioso.
"""

import tempfile
import unittest
from pathlib import Path

from livetiming.clock import ClockDirection, RaceClock
from livetiming.journal import FeedJournal, replay
from livetiming.protocol import (
    Crossing,
    GridReplaced,
    Sector,
    SessionMode,
    SessionReset,
    parse_payload,
    parse_time_to_ms,
)
from livetiming.reader import (
    KartNumberChanged,
    KartNumberMismatch,
    LapCompleted,
    PitIn,
    PitOut,
    TeamBound,
    TeamTracker,
)


HEADER = (
    '<tr data-id="r0" class="head" data-pos="0">'
    '<td data-id="c3" data-type="rk">Cla</td>'
    '<td data-id="c4" data-type="no">Kart</td>'
    '<td data-id="c5" data-type="dr">Pilota</td>'
    '<td data-id="c6" data-type="llp">Ultimo T.</td>'
    '<td data-id="c9" data-type="tlp">Giri</td></tr>'
)

# Forma osservata sul feed FIA: data-id completo sulla cella.
ROW_FULL_ID = (
    '<tr data-id="r1" data-pos="1">'
    '<td data-id="r1c3">1</td>'
    '<td data-id="r1c4">18</td>'
    '<td data-id="r1c5">Scuderia Dante</td>'
    '<td data-id="r1c6">53.200</td>'
    '<td data-id="r1c9">41</td></tr>'
)

# Forma osservata sulle colonne "rk" e "no": l'identificativo sta su
# un elemento annidato e la cella non ne ha alcuno.
ROW_NESTED_ID = (
    '<tr data-id="r1" data-pos="1">'
    '<td class="rk"><div><p data-id="r1c3">1</p></div></td>'
    '<td class="no"><div data-id="r1c4">18</div></td>'
    '<td data-id="r1c5">Scuderia Dante</td>'
    '<td data-id="r1c6">53.200</td>'
    '<td data-id="r1c9">41</td></tr>'
)

# Forma minima, senza identificativi: deve reggere comunque.
ROW_NO_ID = (
    '<tr data-id="r1" data-pos="1">'
    "<td>1</td><td>18</td><td>Scuderia Dante</td>"
    "<td>53.200</td><td>41</td></tr>"
)


def grid_payload(row: str) -> str:
    return "init|r|\ngrid||<tbody>" + HEADER + row + "</tbody>"


class TestParsingTempi(unittest.TestCase):

    def test_formati_accettati(self):
        self.assertEqual(parse_time_to_ms("53.200"), 53_200)
        self.assertEqual(parse_time_to_ms("1:03.421"), 63_421)
        self.assertEqual(parse_time_to_ms("1:02:03.456"), 3_723_456)

    def test_decimi_non_sono_millesimi(self):
        # "1.2" vale un secondo e due decimi, non un secondo e 2 ms.
        self.assertEqual(parse_time_to_ms("1.2"), 1_200)

    def test_testo_non_numerico(self):
        self.assertIsNone(parse_time_to_ms("Pilota"))
        self.assertIsNone(parse_time_to_ms(""))


class TestProtocollo(unittest.TestCase):

    def test_riconoscimento_messaggi(self):
        eventi = parse_payload("init|r|\nr12|*|53\nr12|*in|\nr12|#|3")

        self.assertIsInstance(eventi[0], SessionReset)
        self.assertEqual(eventi[0].mode, SessionMode.RACE)

        self.assertEqual(eventi[1].sector, Sector.FINISH_LINE)
        self.assertEqual(eventi[2].sector, Sector.PIT_IN)
        self.assertEqual(eventi[3].position, 3)

    def test_colonne_lette_dall_intestazione(self):
        evento = parse_payload(grid_payload(ROW_FULL_ID))[1]

        self.assertIsInstance(evento, GridReplaced)
        self.assertEqual(evento.columns["no"], "c4")
        self.assertEqual(evento.columns["llp"], "c6")

    def test_tutte_le_forme_di_cella(self):
        """
        Le righe reali usano tre forme diverse di identificativo.

        La lettura avviene per posizione, quindi il risultato non
        deve cambiare.
        """

        for nome, riga in (
            ("completo", ROW_FULL_ID),
            ("annidato", ROW_NESTED_ID),
            ("assente", ROW_NO_ID),
        ):
            with self.subTest(forma=nome):
                evento = parse_payload(grid_payload(riga))[1]
                celle = evento.rows["r1"].cells

                self.assertEqual(celle["c4"], "18")
                self.assertEqual(celle["c5"], "Scuderia Dante")
                self.assertEqual(celle["c9"], "41")


class TestAggancioSquadra(unittest.TestCase):

    def nuovo_lettore(self, riga=ROW_FULL_ID):
        tracker = TeamTracker(
            team_name="Scuderia Dante",
            race_duration_ms=6 * 60 * 60 * 1000,
        )

        eventi = tracker.process(grid_payload(riga))

        return tracker, eventi

    def test_aggancio_per_nome(self):
        tracker, eventi = self.nuovo_lettore()

        agganci = [e for e in eventi if isinstance(e, TeamBound)]

        self.assertEqual(len(agganci), 1)
        self.assertEqual(agganci[0].row_id, "r1")
        self.assertEqual(agganci[0].kart_number, "18")

    def test_giro_completato(self):
        tracker, _ = self.nuovo_lettore()

        eventi = tracker.process("r1c6|nb|52.980\nr1c9||42\nr1|*|53")
        giri = [e for e in eventi if isinstance(e, LapCompleted)]

        self.assertEqual(len(giri), 1)
        self.assertEqual(giri[0].lap_number, 42)
        self.assertEqual(giri[0].lap_time_ms, 52_980)

    def test_cambio_kart_al_pit(self):
        """
        Al pit la squadra cambia kart: si segue la riga, non il numero.
        """

        tracker, _ = self.nuovo_lettore()
        tracker.set_operator_kart_number("18")

        tracker.process("r1|*in|")
        eventi = tracker.process("r1c4||23\nr1|*out|8000")

        cambi = [e for e in eventi if isinstance(e, KartNumberChanged)]
        allarmi = [e for e in eventi if isinstance(e, KartNumberMismatch)]

        self.assertEqual(cambi[0].previous, "18")
        self.assertEqual(cambi[0].current, "23")

        # L'operatore non ha ancora aggiornato la GUI: deve saperlo.
        self.assertEqual(allarmi[0].operator_value, "18")
        self.assertEqual(allarmi[0].feed_value, "23")

        # La riga seguita non cambia.
        self.assertEqual(tracker.state.row_id, "r1")

    def test_numero_kart_corretto_non_allarma(self):
        tracker, _ = self.nuovo_lettore()

        self.assertEqual(tracker.set_operator_kart_number("18"), [])

    def test_eventi_di_pit(self):
        tracker, _ = self.nuovo_lettore()

        entrata = tracker.process("r1|*in|")
        uscita = tracker.process("r1|*out|8000")

        self.assertTrue(any(isinstance(e, PitIn) for e in entrata))
        self.assertTrue(any(isinstance(e, PitOut) for e in uscita))

    def test_squadra_assente(self):
        tracker = TeamTracker(team_name="Squadra Inesistente")
        eventi = tracker.process(grid_payload(ROW_FULL_ID))

        self.assertFalse([e for e in eventi if isinstance(e, TeamBound)])
        self.assertIsNone(tracker.state.row_id)


class TestCronometro(unittest.TestCase):

    def campiona(self, clock, classe, valori, inizio=1_000_000):
        istante = inizio

        for valore in valori:
            clock.update(classe, valore, istante)
            istante += 1000

        return istante

    def test_conto_alla_rovescia_con_durata_nota(self):
        clock = RaceClock(total_duration_ms=6 * 60 * 60 * 1000)
        istante = self.campiona(
            clock,
            "countdown",
            ["05:59:00", "05:58:59", "05:58:58"],
        )

        self.assertEqual(clock.direction, ClockDirection.COUNTING_DOWN)

        # 6 ore meno 5h58m58s fa 62 secondi, più l'interpolazione.
        self.assertEqual(clock.race_time_ms(istante), 63_000)

    def test_conto_in_avanti(self):
        clock = RaceClock()
        istante = self.campiona(
            clock,
            "text",
            ["02:13:05", "02:13:06", "02:13:07"],
        )

        self.assertEqual(clock.direction, ClockDirection.COUNTING_UP)
        self.assertEqual(clock.race_time_ms(istante), 7_988_000)

    def test_cronometro_fermo_non_avanza(self):
        clock = RaceClock()
        istante = self.campiona(
            clock,
            "text",
            ["01:00:00", "01:00:01", "01:00:01", "01:00:01"],
        )

        self.assertFalse(clock.is_running)

        fermo = clock.race_time_ms(istante)

        self.assertEqual(clock.race_time_ms(istante + 30_000), fermo)

    def test_nessuna_lettura(self):
        self.assertIsNone(RaceClock().race_time_ms(1_000_000))


class TestRegistro(unittest.TestCase):

    def test_scrittura_e_rilettura(self):
        with tempfile.TemporaryDirectory() as cartella:
            percorso = Path(cartella) / "gara.jsonl"

            with FeedJournal(percorso) as registro:
                registro.append("init|r|")
                registro.note("riconnessione")
                registro.append("r1|*|53")

            letti = list(replay(percorso))

            self.assertEqual([p for _, p in letti], ["init|r|", "r1|*|53"])

    def test_riga_troncata_ignorata(self):
        """Un arresto improvviso lascia l'ultima riga incompleta."""

        with tempfile.TemporaryDirectory() as cartella:
            percorso = Path(cartella) / "gara.jsonl"

            with FeedJournal(percorso) as registro:
                registro.append("init|r|")

            with percorso.open("a", encoding="utf-8") as handle:
                handle.write('{"t": 1, "p": "r1c6|nb|52')

            self.assertEqual(len(list(replay(percorso))), 1)


if __name__ == "__main__":
    unittest.main()
