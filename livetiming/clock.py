"""
Ricostruzione del tempo di gara.

Il modello di RaceEngineer registra ogni giro con il momento della
gara in cui è stato completato: da quel valore dipendono l'inizio e
la fine degli stint e quindi tutte le durate. Il feed però non invia
un tempo di gara: invia un cronometro che a seconda del circuito
conta in avanti oppure alla rovescia.

Qui il cronometro viene osservato, se ne deduce il verso e se ne
ricava un tempo di gara crescente e continuo.
"""

from typing import Optional

from livetiming.protocol import parse_time_to_ms


class ClockDirection:
    """Verso di scorrimento del cronometro."""

    UNKNOWN = "unknown"
    COUNTING_UP = "up"
    COUNTING_DOWN = "down"


# Oltre questo scarto fra due letture si assume un salto del
# cronometro (sessione ricaricata, non semplice scorrimento).
JUMP_THRESHOLD_MS = 5 * 60 * 1000

# Classi con cui il feed dichiara un cronometro che scorre da solo.
# Il valore è in millisecondi ("18203766"), in secondi se contiene un
# punto, e il client ufficiale lo fa avanzare dal momento in cui lo
# riceve (tzfjc() in javascript_live_timing.min.js). Il server lo
# rimanda ogni 30 secondi circa.
RUNNING_CLASSES = {
    "count": ClockDirection.COUNTING_UP,
    "countdown": ClockDirection.COUNTING_DOWN,
    "countdown_text": ClockDirection.COUNTING_DOWN,
}


def parse_clock_value(css_class: str, text: str) -> Optional[int]:
    """
    Converte il valore del cronometro in millisecondi.

    Con le classi di RUNNING_CLASSES il valore è numerico; con
    "countdown_text" è seguito da "_" e da un testo da mostrare.
    Qualunque altro formato si legge come tempo ("5:59:59").
    """

    if css_class in RUNNING_CLASSES:
        value = (text or "").strip()

        if css_class == "countdown_text":
            value = value.split("_", 1)[0]

        try:
            if "." in value:
                return round(float(value) * 1000)

            return int(value)

        except ValueError:
            pass

    return parse_time_to_ms(text)


class RaceClock:
    """
    Traduce il cronometro del feed in un tempo di gara.

    Il valore restituito è sempre crescente e in millisecondi, come
    richiesto da Lap.race_time_ms.
    """

    def __init__(self, total_duration_ms: Optional[int] = None):
        # Durata prevista della gara: se nota, permette di collocare
        # correttamente un conto alla rovescia anche agganciandosi a
        # gara iniziata.
        self.total_duration_ms = total_duration_ms

        self.direction = ClockDirection.UNKNOWN

        self._first_value_ms: Optional[int] = None
        self._last_value_ms: Optional[int] = None
        self._last_sample_at_ms: Optional[int] = None

        # Tempo di gara corrispondente all'ultima lettura.
        self._last_race_time_ms: Optional[int] = None

        self.is_running = False

    def update(
        self,
        css_class: str,
        text: str,
        now_ms: int,
    ) -> None:
        """Registra una lettura del cronometro."""

        value_ms = parse_clock_value(css_class, text)

        if value_ms is None:
            return

        # Verso dichiarato dal feed: il cronometro scorre da subito,
        # senza aspettare una seconda lettura.
        declared = RUNNING_CLASSES.get(css_class)

        if declared is not None:
            self.direction = declared
            self.is_running = True

        previous = self._last_value_ms

        if previous is not None:
            difference = value_ms - previous

            if abs(difference) > JUMP_THRESHOLD_MS:
                # Salto: si riparte da capo su questa lettura.
                self._first_value_ms = value_ms

            elif declared is not None:
                pass

            elif difference > 0:
                self.direction = ClockDirection.COUNTING_UP
                self.is_running = True

            elif difference < 0:
                self.direction = ClockDirection.COUNTING_DOWN
                self.is_running = True

            else:
                self.is_running = False

        if self._first_value_ms is None:
            self._first_value_ms = value_ms

        self._last_value_ms = value_ms
        self._last_sample_at_ms = now_ms
        self._last_race_time_ms = self._race_time_at_sample(value_ms)

    def _race_time_at_sample(self, value_ms: int) -> Optional[int]:
        """Converte una lettura nel tempo di gara corrispondente."""

        if self.direction == ClockDirection.COUNTING_UP:
            return value_ms

        if self.direction == ClockDirection.COUNTING_DOWN:

            # Con la durata nota il conto alla rovescia è assoluto.
            if self.total_duration_ms is not None:
                return self.total_duration_ms - value_ms

            # Altrimenti si misura dal momento dell'aggancio.
            if self._first_value_ms is not None:
                return self._first_value_ms - value_ms

        return None

    def race_time_ms(self, now_ms: int) -> Optional[int]:
        """
        Tempo di gara al momento indicato, in millisecondi.

        Fra una lettura e l'altra il valore viene interpolato con
        l'orologio locale, perché il cronometro del feed avanza al
        secondo mentre i giri arrivano in qualunque istante.
        """

        if (
            self._last_race_time_ms is None
            or self._last_sample_at_ms is None
        ):
            return None

        if not self.is_running:
            return self._last_race_time_ms

        elapsed_since_sample = now_ms - self._last_sample_at_ms

        if elapsed_since_sample < 0:
            elapsed_since_sample = 0

        return self._last_race_time_ms + elapsed_since_sample
