"""
Collegamento resistente al feed Apex.

Una gara di endurance dura ore e il collegamento cade: il client
ufficiale si ricollega da solo e qui si fa lo stesso. Oltre alla
caduta esplicita si sorveglia il silenzio, perché una WebSocket può
restare aperta senza più trasportare nulla.

Alla riconnessione il server rinvia lo stato completo, quindi il
lettore si riaggancia da solo: non si perde l'aggancio alla squadra.
"""

from dataclasses import dataclass
import time
from typing import Iterator, Optional

from livetiming.client import LiveTimingSocket, TrackConfig


# Il server non ha un battito regolare e durante una pausa può
# tacere per minuti: il ping lo mandiamo noi a intervalli fissi e
# consideriamo morto il collegamento se non torna nulla.
DEFAULT_PING_EVERY_S = 15
DEFAULT_SILENCE_LIMIT_S = 45

DEFAULT_FIRST_BACKOFF_S = 1
DEFAULT_MAX_BACKOFF_S = 30


@dataclass
class Connected:
    """Collegamento stabilito."""

    attempt: int


@dataclass
class Disconnected:
    """Collegamento caduto: seguirà un nuovo tentativo."""

    reason: str
    retry_in_s: float


@dataclass
class Payload:
    """Dati ricevuti dal feed."""

    text: str


class LiveTimingFeed:
    """
    Fornisce i payload del feed ricollegandosi da sola.

    Non interpreta i dati: si limita a tenere vivo il collegamento e
    a dichiarare quando cade e quando torna.
    """

    def __init__(
        self,
        config: TrackConfig,
        silence_limit_s: int = DEFAULT_SILENCE_LIMIT_S,
        max_backoff_s: int = DEFAULT_MAX_BACKOFF_S,
        ping_every_s: int = DEFAULT_PING_EVERY_S,
    ):
        self.config = config
        self.silence_limit_s = silence_limit_s
        self.ping_every_s = ping_every_s
        self.max_backoff_s = max_backoff_s

        self.attempts = 0
        self.last_payload_at: Optional[float] = None

    def run(self, timeout_s: Optional[float] = None) -> Iterator:
        """
        Restituisce gli eventi del collegamento e i payload.

        Continua finché non scade il tempo indicato; senza tempo
        indicato prosegue fino all'interruzione del chiamante.
        """

        deadline = None if timeout_s is None else time.time() + timeout_s
        backoff = DEFAULT_FIRST_BACKOFF_S

        while deadline is None or time.time() < deadline:

            socket_client = LiveTimingSocket(self.config)
            self.attempts += 1

            try:
                socket_client.connect()

            except Exception as error:
                wait = min(backoff, self.max_backoff_s)

                yield Disconnected(
                    reason=f"collegamento non riuscito: {error}",
                    retry_in_s=wait,
                )

                if not self._wait(wait, deadline):
                    return

                backoff = min(backoff * 2, self.max_backoff_s)
                continue

            # Il collegamento è riuscito: si riparte da un'attesa breve.
            backoff = DEFAULT_FIRST_BACKOFF_S

            yield Connected(attempt=self.attempts)

            # yield from consegna i payload e restituisce il motivo
            # della caduta dichiarato da _pump().
            reason = yield from self._pump(socket_client, deadline)

            socket_client.close()

            if reason is None:
                return

            wait = DEFAULT_FIRST_BACKOFF_S

            yield Disconnected(
                reason=reason,
                retry_in_s=wait,
            )

            if not self._wait(wait, deadline):
                return

    def _pump(
        self,
        socket_client: LiveTimingSocket,
        deadline: Optional[float],
    ) -> Iterator:
        """
        Consuma un collegamento finché regge.

        Cede i payload ricevuti e restituisce il motivo della caduta,
        oppure None se il tempo a disposizione è finito.
        """

        self.last_payload_at = time.time()
        last_ping_at = time.time()

        while deadline is None or time.time() < deadline:

            if time.time() - last_ping_at >= self.ping_every_s:
                if not socket_client.send_ping():
                    return "invio del ping non riuscito"

                last_ping_at = time.time()

            batch = socket_client.poll()

            if batch is None:
                return "collegamento chiuso dal server"

            now = time.time()

            if batch:
                self.last_payload_at = now

                for text in batch:
                    yield Payload(text=text)

            # Si sorveglia qualunque traffico, ping inclusi.
            silence = now - (socket_client.last_activity_at or now)

            if silence > self.silence_limit_s:
                return f"nessun segnale da {int(silence)} secondi"

        return None

    @staticmethod
    def _wait(seconds: float, deadline: Optional[float]) -> bool:
        """Attende, rispettando la scadenza complessiva."""

        target = time.time() + seconds

        if deadline is not None:
            target = min(target, deadline)

        while time.time() < target:
            time.sleep(0.2)

        return deadline is None or time.time() < deadline
