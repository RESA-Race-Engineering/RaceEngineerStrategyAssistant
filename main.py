from core.models import (
    Race,
    RaceConfig,
    Kart,
    Team,
    Driver,
)
from core.race_logic import (
    start_stint,
    register_lap,
    register_pit_stop,
    finish_stint,
)
from core.analytics import (
    analyze_laps,
    analyze_driver_laps,
    AnalysisWindow,
    AnalysisWindowType,
    get_laps_for_window,
)
from core.rules import validate_race
from core.time_utils import format_time
from database.db import RaceDatabase


def main():
    print("=" * 60)
    print("RACE ENGINEER V1 - TEST COMPLETO")
    print("=" * 60)

    # ---------------------------------------------------------
    # 1. CONFIGURAZIONE GARA
    # ---------------------------------------------------------

    config = RaceConfig()

    print()
    print("CONFIGURAZIONE")
    print(f"Durata gara: {format_time(config.duration_ms)}")
    print(f"Piloti per team: {config.drivers_per_team}")
    print(f"Stint minimi: {config.min_stints}")
    print(f"Durata massima stint: {format_time(config.max_stint_ms)}")
    print(f"Pit stop minimi: {config.min_pit_stops}")
    print(f"Durata minima pit: {format_time(config.min_pit_ms)}")

    # ---------------------------------------------------------
    # 2. CREAZIONE GARA IN MEMORY
    # ---------------------------------------------------------

    race = Race(config=config)

    kart = Kart(
    id=1,
    number=18,
    )

    kart_2 = Kart(
        id=2,
        number=7,
    )

    team = Team(
        id=1,
        name="Our Team",
        kart_id=kart.id,
    )

    driver_1 = Driver(
        id=1,
        name="Marco",
        team_id=team.id,
    )

    driver_2 = Driver(
        id=2,
        name="Luca",
        team_id=team.id,
    )

    race.karts.append(kart)
    race.karts.append(kart_2)
    race.teams.append(team)
    race.drivers.append(driver_1)
    race.drivers.append(driver_2)

    print()
    print("GARA CREATA")
    print(f"Team: {team.name}")
    print(f"Kart: {kart.number}")
    print(f"Pilota 1: {driver_1.name}")
    print(f"Pilota 2: {driver_2.name}")

    # ---------------------------------------------------------
    # 3. DATABASE
    # ---------------------------------------------------------

    db = RaceDatabase()
    db.create_tables()

    race_id = db.create_race(
        name="Integration Test",
        duration_ms=config.duration_ms,
        created_at="2026-09-18 18:30:00",
    )

    db_team_id = db.create_team(
        race_id=race_id,
        name=team.name,
    )

    db_kart_id = db.create_kart(
        race_id=race_id,
        number=kart.number,
    )

    db_driver_1_id = db.create_driver(
        race_id=race_id,
        team_id=db_team_id,
        name=driver_1.name,
    )

    db_driver_2_id = db.create_driver(
        race_id=race_id,
        team_id=db_team_id,
        name=driver_2.name,
    )

    print()
    print("DATABASE")
    print(f"Race ID: {race_id}")
    print(f"Team ID: {db_team_id}")
    print(f"Kart ID: {db_kart_id}")
    print(f"Driver 1 ID: {db_driver_1_id}")
    print(f"Driver 2 ID: {db_driver_2_id}")

    # ---------------------------------------------------------
    # 4. STINT 1
    # ---------------------------------------------------------

    print()
    print("STINT 1")

    stint_1 = start_stint(
        race=race,
        kart_id=kart.id,
        driver_id=driver_1.id,
        start_lap=0,
        start_time_ms=0,
        db=db,
        race_id=race_id,
    )

    print(
        f"Stint {stint_1.stint_number} | "
        f"Driver {stint_1.driver_id} | "
        f"Start lap {stint_1.start_lap}"
    )

    # ---------------------------------------------------------
    # 5. REGISTRAZIONE GIRI
    # ---------------------------------------------------------

    laps_data = [
        (41, 53200, 2173200),
        (42, 53100, 2226300),
        (43, 53400, 2279700),
    ]

    for lap_number, lap_time_ms, race_time_ms in laps_data:
        lap = register_lap(
            race=race,
            kart_id=kart.id,
            lap_number=lap_number,
            lap_time_ms=lap_time_ms,
            race_time_ms=race_time_ms,
            db=db,
            race_id=race_id,
        )

        print(
            f"Giro {lap.lap_number} | "
            f"Driver {lap.driver_id} | "
            f"Tempo {lap.lap_time_ms} ms"
        )

    # ---------------------------------------------------------
    # 6. PIT STOP + CAMBIO PILOTA
    # ---------------------------------------------------------

    print()
    print("PIT STOP")

    pit = register_pit_stop(
        race=race,
        kart_id=kart.id,
        new_kart_id=kart_2.id,
        lap_before=43,
        driver_in=driver_2.id,
        duration_ms=90000,
        refuel=True,
        tire_change=False,
        db=db,
        race_id=race_id,
    )

    print(
        f"Pit dopo giro {pit.lap_before} | "
        f"Driver out {pit.driver_out} | "
        f"Driver in {pit.driver_in} | "
        f"Durata {pit.duration_ms} ms"
    )

    # ---------------------------------------------------------
    # 7. GIRO DEL NUOVO PILOTA
    # ---------------------------------------------------------

    lap = register_lap(
        race=race,
        kart_id=kart_2.id,
        lap_number=44,
        lap_time_ms=53000,
        race_time_ms=2369700,
        db=db,
        race_id=race_id,
    )

    print(
        f"Giro {lap.lap_number} | "
        f"Driver {lap.driver_id} | "
        f"Tempo {lap.lap_time_ms} ms"
    )

    # ---------------------------------------------------------
    # 8. ALTRO GIRO
    # ---------------------------------------------------------

    lap = register_lap(
        race=race,
        kart_id=kart_2.id,
        lap_number=45,
        lap_time_ms=52900,
        race_time_ms=2422600,
        db=db,
        race_id=race_id,
    )

    print(
        f"Giro {lap.lap_number} | "
        f"Driver {lap.driver_id} | "
        f"Tempo {lap.lap_time_ms} ms"
    )

    # ---------------------------------------------------------
    # 9. CHIUSURA STINT 2
    # ---------------------------------------------------------

    stint_2 = finish_stint(
        race=race,
        kart_id=kart_2.id,
        end_lap=45,
        db=db,
        race_id=race_id,
    )

    print()
    print("STINT 2 CHIUSO")

    print(
        f"Stint {stint_2.stint_number} | "
        f"Driver {stint_2.driver_id} | "
        f"Start lap {stint_2.start_lap} | "
        f"End lap {stint_2.end_lap} | "
        f"Durata {stint_2.duration_ms} ms"
    )

    # ---------------------------------------------------------
    # 10. DATI IN MEMORY
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("DATI RACE IN MEMORY")
    print("=" * 60)

    print()
    print("GIRI")

    for lap in race.laps:
        print(
            f"Giro {lap.lap_number} | "
            f"Driver {lap.driver_id} | "
            f"Kart {lap.kart_id} | "
            f"{lap.lap_time_ms} ms"
        )

    print()
    print("STINT")

    for stint in race.stints:
        print(
            f"Stint {stint.stint_number} | "
            f"Driver {stint.driver_id} | "
            f"Start lap {stint.start_lap} | "
            f"End lap {stint.end_lap} | "
            f"Durata {stint.duration_ms} ms"
        )

    print()
    print("PIT STOP")

    for pit_stop in race.pit_stops:
        print(
            f"Pit dopo giro {pit_stop.lap_before} | "
            f"Kart {pit_stop.kart_out_id} -> {pit_stop.kart_in_id} | "
            f"Driver {pit_stop.driver_out} -> {pit_stop.driver_in} | "
            f"Durata {pit_stop.duration_ms} ms"
        )

    # ---------------------------------------------------------
    # 11. ANALYTICS
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("ANALYTICS")
    print("=" * 60)

    analysis = analyze_laps(race.laps)

    print()
    print("ANALISI GENERALE")

    print(f"Giri analizzati: {analysis.lap_count}")

    if analysis.best_lap_ms is not None:
        print(
            f"Best lap: "
            f"{format_time(analysis.best_lap_ms)}"
        )

    if analysis.average_lap_ms is not None:
        print(
            f"Media: "
            f"{format_time(round(analysis.average_lap_ms))}"
        )

    if analysis.consistency_ms is not None:
        print(
            f"Consistenza: "
            f"{analysis.consistency_ms:.1f} ms"
        )

    # ---------------------------------------------------------
    # 12. ANALISI PILOTA
    # ---------------------------------------------------------

    print()
    print("ANALISI PILOTI")

    driver_1_analysis = analyze_driver_laps(
        race.laps,
        driver_1.id,
    )

    driver_2_analysis = analyze_driver_laps(
        race.laps,
        driver_2.id,
    )

    print(
        f"{driver_1.name}: "
        f"{driver_1_analysis.lap_count} giri"
    )

    if driver_1_analysis.average_lap_ms is not None:
        print(
            f"  Media: "
            f"{format_time(round(driver_1_analysis.average_lap_ms))}"
        )

    print(
        f"{driver_2.name}: "
        f"{driver_2_analysis.lap_count} giri"
    )

    if driver_2_analysis.average_lap_ms is not None:
        print(
            f"  Media: "
            f"{format_time(round(driver_2_analysis.average_lap_ms))}"
        )

    # ---------------------------------------------------------
    # 13. FINESTRA ULTIMI GIRI
    # ---------------------------------------------------------

    print()
    print("ULTIMI 3 GIRI")

    window = AnalysisWindow(
        window_type=AnalysisWindowType.LAST_LAPS,
        value=3,
    )

    last_laps = get_laps_for_window(
        laps=race.laps,
        stints=race.stints,
        window=window,
        kart_id=kart.id,
    )

    for lap in last_laps:
        print(
            f"Giro {lap.lap_number} | "
            f"{lap.lap_time_ms} ms"
        )

    # ---------------------------------------------------------
    # 14. CONTROLLO REGOLE
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("CONTROLLO REGOLE")
    print("=" * 60)

    rule_results = validate_race(race)

    for result in rule_results:
        print(
            f"{result.status.value.upper()} | "
            f"{result.rule_name} | "
            f"{result.message}"
        )

    # ---------------------------------------------------------
    # 15. LETTURA DATABASE
    # ---------------------------------------------------------

    print()
    print("=" * 60)
    print("DATI LETTI DAL DATABASE")
    print("=" * 60)

    print()
    print("GIRI DAL DATABASE")

    db_laps = db.get_laps(
        race_id=race_id,
        kart_id=db_kart_id,
    )

    for lap in db_laps:
        print(
            f"Giro {lap['lap_number']} | "
            f"Driver {lap['driver_id']} | "
            f"{lap['lap_time_ms']} ms"
        )

    print()
    print("STINT DAL DATABASE")

    db_stints = db.get_stints(
        race_id=race_id,
        kart_id=db_kart_id,
    )

    for stint in db_stints:
        print(
            f"Stint {stint['stint_number']} | "
            f"Driver {stint['driver_id']} | "
            f"Start lap {stint['start_lap']} | "
            f"End lap {stint['end_lap']} | "
            f"Start {stint['start_time_ms']} ms | "
            f"End {stint['end_time_ms']} ms"
        )

    print()
    print("PIT STOP DAL DATABASE")

    db_pits = db.get_pit_stops(
        race_id=race_id,
        kart_id=db_kart_id,
    )

    for pit in db_pits:
        print(
            f"Pit dopo giro {pit['lap_before']} | "
            f"Driver out {pit['driver_out']} | "
            f"Driver in {pit['driver_in']} | "
            f"Durata {pit['duration_ms']} ms"
        )

    # ---------------------------------------------------------
    # 16. EVENTO / PENALITÀ
    # ---------------------------------------------------------

    print()
    print("EVENTO / PENALITÀ")

    event_id = db.create_event(
        race_id=race_id,
        time_ms=2500000,
        description="Track limits",
        penalty_ms=5000,
    )

    print(f"Evento salvato con ID: {event_id}")

    db_events = db.get_events(race_id)

    for event in db_events:
        print(
            f"Tempo {event['time_ms']} ms | "
            f"{event['description']} | "
            f"Penalità {event['penalty_ms']} ms"
        )

    # ---------------------------------------------------------
    # 17. CHIUSURA
    # ---------------------------------------------------------

    db.close()

    print()
    print("=" * 60)
    print("TEST COMPLETATO")
    print("=" * 60)


if __name__ == "__main__":
    main()
