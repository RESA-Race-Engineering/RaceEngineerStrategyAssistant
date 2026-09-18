"""
Sorgenti dei dati per la sessione: feed dal vivo o registro.

Ognuna gira in un thread proprio e consegna i payload a
RaceSession.process_payload(). Un errore nell'elaborazione di un
payload diventa un avviso e non ferma la sorgente: in gara il feed
non deve mai smettere di essere letto e registrato.
"""

import threading
import time
import traceback
from typing import Optional

from app.session import RaceSession
from livetiming.client import TrackConfig
from livetiming.feed import (
    Connected,
    Disconnected,
    LiveTimingFeed,
    Payload,
)
from livetiming.journal import FeedJournal, replay


def _deliver(
    session: RaceSession,
    payload: str,
    received_at_ms: int,
) -> None:
    """Consegna un payload senza lasciar cadere il thread."""

    try:
        session.process_payload(
            payload,
            received_at_ms=received_at_ms,
        )

    except Exception as error:
        traceback.print_exc()

        session.source_event(
            f"Errore nell'elaborazione del feed: {error}",
            level="error",
        )


class LiveSource(threading.Thread):
    """Feed Apex dal vivo, registrato su file se indicato."""

    def __init__(
        self,
        session: RaceSession,
        config: TrackConfig,
        journal_path: Optional[str] = None,
    ):
        super().__init__(
            name="feed-dal-vivo",
            daemon=True,
        )

        self.session = session
        self.config = config
        self.journal_path = journal_path

    def run(self) -> None:
        journal = (
            FeedJournal(self.journal_path)
            if self.journal_path
            else None
        )

        self.session.set_source(
            "diretta",
            f"collegamento a {self.config.websocket_url}",
        )

        try:
            for event in LiveTimingFeed(self.config).run():

                if isinstance(event, Connected):
                    self.session.source_event(
                        f"collegato (tentativo {event.attempt})",
                        level="info",
                    )

                    if journal is not None:
                        journal.note(f"collegato, tentativo {event.attempt}")

                elif isinstance(event, Disconnected):
                    self.session.source_event(
                        f"caduto: {event.reason}, riprovo fra "
                        f"{event.retry_in_s:g} s",
                        level="warning",
                    )

                    if journal is not None:
                        journal.note(f"caduto: {event.reason}")

                elif isinstance(event, Payload):
                    received_at_ms = int(time.time() * 1000)

                    # Prima il registro: se l'elaborazione fallisce, il
                    # dato resta comunque su file.
                    if journal is not None:
                        journal.append(
                            event.text,
                            received_at_ms=received_at_ms,
                        )

                    _deliver(
                        self.session,
                        event.text,
                        received_at_ms,
                    )

        finally:
            if journal is not None:
                journal.close()


class ReplaySource(threading.Thread):
    """
    Rilettura di un registro a velocità scelta.

    speed=1 riproduce i tempi originali, speed=30 è trenta volte più
    veloce, speed=0 va alla massima velocità possibile.
    """

    def __init__(
        self,
        session: RaceSession,
        path: str,
        speed: float = 1.0,
    ):
        super().__init__(
            name="rilettura",
            daemon=True,
        )

        self.session = session
        self.path = path
        self.speed = speed

    def run(self) -> None:
        self.session.set_source(
            "rilettura",
            f"rilettura di {self.path} (x{self.speed:g})",
            speed=self.speed,
        )

        first_ms: Optional[int] = None
        started_at = time.time()
        count = 0

        for received_at_ms, payload in replay(self.path):

            if first_ms is None:
                first_ms = received_at_ms

            if self.speed > 0:
                due_at = started_at + (
                    (received_at_ms - first_ms) / 1000 / self.speed
                )

                delay = due_at - time.time()

                if delay > 0:
                    time.sleep(delay)

            _deliver(
                self.session,
                payload,
                received_at_ms,
            )

            count += 1

        self.session.source_event(
            f"rilettura terminata ({count} payload)",
            level="info",
            finished=True,
        )
