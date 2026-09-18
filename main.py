from core.models import (
    RaceConfig,
    Race,
    Team,
    Kart,
    Driver,
    RaceEvent,
)
from core.race_logic import (
    start_stint,
    register_lap,
    register_pit_stop,
    finish_stint,
)
from core.analytics import (
    AnalysisWindow,
    AnalysisWindowType,
    analyze_laps,
    analyze_driver_laps,
    get_last_laps,
)
from core.rules import validate_race
from core.time_utils import format_time
from database.db import RaceDatabase
from datetime import datetime


print("=" * 60)
print("RACE ENGINEER V1 - TEST COMPLETO")
print("=" * 60)


# ============================================================
# CONFIGURAZIONE
# ============================================================

config = RaceConfig()

print()
print("CONFIGURAZIONE")
print(f"Durata gara: {format_time(config.duration_ms)}")
print(f"Piloti per team: {config.drivers_per_team}")
print(f"Stint minimi: {config.min_stints}")
print(
    f"Durata massima stint: "
    f"{format_time(config.max_stint_ms)}"
)
print(f"Pit stop minimi: {config.min_pit_stops}")
print(
    f"Durata minima pit: "
    f"{format_time(config.min_pit_ms)}"
)


# ============================================================
# DATABASE
# ============================================================

db = RaceDatabase("data/race_engineer.db")


# ============================================================
# GARA
# ============================================================

race = Race(config=config)

team = Team(
    id=1,
    name="Our Team",
)

kart = Kart(
    id=1,
    number=18,
)

kart_2 = Kart(
    id=2,
    number=7,
)

driver_1 = Driver(
    id=1,
    name="Marco",
    team_id=1,
)

driver_2 = Driver(
    id=2,
    name="Luca",
    team_id=1,
)

race.teams.append(team)
race.karts.append(kart)
race.karts.append(kart_2)
race.drivers.append(driver_1)
race.drivers.append(driver_2)

print()
print("GARA CREATA")
print(f"Team: {team.name}")
print(f"Kart: {kart.number}")
print(f"Kart 2: {kart_2.number}")
print(f"Pilota 1: {driver_1.name}")
print(f"Pilota 2: {driver_2.name}")


# ============================================================
# SALVATAGGIO DATABASE
# ============================================================


race_id = db.create_race(
    name="Test Race",
    duration_ms=config.duration_ms,
    created_at=datetime.now().isoformat(),
)

team_db_id = db.create_team(
    race_id=race_id,
    name=team.name,
)

kart_db_id = db.create_kart(
    race_id=race_id,
    number=kart.number,
)

kart_2_db_id = db.create_kart(
    race_id=race_id,
    number=kart_2.number,
)

driver_1_db_id = db.create_driver(
    race_id=race_id,
    team_id=team_db_id,
    name=driver_1.name,
)

driver_2_db_id = db.create_driver(
    race_id=race_id,
    team_id=team_db_id,
    name=driver_2.name,
)


# Usiamo gli ID reali del database anche nei modelli in memoria.
team.id = team_db_id
kart.id = kart_db_id
kart_2.id = kart_2_db_id
driver_1.id = driver_1_db_id
driver_2.id = driver_2_db_id

print()
print("DATABASE")
print(f"Race ID: {race_id}")
print(f"Team ID: {team.id}")
print(f"Kart 1 ID: {kart.id}")
print(f"Kart 2 ID: {kart_2.id}")
print(f"Driver 1 ID: {driver_1.id}")
print(f"Driver 2 ID: {driver_2.id}")


# ============================================================
# STINT 1
# ============================================================

print()
print("STINT 1")

stint_1 = start_stint(
    race=race,
    kart_id=kart.id,
    driver_id=driver_1.id,
    start_lap=0,
    db=db,
    race_id=race_id,
)

print(
    f"Stint {stint_1.stint_number} | "
    f"Driver {stint_1.driver_id} | "
    f"Start lap {stint_1.start_lap}"
)


# ============================================================
# GIRI KART 1
# ============================================================

lap_41 = register_lap(
    race=race,
    kart_id=kart.id,
    lap_number=41,
    lap_time_ms=53200,
    race_time_ms=2200000,
    db=db,
    race_id=race_id,
)

print(
    f"Giro {lap_41.lap_number} | "
    f"Driver {lap_41.driver_id} | "
    f"Tempo {lap_41.lap_time_ms} ms"
)

lap_42 = register_lap(
    race=race,
    kart_id=kart.id,
    lap_number=42,
    lap_time_ms=53100,
    race_time_ms=2253200,
    db=db,
    race_id=race_id,
)

print(
    f"Giro {lap_42.lap_number} | "
    f"Driver {lap_42.driver_id} | "
    f"Tempo {lap_42.lap_time_ms} ms"
)

lap_43 = register_lap(
    race=race,
    kart_id=kart.id,
    lap_number=43,
    lap_time_ms=53400,
    race_time_ms=2306500,
    db=db,
    race_id=race_id,
)

print(
    f"Giro {lap_43.lap_number} | "
    f"Driver {lap_43.driver_id} | "
    f"Tempo {lap_43.lap_time_ms} ms"
)


# ============================================================
# PIT STOP + CAMBIO KART
# ============================================================

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
    f"Kart {pit.kart_out_id} -> {pit.kart_in_id} | "
    f"Driver {pit.driver_out} -> {pit.driver_in} | "
    f"Durata {pit.duration_ms} ms"
)


# ============================================================
# GIRI KART 2
# ============================================================

lap_44 = register_lap(
    race=race,
    kart_id=kart_2.id,
    lap_number=44,
    lap_time_ms=53000,
    race_time_ms=2440000,
    db=db,
    race_id=race_id,
)

