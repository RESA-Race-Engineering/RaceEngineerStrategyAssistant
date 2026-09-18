"""
Avvio della GUI di Race Engineer.

In gara, con il live timing di Kart&Go e il registro del feed:

    python -m gui --team "Scuderia Dante" --drivers "Marco,Luca,Andrea,Giulia,Paolo,Sara"

Senza feed (tutto a mano):

    python -m gui --manual --team ... --drivers ...

Rilettura di un registro, per esempio una gara simulata:

    python -m livetiming.simulate --out data/sim.jsonl
    python -m gui --replay data/sim.jsonl --speed 60 --auto-pit \
        --team "Scuderia Dante" --drivers "Marco,Luca,Andrea,Giulia,Paolo,Sara"

Ripresa dopo una chiusura del programma:

    python -m gui --resume
"""

import argparse
from datetime import datetime
import webbrowser

from app.session import RaceSession
from app.sources import LiveSource, ReplaySource
from core.models import RaceConfig
from gui.server import make_server
from livetiming.client import (
    DEFAULT_HOST,
    TrackConfig,
    load_track_config,
)


DEFAULT_DB = "data/race_engineer.db"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GUI di Race Engineer: si apre nel browser."
    )

    parser.add_argument(
        "--team",
        default="",
        help="Nome della squadra, come compare nel live timing.",
    )

    parser.add_argument(
        "--drivers",
        default="",
        help="Piloti separati da virgola, nell'ordine previsto.",
    )

    source = parser.add_mutually_exclusive_group()

    source.add_argument(
        "--club",
        default="kartandgo",
        help="Circuito Apex da seguire dal vivo (predefinito).",
    )

    source.add_argument(
        "--replay",
        default="",
        help="Rilegge un registro invece di collegarsi al feed.",
    )

    source.add_argument(
        "--manual",
        action="store_true",
        help="Nessun feed: giri e pit inseriti a mano.",
    )

    parser.add_argument(
        "--apex-port",
        type=int,
        default=0,
        help="configPort del circuito, se config.js non è raggiungibile.",
    )

    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Velocità di rilettura: 60 = un'ora in un minuto, 0 = massima.",
    )

    parser.add_argument(
        "--journal",
        default="",
        help="File del registro del feed (in diretta ne viene creato uno comunque).",
    )

    parser.add_argument(
        "--db",
        default="",
        help=f"Database della gara (in diretta e a mano: {DEFAULT_DB}).",
    )

    parser.add_argument(
        "--resume",
        nargs="?",
        const=-1,
        type=int,
        help="Riprende una gara dal database: l'ultima, o quella indicata.",
    )

    parser.add_argument(
        "--hours",
        type=float,
        default=6,
        help="Durata della gara in ore.",
    )

    parser.add_argument(
        "--auto-pit",
        action="store_true",
        help="Conferma i pit da solo (solo per simulazioni).",
    )

    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Indirizzo del server; 0.0.0.0 per aprire la pagina da altri dispositivi.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Porta del server della GUI.",
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Non aprire il browser.",
    )

    arguments = parser.parse_args()

    live = not arguments.replay and not arguments.manual

    # La simulazione non deve finire nel database della gara vera.
    db_path = arguments.db or (DEFAULT_DB if not arguments.replay else "")

    # ----- sessione -----

    if arguments.resume is not None:
        session = RaceSession.resume(
            arguments.db or DEFAULT_DB,
            race_id=arguments.resume if arguments.resume > 0 else None,
            auto_pit=arguments.auto_pit,
        )
    else:
        drivers = [
            name.strip()
            for name in arguments.drivers.split(",")
            if name.strip()
        ]

        if not arguments.team or not drivers:
            raise SystemExit("Indicare --team e --drivers (oppure --resume).")

        session = RaceSession.create(
            team_name=arguments.team,
            driver_names=drivers,
            db_path=db_path or None,
            config=RaceConfig(
                duration_ms=int(arguments.hours * 60 * 60 * 1000),
            ),
            auto_pit=arguments.auto_pit,
        )

    # ----- sorgente -----

    if arguments.replay:
        ReplaySource(
            session,
            arguments.replay,
            speed=arguments.speed,
        ).start()

    elif live:
        if arguments.apex_port:
            track = TrackConfig(
                club=arguments.club,
                host=DEFAULT_HOST,
                port=arguments.apex_port,
                request_url=f"https://{DEFAULT_HOST}/live-timing/commonv2/functions/",
            )
        else:
            track = load_track_config(arguments.club)

        # In diretta il registro c'è sempre: è la copia di sicurezza
        # della gara.
        journal = (
            arguments.journal
            or f"data/journal_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        )

        LiveSource(
            session,
            track,
            journal_path=journal,
        ).start()

        print(f"Registro del feed: {journal}")

    else:
        session.set_source("manuale", "nessun feed: inserimento a mano")

    # ----- server -----

    server = make_server(
        session,
        host=arguments.host,
        port=arguments.port,
    )

    shown_host = (
        "localhost"
        if arguments.host in ("127.0.0.1", "0.0.0.0")
        else arguments.host
    )

    url = f"http://{shown_host}:{arguments.port}/"

    print(f"Race Engineer: {url}")

    if session.race_id is not None:
        print(f"Gara {session.race_id} nel database {db_path or arguments.db or DEFAULT_DB}")

    if not arguments.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nChiusura.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
