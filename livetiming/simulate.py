"""
Simulatore di gara in formato Apex.

Genera un registro, nello stesso formato di journal.py, con una gara
di endurance inventata: squadre di sei piloti, kart di prestazioni
diverse che girano fra le squadre a ogni pit, cronometro alla
rovescia, un periodo di bandiera gialla. Serve a provare lettore e
GUI quando non c'è una gara dal vivo:

    python -m livetiming.simulate --out data/sim.jsonl
    python -m gui --replay data/sim.jsonl --speed 60 --auto-pit \
        --team "Scuderia Dante" --drivers "Marco,Luca,Andrea,Giulia,Paolo,Sara"

Il formato ricalca quello osservato sul feed ma è una nostra
ricostruzione: non sostituisce la verifica su un registro reale.
"""

import argparse
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import heapq
from pathlib import Path
import random
from typing import Optional

from livetiming.journal import FeedJournal


BASE_LAP_MS = 53_000
FIRST_LAP_EXTRA_MS = 3_000

# Tempo perso in più percorrendo la corsia dei box.
PIT_LANE_EXTRA_MS = 6_000

# Punto del giro, in frazione, in cui si entra ai box.
PIT_ENTRY_FRACTION = 0.6

# Peggioramento del passo con i giri dello stint (fatica).
FATIGUE_MS_PER_LAP = 12

# Bandiera gialla: dal secondo al tempo di gara indicato.
YELLOW_FROM_MS = (2 * 60 + 10) * 60 * 1000
YELLOW_TO_MS = (2 * 60 + 14) * 60 * 1000
YELLOW_EXTRA_MS = 10_000

TEAM_NAMES = [
    "Kart Rossi",
    "Team Verdi",
    "Blu Racing",
    "Lupi Grigi",
    "Orange Kart",
    "Falchi",
    "Tartarughe Veloci",
    "Corse Nord",
    "Box Box",
    "Gialloblu",
    "Fulmini",
    "Asfalto Rovente",
    "Curva Tre",
    "Scia Perfetta",
    "Ultimo Giro",
    "Pole Position",
    "Staccata Lunga",
    "Cordolo Racing",
    "Motore Caldo",
    "Traiettoria",
]

# Colonne della griglia: data-id, data-type, intestazione.
COLUMNS = [
    ("c1", "rk", "Pos"),
    ("c2", "no", "Kart"),
    ("c3", "dr", "Squadra"),
    ("c4", "llp", "Ultimo"),
    ("c5", "blp", "Migliore"),
    ("c6", "gap", "Distacco"),
    ("c7", "tlp", "Giri"),
    ("c8", "pit", "Pit"),
]

CELL = {
    data_type: cell_id
    for cell_id, data_type, _ in COLUMNS
}


def format_lap(milliseconds: int) -> str:
    """Tempo sul giro come lo scrive il feed: "53.123", "2:34.567"."""

    minutes, rest = divmod(milliseconds, 60_000)
    seconds, millis = divmod(rest, 1000)

    if minutes:
        return f"{minutes}:{seconds:02d}.{millis:03d}"

    return f"{seconds}.{millis:03d}"


def format_clock(milliseconds: int) -> str:
    """Cronometro come "5:59:59"."""

    total = max(0, milliseconds) // 1000
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)

    return f"{hours}:{minutes:02d}:{seconds:02d}"


@dataclass
class SimTeam:
    """Stato di una squadra simulata."""

    row_id: str
    name: str
    offset_ms: float
    driver_offsets_ms: list[float]
    kart: int

    laps: int = 0
    last_cross_ms: int = 0
    best_ms: Optional[int] = None
    pits: int = 0
    stint: int = 0
    stint_start_ms: int = 0
    lap_in_stint: int = 0
    target_stint_ms: int = 0
    position: int = 0
    pit_lap_ms: int = 0


@dataclass(order=True)
class _Event:
    time_ms: int
    sequence: int
    kind: str = field(compare=False)
    team: Optional[SimTeam] = field(default=None, compare=False)