print(
    f"Giro {lap_44.lap_number} | "
    f"Driver {lap_44.driver_id} | "
    f"Tempo {lap_44.lap_time_ms} ms"
)

lap_45 = register_lap(
    race=race,
    kart_id=kart_2.id,
    lap_number=45,
    lap_time_ms=52900,
    race_time_ms=2492900,
    db=db,
    race_id=race_id,
)

print(
    f"Giro {lap_45.lap_number} | "
    f"Driver {lap_45.driver_id} | "
    f"Tempo {lap_45.lap_time_ms} ms"
)


# ============================================================
# CHIUSURA STINT 2
# ============================================================

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


# ============================================================
# DATI RACE IN MEMORY
# ============================================================

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
        f"Kart {stint.kart_id} | "
        f"Start lap {stint.start_lap} | "
        f"End lap {stint.end_lap} | "
        f"Durata {stint.duration_ms} ms"
    )


print()
print("PIT STOP")

for pit_stop in race.pit_stops:
    print(
        f"Pit dopo giro {pit_stop.lap_before} | "
        f"Kart {pit_stop.kart_out_id} -> "
        f"{pit_stop.kart_in_id} | "
        f"Driver {pit_stop.driver_out} -> "
        f"{pit_stop.driver_in} | "
        f"Durata {pit_stop.duration_ms} ms"
    )


# ============================================================
# ANALYTICS
# ============================================================

print()
print("=" * 60)
print("ANALYTICS")
print("=" * 60)

print()
print("ANALISI GENERALE")

analysis = analyze_laps(race.laps)

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


# ============================================================
# ANALISI PILOTI
# ============================================================

print()
print("ANALISI PILOTI")

driver_1_analysis = analyze_driver_laps(
    laps=race.laps,
    driver_id=driver_1.id,
)

driver_2_analysis = analyze_driver_laps(
    laps=race.laps,
    driver_id=driver_2.id,
)

print(f"{driver_1.name}: {driver_1_analysis.lap_count} giri")

if driver_1_analysis.average_lap_ms is not None:
    print(
        f"  Media: "
        f"{format_time(round(driver_1_analysis.average_lap_ms))}"
    )

print(f"{driver_2.name}: {driver_2_analysis.lap_count} giri")

if driver_2_analysis.average_lap_ms is not None:
    print(
        f"  Media: "
        f"{format_time(round(driver_2_analysis.average_lap_ms))}"
    )


# ============================================================
# ULTIMI 3 GIRI
# ============================================================

print()
print("ULTIMI 3 GIRI")

last_laps = get_last_laps(
    laps=race.laps,
    count=3,
)

for lap in last_laps:
    print(
        f"Giro {lap.lap_number} | "
        f"{lap.lap_time_ms} ms"
    )


# ============================================================
# CONTROLLO REGOLE
# ============================================================

print()
print("=" * 60)
print("CONTROLLO REGOLE")
print("=" * 60)

results = validate_race(race)

for result in results:
    print(
        f"{result.status.name} | "
        f"{result.rule_name} | "
        f"{result.message}"
    )


# ============================================================
# EVENTO / PENALITÀ
# ============================================================

print()
print("EVENTO / PENALITÀ")

event = RaceEvent(
    time_ms=2500000,
    description="Track limits",
    penalty_ms=5000,
)

event_id = db.create_event(
    race_id=race_id,
    time_ms=event.time_ms,
    description=event.description,
    penalty_ms=event.penalty_ms,
)

race.events.append(event)

print(
    f"Evento salvato con ID: {event_id}"
)

print(
    f"Tempo {event.time_ms} ms | "
    f"{event.description} | "
    f"Penalità {event.penalty_ms} ms"
)


# ============================================================
# DATI LETTI DAL DATABASE
# ============================================================

print()
print("=" * 60)
print("DATI LETTI DAL DATABASE")
print("=" * 60)


# ------------------------------------------------------------
# GIRI
# ------------------------------------------------------------

print()
print("GIRI DAL DATABASE")

db_laps = db.get_laps(race_id)

for row in db_laps:
    print(
        f"Giro {row['lap_number']} | "
        f"Driver {row['driver_id']} | "
        f"Kart {row['kart_id']} | "
        f"{row['lap_time_ms']} ms"
    )


# ------------------------------------------------------------
# STINT
# ------------------------------------------------------------

print()
print("STINT DAL DATABASE")

db_stints = db.get_stints(race_id)

for row in db_stints:
    print(
        f"Stint {row['stint_number']} | "
        f"Driver {row['driver_id']} | "
        f"Kart {row['kart_id']} | "
        f"Start lap {row['start_lap']} | "
        f"End lap {row['end_lap']} | "
        f"Start {row['start_time_ms']} ms | "
        f"End {row['end_time_ms']} ms"
    )


# ------------------------------------------------------------
# PIT STOP
# ------------------------------------------------------------

print()
print("PIT STOP DAL DATABASE")

db_pits = db.get_pit_stops(race_id)

for row in db_pits:
    print(
        f"Pit dopo giro {row['lap_before']} | "
        f"Kart {row['kart_out_id']} -> "
        f"{row['kart_in_id']} | "
        f"Driver {row['driver_out']} -> "
        f"{row['driver_in']} | "
        f"Durata {row['duration_ms']} ms"
    )


# ------------------------------------------------------------
# EVENTI
# ------------------------------------------------------------

print()
print("EVENTI DAL DATABASE")

db_events = db.get_events(race_id)

for row in db_events:
    print(
        f"Tempo {row['time_ms']} ms | "
        f"{row['description']} | "
        f"Penalità {row['penalty_ms']} ms"
    )


# ============================================================
# CHIUSURA
# ============================================================

db.close()

print()
print("=" * 60)
print("TEST COMPLETATO")
print("=" * 60)