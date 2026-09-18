"""
Trasporto verso il live timing Apex.

Il feed è una WebSocket in sola lettura: il server invia lo stato
completo alla connessione e poi soltanto le differenze. Non esiste
un messaggio di sottoscrizione e non servono cookie o token.

Nessuna dipendenza esterna: la WebSocket è implementata sopra
socket/ssl della libreria standard.
"""

import base64
import hashlib
import os
import re
import socket
import ssl
import struct
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterator, Optional


BASE_URL = "https://www.apex-timing.com/live-timing"
DEFAULT_HOST = "live-data.apex-timing.com"

OPCODE_TEXT = 0x1
OPCODE_BINARY = 0x2
OPCODE_CLOSE = 0x8
OPCODE_PING = 0x9
OPCODE_PONG = 0xA

# Costante fissata da RFC 6455 per la verifica dell'handshake.
WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


@dataclass
class TrackConfig:
    """Parametri di collegamento di un circuito."""

    club: str
    host: str
    port: int
    request_url: str

    @property
    def websocket_url(self) -> str:
        """La porta sicura è la porta di configurazione più tre."""

        return f"wss://{self.host}:{self.port + 3}/"

    @property
    def ajax_port(self) -> int:
        """La porta usata dal ripiego HTTP è la porta più quattro."""

        return self.port + 4


def load_track_config(club: str, timeout: int = 15) -> TrackConfig:
    """
    Legge config.js del circuito per ricavarne host e porta.

    Ogni circuito ha una porta diversa, quindi la configurazione va
    letta e non scritta a mano.
    """

    url = f"{BASE_URL}/{club}/javascript/config.js"

    with urllib.request.urlopen(url, timeout=timeout) as response:
        source = response.read().decode("utf-8", "replace")

    def find(pattern: str, default: str) -> str:
        match = re.search(pattern, source)
        return match.group(1) if match else default

    port = find(r"configPort\s*=\s*(\d+)", "")

    if not port:
        raise ValueError(
            f"configPort non trovato nel config.js del circuito {club}."
        )

    return TrackConfig(
        club=club,
        host=find(r"configHost\s*=\s*'([^']+)'", DEFAULT_HOST),
        port=int(port),
        request_url=find(
            r"configRequestUrl\s*=\s*'([^']+)'",
            f"https://{DEFAULT_HOST}/live-timing/commonv2/functions/",
        ),
    )