class RaceSimulator:
    """Produce i payload di una gara simulata, in ordine di tempo."""

    def __init__(
        self,
        team_name: str,
        team_count: int = 16,
        duration_ms: int = 6 * 60 * 60 * 1000,
        min_pit_stops: int = 14,
        max_stint_ms: int = 45 * 60 * 1000,
        min_pit_ms: int = 90 * 1000,
        seed: int = 1,
    ):
        self.random = random.Random(seed)

        self.duration_ms = duration_ms
        self.min_pit_stops = min_pit_stops
        self.max_stint_ms = max_stint_ms
        self.min_pit_ms = min_pit_ms

        spare_karts = 4
        kart_count = team_count + spare_karts

        # Qualche kart decisamente lento, come nei noleggi veri.
        self.kart_offsets_ms = {
            number: self.random.gauss(0, 250)
            for number in range(1, kart_count + 1)
        }

        for number in self.random.sample(range(1, kart_count + 1), 2):
            self.kart_offsets_ms[number] += 700

        self.kart_pool = deque(range(team_count + 1, kart_count + 1))

        names = [team_name] + TEAM_NAMES[:team_count - 1]

        self.teams = [
            SimTeam(
                row_id=f"r{101 + index}",
                name=name,
                offset_ms=self.random.gauss(0, 500),
                driver_offsets_ms=[
                    self.random.gauss(0, 300)
                    for _ in range(6)
                ],
                kart=index + 1,
                position=index + 1,
            )
            for index, name in enumerate(names)
        ]

        # La nostra squadra lotta per il podio e ha un pilota
        # decisamente più lento: così le analisi hanno qualcosa da
        # mostrare.
        self.teams[0].offset_ms = -350
        self.teams[0].driver_offsets_ms = [-150, 50, 150, -100, 650, 250]

        self._first_cross_ms: dict[int, int] = {}
        self._events: list[_Event] = []
        self._sequence = 0

    # ----- modello -----

    def _lap_time(self, team: SimTeam, start_ms: int) -> int:
        driver_ms = team.driver_offsets_ms[
            team.stint % len(team.driver_offsets_ms)
        ]

        lap_ms = (
            BASE_LAP_MS
            + team.offset_ms
            + driver_ms
            + self.kart_offsets_ms[team.kart]
            + FATIGUE_MS_PER_LAP * team.lap_in_stint
            + self.random.gauss(0, 250)
        )

        if self.random.random() < 0.03:
            lap_ms += self.random.uniform(800, 3000)

        if YELLOW_FROM_MS <= start_ms < YELLOW_TO_MS:
            lap_ms += YELLOW_EXTRA_MS

        return int(lap_ms)

    def _plan_stint(self, team: SimTeam, now_ms: int) -> int:
        """Durata obiettivo dello stint che inizia ora."""

        pits_left = max(0, self.min_pit_stops - team.pits)
        pit_cost_ms = self.min_pit_ms + 4_000 + PIT_LANE_EXTRA_MS

        target_ms = (
            (self.duration_ms - now_ms - pits_left * pit_cost_ms)
            / (pits_left + 1)
            + self.random.gauss(0, 90_000)
        )

        return int(
            min(
                max(target_ms, 5 * 60 * 1000),
                self.max_stint_ms - 60_000,
            )
        )

    def _push(self, time_ms: int, kind: str, team=None) -> None:
        self._sequence += 1

        heapq.heappush(
            self._events,
            _Event(
                time_ms=time_ms,
                sequence=self._sequence,
                kind=kind,
                team=team,
            ),
        )

    # ----- payload -----

    def _grid(self) -> str:
        header = "".join(
            f'<td data-id="{cell_id}" data-type="{data_type}">{label}</td>'
            for cell_id, data_type, label in COLUMNS
        )

        rows = []

        for team in self.teams:
            values = {
                "rk": team.position,
                "no": team.kart,
                "dr": team.name,
                "llp": "",
                "blp": "",
                "gap": "",
                "tlp": 0,
                "pit": 0,
            }

            cells = "".join(
                f'<td data-id="{team.row_id}{cell_id}">{values[data_type]}</td>'
                for cell_id, data_type, _ in COLUMNS
            )

            rows.append(
                f'<tr data-id="{team.row_id}" data-pos="{team.position}">'
                f"{cells}</tr>"
            )

        return (
            '<tbody><tr data-id="r0" class="head" data-pos="0">'
            + header
            + "</tr>"
            + "".join(rows)
            + "</tbody>"
        )

    def _positions(self) -> list[str]:
        """Riordina la classifica e restituisce le posizioni cambiate."""

        ordered = sorted(
            self.teams,
            key=lambda team: (-team.laps, team.last_cross_ms),
        )

        lines = []

        for position, team in enumerate(ordered, start=1):
            if team.position != position:
                team.position = position

                lines.append(f"{team.row_id}{CELL['rk']}||{position}")
                lines.append(f"{team.row_id}|#|{position}")

        return lines

    def _gap(self, team: SimTeam, now_ms: int) -> str:
        first_ms = self._first_cross_ms[team.laps]

        if first_ms == now_ms:
            return ""

        laps_down = 0

        while self._first_cross_ms.get(team.laps + laps_down + 1, now_ms + 1) <= now_ms:
            laps_down += 1

        if laps_down:
            return f"{laps_down} Giro" if laps_down == 1 else f"{laps_down} Giri"

        return f"+{(now_ms - first_ms) / 1000:.3f}"

    def _cross(self, team: SimTeam, now_ms: int) -> str:
        lap_ms = now_ms - team.last_cross_ms

        team.laps += 1
        team.last_cross_ms = now_ms
        team.lap_in_stint += 1

        self._first_cross_ms.setdefault(team.laps, now_ms)

        lines = [
            f"{team.row_id}{CELL['llp']}|tn|{format_lap(lap_ms)}",
            f"{team.row_id}{CELL['tlp']}||{team.laps}",
            f"{team.row_id}{CELL['gap']}||{self._gap(team, now_ms)}",
        ]

        if team.best_ms is None or lap_ms < team.best_ms:
            team.best_ms = lap_ms
            lines.append(f"{team.row_id}{CELL['blp']}|tb|{format_lap(lap_ms)}")

        lines.extend(self._positions())
        lines.append(f"{team.row_id}|*|{lap_ms}")

        self._schedule_next(team, now_ms)

        return "\n".join(lines)

    def _schedule_next(self, team: SimTeam, now_ms: int) -> None:
        """Decide se il prossimo giro è normale o con il pit."""

        remaining_ms = self.duration_ms - now_ms

        if remaining_ms <= 0:
            return

        lap_ms = self._lap_time(team, now_ms)

        more_pits_needed = (
            team.pits < self.min_pit_stops
            or remaining_ms > self.max_stint_ms - 60_000
        )

        pit_due = (
            more_pits_needed
            and remaining_ms > 3 * 60 * 1000
            and now_ms - team.stint_start_ms >= team.target_stint_ms
        )

        if pit_due:
            team.pit_lap_ms = lap_ms

            self._push(
                now_ms + int(lap_ms * PIT_ENTRY_FRACTION),
                "pit_in",
                team,
            )
        else:
            self._push(now_ms + lap_ms, "cross", team)

    def _pit_in(self, team: SimTeam, now_ms: int) -> str:
        stop_ms = self.min_pit_ms + int(self.random.uniform(500, 8000))

        self._push(now_ms + stop_ms, "pit_out", team)

        return f"{team.row_id}|*in|"

    def _pit_out(self, team: SimTeam, now_ms: int) -> str:
        # Il kart lasciato torna in fondo alla fila di quelli ai box.
        self.kart_pool.append(team.kart)
        team.kart = self.kart_pool.popleft()

        team.pits += 1
        team.stint += 1
        team.stint_start_ms = now_ms
        team.lap_in_stint = 0
        team.target_stint_ms = self._plan_stint(team, now_ms)

        self._push(
            now_ms
            + int(team.pit_lap_ms * (1 - PIT_ENTRY_FRACTION))
            + PIT_LANE_EXTRA_MS,
            "cross",
            team,
        )

        return "\n".join(
            [
                f"{team.row_id}{CELL['no']}||{team.kart}",
                f"{team.row_id}{CELL['pit']}||{team.pits}",
                f"{team.row_id}|*out|",
            ]
        )

    # ----- generazione -----

    def payloads(self):
        """Restituisce (tempo di gara in ms, payload) in ordine."""

        yield -30_000, "\n".join(
            [
                "init|r|",
                "title1||Simulazione",
                "title2||6 Ore di prova",
                "track||Pista simulata",
                "light|lg|",
                f"grid||{self._grid()}",
                f"dyn1|countdown|{format_clock(self.duration_ms)}",
            ]
        )

        for second in range(0, self.duration_ms // 1000 + 1):
            self._push(second * 1000, "tick")

        self._push(YELLOW_FROM_MS, "yellow")
        self._push(YELLOW_TO_MS, "green")

        for team in self.teams:
            team.target_stint_ms = self._plan_stint(team, 0)

            self._push(
                self._lap_time(team, 0)
                + FIRST_LAP_EXTRA_MS
                + team.position * 400,
                "cross",
                team,
            )

        while self._events:
            event = heapq.heappop(self._events)

            if event.kind == "tick":
                payload = (
                    f"dyn1|countdown|"
                    f"{format_clock(self.duration_ms - event.time_ms)}"
                )
            elif event.kind == "yellow":
                payload = "light|ly|"
            elif event.kind == "green":
                payload = "light|lg|"
            elif event.kind == "cross":
                payload = self._cross(event.team, event.time_ms)
            elif event.kind == "pit_in":
                payload = self._pit_in(event.team, event.time_ms)
            else:
                payload = self._pit_out(event.team, event.time_ms)

            yield event.time_ms, payload


def write_journal(
    simulator: RaceSimulator,
    path: str | Path,
    start: Optional[datetime] = None,
) -> int:
    """Scrive la gara simulata su registro; restituisce i payload."""

    path = Path(path)

    # Il registro si apre in aggiunta: una simulazione nuova riparte
    # da un file vuoto.
    path.unlink(missing_ok=True)

    start_ms = int((start or datetime.now()).timestamp() * 1000)
    count = 0

    with FeedJournal(path) as journal:
        for race_time_ms, payload in simulator.payloads():
            journal.append(
                payload,
                received_at_ms=start_ms + race_time_ms,
            )

            count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera un registro con una gara simulata."
    )

    parser.add_argument(
        "--out",
        default="data/sim.jsonl",
        help="File del registro da creare.",
    )

    parser.add_argument(
        "--team",
        default="Scuderia Dante",
        help="Nome della nostra squadra.",
    )

    parser.add_argument(
        "--teams",
        type=int,
        default=16,
        help="Numero di squadre in pista.",
    )

    parser.add_argument(
        "--hours",
        type=float,
        default=6,
        help="Durata della gara in ore.",
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=1,
        help="Seme casuale: lo stesso seme dà la stessa gara.",
    )

    arguments = parser.parse_args()

    if not 2 <= arguments.teams <= len(TEAM_NAMES) + 1:
        raise SystemExit(
            f"Le squadre devono essere fra 2 e {len(TEAM_NAMES) + 1}."
        )

    simulator = RaceSimulator(
        team_name=arguments.team,
        team_count=arguments.teams,
        duration_ms=int(arguments.hours * 60 * 60 * 1000),
        seed=arguments.seed,
    )

    count = write_journal(simulator, arguments.out)

    print(f"Registrati {count} payload in {arguments.out}")
    print()
    print("Per vederla nella GUI:")
    print(
        f'  python -m gui --replay {arguments.out} --speed 60 --auto-pit '
        f'--team "{arguments.team}" '
        f'--drivers "Marco,Luca,Andrea,Giulia,Paolo,Sara"'
    )


if __name__ == "__main__":
    main()
