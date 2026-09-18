"""
Strategia di gara: finestra di pit, passo di piloti, stint e kart.

Funzioni pure sui dati già registrati: non modificano la gara e la
GUI le richiama a ogni aggiornamento.

Il regolamento fissa il numero minimo di stint e di pit, la durata
massima di uno stint e impone che ogni pilota guidi almeno una volta.
Senza durata minima dello stint, la leva strategica è quando fermarsi:
distribuire il tempo restante sugli stint ancora dovuti, anticipare il
pit con un kart lento per cambiarlo, allungare con un kart veloce
senza superare il limite.
"""

from dataclasses import dataclass, field
import statistics
from typing import Optional, Protocol

from core.analytics import (
    clean_laps,
    get_stint_laps,
    lap_time_trend,
)
from core.models import Race, Stint
from core.time_utils import format_time


# Ampiezza della finestra di pit attorno all'obiettivo, per lato.
PIT_WINDOW_HALF_WIDTH_MS = 3 * 60 * 1000

# Preavviso prima del limite di durata dello stint.
STINT_LIMIT_WARNING_MS = 5 * 60 * 1000

# Giri puliti minimi perché un kart entri nella classifica dei kart.
MIN_KART_LAPS = 5


# ==============================
# FINESTRA DI PIT
# ==============================


@dataclass
class StintPlan:
    """Dove siamo rispetto al regolamento e quando conviene fermarsi."""

    race_time_ms: int
    remaining_ms: int

    stint_number: int
    stint_start_ms: int
    stint_elapsed_ms: int

    # Limite regolamentare: inizio stint + durata massima.
    stint_limit_ms: int

    pits_done: int

    # Pit ancora necessari, compreso il prossimo.
    pits_remaining: int

    # Durata media di un pit: quella registrata, o il minimo.
    average_pit_ms: int

    # Tempi di gara del prossimo pit. None se non ne servono altri.
    target_stint_ms: Optional[int] = None
    target_pit_ms: Optional[int] = None
    window_open_ms: Optional[int] = None
    window_close_ms: Optional[int] = None

    unused_driver_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _open_stint(race: Race) -> Optional[Stint]:
    """Stint in corso, se c'è."""

    for stint in reversed(race.stints):
        if stint.end_lap is None:
            return stint

    return None


