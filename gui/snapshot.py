"""
Fotografia dello stato della gara per la pagina web.

Tutti i calcoli stanno qui, in Python: la pagina si limita a
disegnare. La finestra di analisi scelta dall'operatore vale per la
nostra squadra, per i concorrenti e per il grafico, come chiede il
piano; i dati nostri (race.laps) e quelli dei concorrenti (feed) non
vengono mai mescolati.

Tempi in millisecondi interi; None diventa null in JSON.
"""

from typing import Optional

from app.session import RaceSession, _is_practice
from core.analytics import (
    ANALYSIS_WINDOWS,
    AnalysisWindow,
    AnalysisWindowType,
    analyze_window,
    clean_laps,
    get_laps_for_window,
    get_stint_laps,
)
from core.rules import (
    RuleStatus,
    check_all_drivers_used,
    check_min_pit_stops,
    check_min_stints,
    check_pit_duration,
    check_stint_duration,
)
from core.strategy import (
    driver_pace,
    plan_stints,
    rate_karts,
    stint_pace,
)


SELECTED_STINT = "Stint selezionato"
DEFAULT_WINDOW = "Ultimi 10"

# Avvisi inviati alla pagina.
ALERTS_SHOWN = 60


def window_keys() -> list[str]:
    return list(ANALYSIS_WINDOWS) + [SELECTED_STINT]


def _window(key: str, stint_number: Optional[int]) -> AnalysisWindow:
    if key == SELECTED_STINT and stint_number:
        return AnalysisWindow(
            window_type=AnalysisWindowType.STINT,
            value=stint_number,
        )

    return ANALYSIS_WINDOWS.get(key, ANALYSIS_WINDOWS[DEFAULT_WINDOW])


def _ms(value) -> Optional[int]:
    return None if value is None else int(round(value))


def _analysis(analysis) -> dict:
    return {
        "laps": analysis.lap_count,
        "best": _ms(analysis.best_lap_ms),
        "avg": _ms(analysis.average_lap_ms),
        "std": _ms(analysis.consistency_ms),
        "last": _ms(analysis.last_lap_ms),
    }


def _pace(pace) -> dict:
    return {
        "laps": pace.lap_count,
        "clean": pace.clean_lap_count,
        "best": _ms(pace.best_lap_ms),
        "avg": _ms(pace.average_lap_ms),
        "median": _ms(pace.median_lap_ms),
        "std": _ms(pace.consistency_ms),
        "trend": (
            None
            if pace.trend_ms_per_lap is None
            else round(pace.trend_ms_per_lap, 1)
        ),
    }


def _rule(result) -> dict:
    return {
        "status": result.status.value,
        "rule": result.rule_name,
        "message": result.message,
    }


def build_snapshot(
    session: RaceSession,
    window_key: str = DEFAULT_WINDOW,
    stint_number: Optional[int] = None,
) -> dict:
    """Stato completo, pronto per json.dumps()."""

    with session.lock:
        return _build(
            session,
            window_key,
            stint_number,
        )


