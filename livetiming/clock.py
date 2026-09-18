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

        value_ms = parse_time_to_ms(text)

        if value_ms is None:
            return

        # La classe dichiarata dal feed è solo un indizio iniziale:
        # il verso vero si deduce confrontando le letture.
        if (
            self.direction == ClockDirection.UNKNOWN
            and "countdown" in (css_class or "")
        ):
            self.direction = ClockDirection.COUNTING_DOWN

        previous = self._last_value_ms

        if previous is not None:
            difference = value_ms - previous

            if abs(difference) > JUMP_THRESHOLD_MS:
                # Salto: si riparte da capo su questa lettura.
                self._first_value_ms = value_ms

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
