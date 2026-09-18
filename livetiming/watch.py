"""
Monitor da riga di comando del live timing.

Serve per verificare l'aggancio in pista prima e durante la gara:

    python -m livetiming.watch --club kartandgo --team "Nome Squadra"

Senza --team mostra la griglia completa, utile per leggere il nome
esatto con cui il cronometraggio ha iscritto la squadra.
"""

import argparse
import time

from core.models import RaceConfig
from livetiming.client import (
    DEFAULT_HOST,
    TrackConfig,
    load_track_config,
)
from livetiming.feed import (
    Connected,
    Disconnected,
    LiveTimingFeed,
    Payload,
)
from livetiming.journal import FeedJournal, replay
from livetiming.protocol import GridReplaced, parse_payload
from livetiming.reader import (
    KartNumberChanged,
    KartNumberMismatch,
    LapCompleted,
    PitIn,
    PitOut,
    SessionChanged,
    TeamBound,
    TeamLost,
    TeamTracker,
)
from core.time_utils import format_time


def describe(event) -> str:
    """Rende leggibile un evento del lettore."""

    if isinstance(event, TeamBound):
        return (
            f"AGGANCIATA  riga {event.row_id} | "
            f"{event.team_label} | kart {event.kart_number}"
        )

    if isinstance(event, TeamLost):
        return (
            f"PERSA       la riga {event.row_id} non è più in griglia"
        )

    if isinstance(event, LapCompleted):
        lap_time = (
            format_time(event.lap_time_ms)
            if event.lap_time_ms is not None
            else "n/d"
        )

        race_time = (
            format_time(event.race_time_ms)
            if event.race_time_ms is not None
            else "n/d"
        )

        return (
            f"GIRO        {event.lap_number} | {lap_time} | "
            f"kart {event.kart_number} | gara {race_time}"
        )

    if isinstance(event, PitIn):
        return (
            f"PIT IN      dopo il giro {event.lap_number} | "
            f"kart {event.kart_number} -> lo stint si chiude"
        )

    if isinstance(event, PitOut):
        return (
            f"PIT OUT     kart {event.kart_number} -> "
            f"inizia lo stint successivo"
        )

    if isinstance(event, KartNumberChanged):
        return (
            f"KART        il feed è passato da "
            f"{event.previous} a {event.current}"
        )

    if isinstance(event, KartNumberMismatch):
        return (
            f"ATTENZIONE  la GUI dice kart {event.operator_value}, "
            f"il feed dice {event.feed_value}"
        )

    if isinstance(event, SessionChanged):
        return f"SESSIONE    ricaricata (modalità {event.mode})"

    return str(event)


def show_grid(payload: str) -> None:
    """Stampa la griglia completa, per individuare la squadra."""

    for message in parse_payload(payload):

        if not isinstance(message, GridReplaced):
            continue

        number_cell = message.columns.get("no", "")
        name_cell = message.columns.get("dr", "")
        rank_cell = message.columns.get("rk", "")

        if not message.rows:
            print("  (griglia vuota: nessun kart in pista)")
            return

        for row_id, row in sorted(
            message.rows.items(),
            key=lambda item: item[1].position,
        ):
            print(
                f"  {row_id:>5} | pos {row.cells.get(rank_cell, ''):>3} | "
                f"kart {row.cells.get(number_cell, ''):>4} | "
                f"{row.cells.get(name_cell, '')}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monitor del live timing Apex."
    )

    parser.add_argument(
        "--club",
        default="kartandgo",
        help="Identificativo del circuito nell'URL di Apex.",
    )

    parser.add_argument(
        "--team",
        default="",
        help="Nome della squadra da seguire.",
    )

    parser.add_argument(
        "--kart",
        default="",
        help="Numero di kart dichiarato dall'operatore.",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help=(
            "configPort del circuito, da usare quando il live timing "
            "non è ospitato sotto apex-timing.com/live-timing/<club>/. "
            "È la porta della WebSocket meno tre."
        ),
    )

    parser.add_argument(
        "--journal",
        default="",
        help=(
            "File su cui registrare tutto il feed. In gara va sempre "
            "indicato: permette di ricostruire la gara se qualcosa "
            "si blocca."
        ),
    )

    parser.add_argument(
        "--replay",
        default="",
        help="Rilegge un registro invece di collegarsi al feed.",
    )

    parser.add_argument(
        "--seconds",
        type=int,
        default=0,
        help="Durata del monitoraggio: 0 significa senza limite.",
    )

    arguments = parser.parse_args()

    tracker = TeamTracker(
        team_name=arguments.team,
        race_duration_ms=RaceConfig().duration_ms,
    )

    if arguments.kart:
        tracker.set_operator_kart_number(arguments.kart)

    # ----- rilettura di un registro -----

    if arguments.replay:
        for received_at_ms, payload in replay(arguments.replay):

            stamp = time.strftime(
                "%H:%M:%S",
                time.localtime(received_at_ms / 1000),
            )

            if not arguments.team:
                print(f"[{stamp}] payload di {len(payload)} byte")
                show_grid(payload)
                continue

            for event in tracker.process(
                payload,
                now_ms=received_at_ms,
            ):
                print(f"[{stamp}] {describe(event)}")

        return

    # ----- collegamento al feed -----

    if arguments.port:
        config = TrackConfig(
            club=arguments.club,
            host=DEFAULT_HOST,
            port=arguments.port,
            request_url=(
                f"https://{DEFAULT_HOST}"
                f"/live-timing/commonv2/functions/"
            ),
        )
    else:
        config = load_track_config(arguments.club)

    print(f"Circuito : {config.club}")
    print(f"WebSocket: {config.websocket_url}")

    journal = FeedJournal(arguments.journal) if arguments.journal else None

    if journal is not None:
        print(f"Registro : {journal.path}")

    print()

    feed = LiveTimingFeed(config)

    timeout = arguments.seconds or None

    try:
        for event in feed.run(timeout_s=timeout):

            stamp = time.strftime("%H:%M:%S")

            if isinstance(event, Connected):
                print(f"[{stamp}] COLLEGATO   tentativo {event.attempt}")

                if journal is not None:
                    journal.note(f"collegato, tentativo {event.attempt}")

                continue

            if isinstance(event, Disconnected):
                print(
                    f"[{stamp}] CADUTO      {event.reason} | "
                    f"riprovo fra {event.retry_in_s}s"
                )

                if journal is not None:
                    journal.note(f"caduto: {event.reason}")

                continue

            if not isinstance(event, Payload):
                continue

            if journal is not None:
                journal.append(event.text)

            if not arguments.team:
                print(f"[{stamp}] payload di {len(event.text)} byte")
                show_grid(event.text)
                continue

            for reader_event in tracker.process(event.text):
                print(f"[{stamp}] {describe(reader_event)}")

    except KeyboardInterrupt:
        print("\nInterrotto.")

    finally:
        if journal is not None:
            print(f"\nRegistrati {journal.written} payload in {journal.path}")
            journal.close()


if __name__ == "__main__":
    main()