def plan_stints(race: Race, now_ms: int) -> Optional[StintPlan]:
    """
    Calcola quando fare il prossimo pit.

    Il tempo che resta dall'inizio dello stint in corso alla fine
    della gara, tolti i pit ancora dovuti, viene diviso in parti
    uguali fra gli stint ancora dovuti: l'obiettivo è la fine della
    prima parte. Gli stint dovuti sono il massimo fra quanto chiede il
    regolamento, quanti ne servono per schierare i piloti mai scesi
    in pista e quanti ne servono per restare sotto la durata massima.

    Restituisce None se la gara non è ancora partita.
    """

    config = race.config
    stint = _open_stint(race)

    if stint is None:
        return None

    stint_start_ms = stint.start_time_ms or 0
    time_from_start_ms = max(0, config.duration_ms - stint_start_ms)

    pit_durations = [
        pit_stop.duration_ms
        for pit_stop in race.pit_stops
        if pit_stop.duration_ms is not None
    ]

    average_pit_ms = (
        round(statistics.mean(pit_durations))
        if pit_durations
        else config.min_pit_ms
    )

    driven = {
        existing.driver_id
        for existing in race.stints
    }

    unused_driver_ids = [
        driver.id
        for driver in race.drivers
        if driver.id not in driven
    ]

    closed_stints = len(race.stints) - 1

    # Stint ancora dovuti, compreso quello in corso.
    stints_needed = max(
        config.min_stints - closed_stints,
        config.min_pit_stops - len(race.pit_stops) + 1,
        len(unused_driver_ids) + 1,
        1,
    )

    while (
        time_from_start_ms - (stints_needed - 1) * average_pit_ms
    ) / stints_needed > config.max_stint_ms:
        stints_needed += 1

    plan = StintPlan(
        race_time_ms=now_ms,
        remaining_ms=max(0, config.duration_ms - now_ms),
        stint_number=stint.stint_number,
        stint_start_ms=stint_start_ms,
        stint_elapsed_ms=max(0, now_ms - stint_start_ms),
        stint_limit_ms=stint_start_ms + config.max_stint_ms,
        pits_done=len(race.pit_stops),
        pits_remaining=stints_needed - 1,
        average_pit_ms=average_pit_ms,
        unused_driver_ids=unused_driver_ids,
    )

    if plan.pits_remaining > 0:
        plan.target_stint_ms = round(
            (time_from_start_ms - plan.pits_remaining * average_pit_ms)
            / stints_needed
        )

        plan.target_pit_ms = stint_start_ms + plan.target_stint_ms

        plan.window_open_ms = (
            plan.target_pit_ms - PIT_WINDOW_HALF_WIDTH_MS
        )

        plan.window_close_ms = min(
            plan.target_pit_ms + PIT_WINDOW_HALF_WIDTH_MS,
            plan.stint_limit_ms,
        )

        to_limit_ms = plan.stint_limit_ms - now_ms

        if to_limit_ms < 0:
            plan.warnings.append(
                f"Stint oltre la durata massima da "
                f"{format_time(-to_limit_ms)}."
            )

        elif to_limit_ms <= STINT_LIMIT_WARNING_MS:
            plan.warnings.append(
                f"Limite dello stint fra "
                f"{format_time(to_limit_ms)}: rientrare."
            )

    if unused_driver_ids:
        plan.warnings.append(
            f"Piloti ancora da schierare: {len(unused_driver_ids)}."
        )

    return plan


# ==============================
# PASSO DI STINT E PILOTI
# ==============================


@dataclass
class PaceStats:
    """Statistiche di passo su un insieme di giri."""

    lap_count: int
    clean_lap_count: int
    best_lap_ms: Optional[int]

    # Media, mediana e deviazione standard dei soli giri puliti.
    average_lap_ms: Optional[float]
    median_lap_ms: Optional[float]
    consistency_ms: Optional[float]

    # Millisecondi per giro: positivo se il passo peggiora.
    trend_ms_per_lap: Optional[float]


def pace_stats(laps: list, trend_groups: Optional[list[list]] = None) -> PaceStats:
    """
    Calcola le statistiche di passo.

    La tendenza si calcola separatamente su ogni gruppo (di solito uno
    per stint) e poi si media: un cambio di kart o di pilota fra un
    gruppo e l'altro non deve apparire come un peggioramento.
    """

    clean = clean_laps(laps)
    times = [lap.lap_time_ms for lap in clean]

    trends = [
        trend
        for trend in (
            lap_time_trend(clean_laps(group))
            for group in (trend_groups if trend_groups is not None else [laps])
        )
        if trend is not None
    ]

    return PaceStats(
        lap_count=len(laps),
        clean_lap_count=len(clean),
        best_lap_ms=min(
            (lap.lap_time_ms for lap in laps),
            default=None,
        ),
        average_lap_ms=statistics.mean(times) if times else None,
        median_lap_ms=statistics.median(times) if times else None,
        consistency_ms=statistics.pstdev(times) if times else None,
        trend_ms_per_lap=statistics.mean(trends) if trends else None,
    )


@dataclass
class StintPace:
    """Uno stint con il suo passo."""

    stint_number: int
    driver_id: int
    kart_id: int
    start_lap: Optional[int]
    end_lap: Optional[int]
    start_time_ms: Optional[int]

    # Per lo stint in corso è la durata fino a ora.
    duration_ms: Optional[int]
    is_open: bool
    pace: PaceStats


