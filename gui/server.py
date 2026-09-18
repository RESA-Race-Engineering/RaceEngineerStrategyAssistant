"""
Server web della GUI.

Solo libreria standard: la pagina (gui/static) chiede lo stato a
/api/state una volta al secondo e invia le azioni dell'operatore con
richieste POST in JSON. Il server ascolta di serie solo su questo
computer; con --host 0.0.0.0 la pagina si apre anche da telefoni e
tablet sulla stessa rete, che però possono anche confermare i pit.
"""

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import traceback
from urllib.parse import parse_qs, urlparse

from app.session import RaceSession
from gui.snapshot import DEFAULT_WINDOW, build_snapshot
from livetiming.protocol import parse_time_to_ms


STATIC_DIR = Path(__file__).parent / "static"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}


def _optional_int(value):
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Valore non valido: '{value}'.") from None


def _seconds_to_ms(value):
    """Secondi dalla pagina ("91.5" o "91,5") in millisecondi."""

    if value in (None, ""):
        return None

    try:
        return round(float(str(value).replace(",", ".")) * 1000)
    except ValueError:
        raise ValueError(f"Durata non valida: '{value}'.") from None


class _Handler(BaseHTTPRequestHandler):
    """Richieste della pagina. session è impostata da make_server()."""

    session: RaceSession = None

    # ----- risposte -----

    def _send(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(
            status,
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def log_message(self, *_) -> None:
        # Una richiesta al secondo per ogni pagina aperta: niente log.
        pass

    # ----- GET -----

    def do_GET(self) -> None:
        url = urlparse(self.path)

        if url.path == "/api/state":
            query = parse_qs(url.query)

            try:
                stint = _optional_int(query.get("stint", [""])[0])
            except ValueError:
                stint = None

            self._json(
                build_snapshot(
                    self.session,
                    window_key=query.get("window", [DEFAULT_WINDOW])[0],
                    stint_number=stint,
                )
            )
            return

        name = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
        path = (STATIC_DIR / name).resolve()

        # Nessuna uscita dalla cartella static.
        if STATIC_DIR.resolve() not in path.parents or not path.is_file():
            self._send(
                HTTPStatus.NOT_FOUND,
                b"Non trovato",
                "text/plain; charset=utf-8",
            )
            return

        self._send(
            HTTPStatus.OK,
            path.read_bytes(),
            CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
        )

    # ----- POST -----

    def do_POST(self) -> None:
        url = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)

        try:
            data = json.loads(self.rfile.read(length) or b"{}")
            result = self._action(url.path, data)

        except ValueError as error:
            self._json(
                {"error": str(error)},
                HTTPStatus.BAD_REQUEST,
            )
            return

        except Exception as error:
            traceback.print_exc()

            self._json(
                {"error": f"Errore interno: {error}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        if result is None:
            self._json(
                {"error": "Azione sconosciuta."},
                HTTPStatus.NOT_FOUND,
            )
            return

        self._json(result)

    def _action(self, path: str, data: dict):
        session = self.session

        if path == "/api/start":
            session.start_race(
                driver_id=int(data["driver_id"]),
                kart_number=data.get("kart_number"),
            )
            return {"ok": True}

        if path == "/api/pit":
            session.confirm_pit(
                kart_number=data.get("kart_number"),
                driver_id=int(data["driver_id"]),
                duration_ms=_seconds_to_ms(data.get("duration_s")),
                refuel=bool(data.get("refuel")),
                tire_change=bool(data.get("tire_change")),
            )
            return {"ok": True}

        if path == "/api/pit/discard":
            session.discard_pit()
            return {"ok": True}

        if path == "/api/lap":
            lap_time_ms = parse_time_to_ms(str(data.get("lap_time", "")))

            if not lap_time_ms:
                raise ValueError("Tempo sul giro non valido: usare 53.123 o 1:02.345.")

            session.add_manual_lap(lap_time_ms)
            return {"ok": True}

        if path == "/api/event":
            session.add_event(
                description=str(data.get("description", "")),
                penalty_ms=_seconds_to_ms(data.get("penalty_s")) or 0,
            )
            return {"ok": True}

        if path == "/api/export":
            return {"ok": True, "folder": str(session.export_csv())}

        return None


def make_server(
    session: RaceSession,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    """Crea il server della GUI legato alla sessione."""

    handler = type(
        "Handler",
        (_Handler,),
        {"session": session},
    )

    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True

    return server