def _build(
    session: RaceSession,
    window_key: str,
    stint_number: Optional[int],
) -> dict:
    race = session.race
    config = race.config
    state = session.tracker.state

    race_time_ms = session.race_time_ms()
    now_ms = race_time_ms or 0

    if window_key not in window_keys():
        window_key = DEFAULT_WINDOW

    window = _window(window_key, stint_number)

    drivers = {
        driver.id: driver.name
        for driver in race.drivers
    }

    # ----- nostri giri -----

    clean_ids = set()

    for stint in race.stints:
        for lap in clean_laps(get_stint_laps(race.laps, stint)):
            clean_ids.add(id(lap))

    stint_of_lap = {}

    for stint in race.stints:
        for lap in get_stint_laps(race.laps, stint):
            stint_of_lap[lap.lap_number] = stint.stint_number

    laps = [
        {
            "n": lap.lap_number,
            "t": lap.lap_time_ms,
            "rt": lap.race_time_ms,
            "d": lap.driver_id,
            "s": stint_of_lap.get(lap.lap_number),
            "k": session.kart_number(lap.kart_id),
            "clean": id(lap) in clean_ids,
        }
        for lap in race.laps
    ]

    window_laps = get_laps_for_window(
        race.laps,
        race.stints,
        window,
        now_ms=race_time_ms,
    )

    ours = _analysis(
        analyze_window(
            race.laps,
            race.stints,
            window,
            now_ms=race_time_ms,
            clean=True,
        )
    )

    # ----- concorrenti -----

    competitors = []
    neighbors = {"ahead": None, "behind": None}

    ordered = session.standings.competitors()

    for index, competitor in enumerate(ordered):
        is_us = competitor.row_id == state.row_id

        selected = get_laps_for_window(
            competitor.laps,
            competitor.stints,
            window,
            now_ms=race_time_ms,
        )

        row = {
            "row_id": competitor.row_id,
            "pos": competitor.position,
            "kart": competitor.kart_number,
            "team": competitor.team_label,
            "laps": competitor.lap_number,
            "last": competitor.last_lap_ms,
            "best": competitor.best_lap_ms,
            "gap": competitor.gap,
            "interval": competitor.interval_ms,
            "pits": competitor.pit_count,
            "in_pit": competitor.in_pit,
            "is_us": is_us,
            "window": _analysis(
                analyze_window(
                    competitor.laps,
                    competitor.stints,
                    window,
                    now_ms=race_time_ms,
                    clean=True,
                )
            ),
            "points": [
                [lap.race_time_ms, lap.lap_time_ms]
                for lap in selected
                if lap.race_time_ms is not None
            ],
        }

        competitors.append(row)

        if not is_us:
            continue

        if index > 0:
            neighbors["ahead"] = index - 1

        if index + 1 < len(ordered):
            neighbors["behind"] = index + 1

    # Solo i vicini portano i punti per il grafico.
    for index, row in enumerate(competitors):
        if index not in neighbors.values():
            row["points"] = []

    neighbor_rows = {
        side: competitors[index] if index is not None else None
        for side, index in neighbors.items()
    }

    # Il nostro intervallo è il distacco da chi ci precede; quello
    # verso chi segue è l'intervallo della sua riga.
    us = next(
        (row for row in competitors if row["is_us"]),
        None,
    )

    # ----- kart -----

    kart_ratings = rate_karts(
        {
            competitor.row_id: competitor.laps
            for competitor in ordered
        }
    )

    ratings_by_number = {
        rating.kart_number: rating
        for rating in kart_ratings
    }

    current_kart = session.current_kart()
    current_kart_number = (
        str(current_kart.number)
        if current_kart is not None
        else ""
    )

    # ----- stint e piloti -----

    stints = [
        {
            "number": item.stint_number,
            "driver_id": item.driver_id,
            "driver": drivers.get(item.driver_id, ""),
            "kart": session.kart_number(item.kart_id),
            "start_lap": item.start_lap,
            "end_lap": item.end_lap,
            "start": item.start_time_ms,
            "duration": item.duration_ms,
            "open": item.is_open,
            "pace": _pace(item.pace),
        }
        for item in stint_pace(race, now_ms)
    ]

    driver_rows = [
        {
            "id": item.driver_id,
            "name": drivers.get(item.driver_id, ""),
            "stints": item.stint_count,
            "driving": item.driving_ms,
            "pace": _pace(item.pace),
        }
        for item in driver_pace(race, now_ms)
    ]

    # ----- strategia -----

    plan = (
        plan_stints(race, race_time_ms)
        if race_time_ms is not None
        else None
    )

    plan_dict = None

    if plan is not None:
        plan_dict = {
            "stint_number": plan.stint_number,
            "stint_start": plan.stint_start_ms,
            "stint_elapsed": plan.stint_elapsed_ms,
            "stint_limit": plan.stint_limit_ms,
            "pits_done": plan.pits_done,
            "pits_remaining": plan.pits_remaining,
            "average_pit": plan.average_pit_ms,
            "target_stint": plan.target_stint_ms,
            "target_pit": plan.target_pit_ms,
            "window_open": plan.window_open_ms,
            "window_close": plan.window_close_ms,
            "unused_drivers": [
                drivers.get(driver_id, "")
                for driver_id in plan.unused_driver_ids
            ],
            "warnings": plan.warnings,
        }

    # ----- regolamento -----

    rules = [
        _rule(check_stint_duration(stint, race))
        for stint in race.stints
        if stint.end_lap is not None
    ]

    rules += [
        _rule(check_pit_duration(pit_stop.duration_ms, race))
        for pit_stop in race.pit_stops
    ]

    rules += [
        _rule(check_min_stints(race)),
        _rule(check_min_pit_stops(race)),
        _rule(check_all_drivers_used(race)),
    ]

    pit_stops = [
        {
            "lap": pit_stop.lap_before,
            "kart_out": session.kart_number(pit_stop.kart_out_id),
            "kart_in": session.kart_number(pit_stop.kart_in_id),
            "driver_out": drivers.get(pit_stop.driver_out, ""),
            "driver_in": drivers.get(pit_stop.driver_in, ""),
            "duration": pit_stop.duration_ms,
            "refuel": pit_stop.refuel,
            "tire_change": pit_stop.tire_change,
            "ok": (
                pit_stop.duration_ms is None
                or check_pit_duration(pit_stop.duration_ms, race).status
                != RuleStatus.VIOLATION
            ),
        }
        for pit_stop in race.pit_stops
    ]

    # ----- stato corrente -----

    stint = session.current_stint()
    driver = session.current_driver()

    current = None

    if stint is not None:
        rating = ratings_by_number.get(current_kart_number)

        current = {
            "stint_number": stint.stint_number,
            "driver_id": stint.driver_id,
            "driver": driver.name if driver else "",
            "kart": current_kart.number if current_kart else None,
            "kart_delta": _ms(rating.delta_ms) if rating else None,
            "kart_delta_laps": rating.lap_count if rating else 0,
            "stint_laps": len(get_stint_laps(race.laps, stint)),
        }

    pending = session.pending_pit

    pending_dict = None

    if pending is not None:
        pending_dict = {
            "lap_before": pending.lap_before,
            "in_time": pending.in_race_time_ms,
            "out_time": pending.out_race_time_ms,
            "measured": pending.measured_ms,
            "feed_kart": state.kart_number,
            "out_seen": pending.out_seen,
            "driver_id": pending.driver_id,
            "driver": (
                drivers.get(pending.driver_id)
                if pending.driver_id is not None
                else None
            ),
        }

    return {
        "team": session.team_name,
        "race_id": session.race_id,
        "source": {
            "mode": session.source_mode,
            "status": session.source_status,
            "speed": session.speed,
            "bound": state.row_id is not None,
        },
        "race": {
            "time": race_time_ms,
            "duration": config.duration_ms,
            "remaining": (
                max(0, config.duration_ms - race_time_ms)
                if race_time_ms is not None
                else None
            ),
            "title": state.session_title,
            "track": state.track_name,
            "flag": state.flag,
            "max_stint": config.max_stint_ms,
            "min_pit": config.min_pit_ms,
            "min_stints": config.min_stints,
            "min_pit_stops": config.min_pit_stops,
        },
        "feed": {
            "position": state.position,
            "gap": state.gap,
            "lap": state.lap_number,
            "kart": state.kart_number,
            "in_pit": state.in_pit,
            "interval_ahead": us["interval"] if us else None,
        },
        "window": {
            "key": window_key,
            "keys": window_keys(),
            "stint": stint_number,
            "laps": [lap.lap_number for lap in window_laps],
        },
        "drivers_list": [
            {"id": driver_id, "name": name}
            for driver_id, name in drivers.items()
        ],
        "auto_start": {
            "enabled": session.auto_start,
            "driver_id": session.start_driver_id,
            "driver": drivers.get(session.start_driver_id),
            "practice": _is_practice(state.session_title),
            "started": session.start_point is not None,
        },
        "current": current,
        "pending_pit": pending_dict,
        "pending_laps": len(session.pending_laps),
        "ours": ours,
        "laps": laps,
        "stints": stints,
        "drivers": driver_rows,
        "plan": plan_dict,
        "competitors": competitors,
        "neighbors": neighbor_rows,
        "karts": [
            {
                "number": rating.kart_number,
                "delta": _ms(rating.delta_ms),
                "laps": rating.lap_count,
                "teams": rating.team_count,
                "current": rating.kart_number == current_kart_number,
            }
            for rating in kart_ratings
        ],
        "rules": rules,
        "pit_stops": pit_stops,
        "events": [
            {
                "time": event.time_ms,
                "description": event.description,
                "penalty": event.penalty_ms,
            }
            for event in race.events
        ],
        "alerts": [
            {
                "time": alert.race_time_ms,
                "level": alert.level,
                "message": alert.message,
            }
            for alert in reversed(session.alerts[-ALERTS_SHOWN:])
        ],
    }