def stint_pace(race: Race, now_ms: int) -> list[StintPace]:
    """Passo di ogni stint, nell'ordine di gara."""

    result = []

    for stint in race.stints:
        laps = get_stint_laps(race.laps, stint)
        is_open = stint.end_lap is None

        duration_ms = stint.duration_ms

        if is_open and stint.start_time_ms is not None:
            duration_ms = max(0, now_ms - stint.start_time_ms)

        result.append(
            StintPace(
                stint_number=stint.stint_number,
                driver_id=stint.driver_id,
                kart_id=stint.kart_id,
                start_lap=stint.start_lap,
                end_lap=stint.end_lap,
                start_time_ms=stint.start_time_ms,
                duration_ms=duration_ms,
                is_open=is_open,
                pace=pace_stats(laps),
            )
        )

    return result


@dataclass
class DriverPace:
    """Un pilota con il suo tempo di guida e il suo passo."""

    driver_id: int
    stint_count: int
    driving_ms: int
    pace: PaceStats


def driver_pace(race: Race, now_ms: int) -> list[DriverPace]:
    """
    Passo di ogni pilota su tutti i suoi stint.

    I giri puliti si scelgono sulla mediana del pilota stesso, quindi
    un pilota lento non viene penalizzato dal passo degli altri.
    """

    stints = stint_pace(race, now_ms)
    result = []

    for driver in race.drivers:
        own_stints = [
            stint
            for stint in race.stints
            if stint.driver_id == driver.id
        ]

        groups = [
            get_stint_laps(race.laps, stint)
            for stint in own_stints
        ]

        laps = [
            lap
            for group in groups
            for lap in group
        ]

        result.append(
            DriverPace(
                driver_id=driver.id,
                stint_count=len(own_stints),
                driving_ms=sum(
                    stint.duration_ms or 0
                    for stint in stints
                    if stint.driver_id == driver.id
                ),
                pace=pace_stats(
                    laps,
                    trend_groups=groups,
                ),
            )
        )

    return result


# ==============================
# CLASSIFICA DEI KART
# ==============================


class KartLap(Protocol):
    """Un giro con il numero del kart usato."""

    lap_time_ms: int
    kart_number: str


@dataclass
class KartRating:
    """Quanto un kart fa andare più piano o più forte chi lo guida."""

    kart_number: str

    # Mediana dello scarto dal passo abituale di ogni squadra che lo
    # ha guidato: positivo significa kart lento.
    delta_ms: float
    lap_count: int
    team_count: int


def rate_karts(laps_by_team: dict[str, list[KartLap]]) -> list[KartRating]:
    """
    Classifica i kart dal più veloce al più lento.

    Per ogni squadra si prende la mediana dei suoi giri puliti come
    passo abituale; ogni giro diventa uno scarto da quel passo, così
    si confrontano squadre di livello diverso. Dato che i kart girano
    fra le squadre a ogni pit, sul lungo periodo lo scarto mediano di
    un kart misura il kart e non chi lo guida.
    """

    deltas: dict[str, list[float]] = {}
    teams: dict[str, set[str]] = {}

    for team_key, laps in laps_by_team.items():
        clean = [
            lap
            for lap in clean_laps(laps)
            if lap.kart_number
        ]

        if not clean:
            continue

        baseline_ms = statistics.median(
            lap.lap_time_ms
            for lap in clean
        )

        for lap in clean:
            deltas.setdefault(lap.kart_number, []).append(
                lap.lap_time_ms - baseline_ms
            )

            teams.setdefault(lap.kart_number, set()).add(team_key)

    ratings = [
        KartRating(
            kart_number=kart_number,
            delta_ms=statistics.median(values),
            lap_count=len(values),
            team_count=len(teams[kart_number]),
        )
        for kart_number, values in deltas.items()
        if len(values) >= MIN_KART_LAPS
    ]

    return sorted(
        ratings,
        key=lambda rating: rating.delta_ms,
    )
