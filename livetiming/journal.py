"""
Registro grezzo del feed.

Tutto ciò che arriva viene scritto su file prima di essere
interpretato. Serve a due cose:

- se qualcosa a valle si blocca durante la gara, la gara non è persa:
  si rilegge il registro e si ricostruisce tutto;
- permette di riprovare il lettore su una gara vera, invece che su
  dati inventati.

Il formato è una riga JSON per payload, così un file troncato da un
arresto improvviso resta leggibile fino all'ultima riga intera.
"""

import json
import time
from pathlib import Path
from typing import Iterator, Optional


class FeedJournal:
    """Scrive su file ogni payload ricevuto."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Apertura in aggiunta: una riconnessione non cancella
        # quanto già registrato.
        self._file = self.path.open("a", encoding="utf-8")

        self.written = 0

    def append(
        self,
        payload: str,
        received_at_ms: Optional[int] = None,
    ) -> None:
        """Registra un payload."""

        record = {
            "t": received_at_ms or int(time.time() * 1000),
            "p": payload,
        }

        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Scrittura immediata: in gara non si può perdere la coda
        # del file per via della memoria intermedia.
        self._file.flush()

        self.written += 1

    def note(self, message: str) -> None:
        """Annota un evento di servizio, come una riconnessione."""

        record = {
            "t": int(time.time() * 1000),
            "note": message,
        }

        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()

    def close(self) -> None:
        """Chiude il registro."""

        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> "FeedJournal":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def replay(path: str | Path) -> Iterator[tuple[int, str]]:
    """
    Rilegge un registro e restituisce (istante_ms, payload).

    Le righe incomplete o di servizio vengono saltate: un file
    interrotto a metà resta comunque utilizzabile.
    """

    with Path(path).open(encoding="utf-8") as handle:

        for line in handle:

            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                # Ultima riga troncata da un arresto improvviso.
                continue

            payload = record.get("p")

            if payload is None:
                continue

            yield record.get("t", 0), payload