class LiveTimingSocket:
    """
    Client WebSocket minimale, di sola lettura, per il feed Apex.

    Il server invia un ping ogni pochi secondi e chiude il
    collegamento se non riceve il pong: la risposta è automatica.
    """

    def __init__(
        self,
        config: TrackConfig,
        connect_timeout: int = 15,
        read_timeout: int = 2,
    ):
        self.config = config
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

        self._socket: Optional[socket.socket] = None
        self._buffer = b""

        # Momento dell'ultimo segno di vita, ping compresi: il feed
        # può restare in silenzio per minuti quando nessuno è in pista,
        # ma il ping del server continua ad arrivare.
        self.last_activity_at: Optional[float] = None

    def connect(self) -> None:
        """Apre il collegamento ed esegue l'handshake."""

        host = self.config.host
        port = self.config.port + 3

        raw = socket.create_connection(
            (host, port),
            timeout=self.connect_timeout,
        )

        context = ssl.create_default_context()

        self._socket = context.wrap_socket(
            raw,
            server_hostname=host,
        )

        key = base64.b64encode(os.urandom(16)).decode()

        request = (
            f"GET / HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"Origin: {BASE_URL.rsplit('/', 1)[0]}\r\n"
            f"\r\n"
        )

        self._socket.sendall(request.encode())

        header = self._read_until(b"\r\n\r\n")

        status_line = header.split(b"\r\n")[0]

        if b" 101 " not in status_line:
            raise ConnectionError(
                f"Handshake rifiutato: {status_line.decode(errors='replace')}"
            )

        expected = base64.b64encode(
            hashlib.sha1((key + WEBSOCKET_GUID).encode()).digest()
        ).decode()

        accept = re.search(
            rb"Sec-WebSocket-Accept:\s*(\S+)",
            header,
            re.IGNORECASE,
        )

        if accept is None or accept.group(1).decode() != expected:
            raise ConnectionError(
                "Sec-WebSocket-Accept non valido."
            )

        self._socket.settimeout(self.read_timeout)
        self.last_activity_at = time.time()

    def _read_until(self, marker: bytes) -> bytes:
        """Legge finché non compare il delimitatore indicato."""

        while marker not in self._buffer:
            chunk = self._socket.recv(4096)

            if not chunk:
                raise ConnectionError(
                    "Collegamento chiuso durante l'handshake."
                )

            self._buffer += chunk

        header, self._buffer = self._buffer.split(marker, 1)

        return header

    def _send_frame(self, opcode: int, payload: bytes = b"") -> None:
        """Invia un frame mascherato, come richiesto ai client."""

        mask = os.urandom(4)

        masked = bytes(
            byte ^ mask[index % 4]
            for index, byte in enumerate(payload)
        )

        header = struct.pack("!BB", 0x80 | opcode, 0x80 | len(payload))

        self._socket.sendall(header + mask + masked)

    def _next_frame(self) -> Optional[tuple[int, bytes]]:
        """
        Estrae un frame completo dal buffer.

        Restituisce None se i dati ricevuti non bastano ancora.
        """

        data = self._buffer

        if len(data) < 2:
            return None

        opcode = data[0] & 0x0F
        length = data[1] & 0x7F
        offset = 2

        if length == 126:
            if len(data) < offset + 2:
                return None

            length = struct.unpack(">H", data[offset:offset + 2])[0]
            offset += 2

        elif length == 127:
            if len(data) < offset + 8:
                return None

            length = struct.unpack(">Q", data[offset:offset + 8])[0]
            offset += 8

        # Il server non maschera: il bit di maschera è sempre a zero.
        if len(data) < offset + length:
            return None

        payload = data[offset:offset + length]
        self._buffer = data[offset + length:]

        return opcode, payload

    def send_ping(self) -> bool:
        """
        Invia un ping al server.

        Il feed non ha un battito regolare: manda un ping poco dopo
        la connessione e poi tace anche per minuti quando la pista è
        vuota. Per distinguere una pista ferma da un collegamento
        morto il ping lo facciamo noi, e il server risponde col pong.
        """

        if self._socket is None:
            return False

        try:
            self._send_frame(OPCODE_PING)
            return True

        except OSError:
            return False

    def poll(self) -> Optional[list[str]]:
        """
        Legge i dati disponibili senza bloccare a lungo.

        Restituisce la lista dei payload completi ricevuti, che può
        essere vuota, oppure None se il server ha chiuso. Serve per
        poter sorvegliare il silenzio del feed dall'esterno.
        """

        if self._socket is None:
            return None

        closed = False

        try:
            chunk = self._socket.recv(65536)

            if not chunk:
                closed = True
            else:
                self._buffer += chunk
                self.last_activity_at = time.time()

        except socket.timeout:
            pass

        except OSError:
            return None

        payloads = []

        while True:
            frame = self._next_frame()

            if frame is None:
                break

            opcode, payload = frame

            if opcode == OPCODE_PING:
                try:
                    self._send_frame(OPCODE_PONG, payload)
                except OSError:
                    return None

                continue

            if opcode == OPCODE_CLOSE:
                return None

            if opcode in (OPCODE_TEXT, OPCODE_BINARY):
                text = payload.decode("utf-8", "replace")

                if text.strip():
                    payloads.append(text)

        if closed:
            return None if not payloads else payloads

        return payloads

    def payloads(self, timeout_s: Optional[float] = None) -> Iterator[str]:
        """
        Restituisce i payload testuali via via che arrivano.

        Si interrompe quando il server chiude o quando scade il
        tempo indicato.
        """

        if self._socket is None:
            raise ConnectionError("Collegamento non aperto.")

        deadline = None if timeout_s is None else time.time() + timeout_s

        while deadline is None or time.time() < deadline:

            batch = self.poll()

            if batch is None:
                return

            for payload in batch:
                yield payload

    def close(self) -> None:
        """Chiude il collegamento."""

        if self._socket is None:
            return

        try:
            self._send_frame(OPCODE_CLOSE)
        except OSError:
            pass

        try:
            self._socket.close()
        finally:
            self._socket = None


def fetch_via_http(
    config: TrackConfig,
    init: str = "0",
    index: str = "0",
    counter: int = 1,
    client_id: int = 0,
    timeout: int = 15,
) -> tuple[str, str, str]:
    """
    Ripiego HTTP usato dal client ufficiale quando manca la WebSocket.

    Restituisce (init, index, payload): init e index vanno rimandati
    alla chiamata successiva. Un payload vuoto significa che non è
    cambiato nulla.
    """

    query = urllib.parse.urlencode(
        {
            "version": 2,
            "init": init,
            "index": index,
            "port": config.ajax_port,
            "counter": counter,
            "duration": 0,
            "id": client_id or (os.getpid() * 7919),
            "ignored": 0,
        }
    )

    url = f"{config.request_url}live_ajax.php?{query}"

    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8", "replace").strip()

    if not body:
        return init, index, ""

    parts = body.split("@", 2)

    if len(parts) != 3:
        return init, index, ""

    return parts[0], parts[1], parts[2]
