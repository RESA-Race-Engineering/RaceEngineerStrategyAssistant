from core.models import (
    RaceConfig,
    Kart,
    Team,
    Driver,
    Race,
)

from core.race_logic import (
    start_stint,
    register_pit_stop,
    register_lap,
    finish_stint,
)

from core.analytics import (
    last_lap,
    best_lap,
    average_last_laps,
    consistency,
    analyze_laps,
    get_stint_laps,
    analyze_driver_laps,
    compare_driver_analysis,
    DriverAnalysis,
)


def main():

    # ==============================
    # CONFIGURAZIONE GARA
    # ==============================

    config = RaceConfig()

    # ==============================
    # KART
    # ==============================

    our_kart = Kart(
        id=1,
        number=18,
    )

    # ==============================
    # TEAM
    # ==============================

    our_team = Team(
        id=1,
        name="Our Team",
        kart_id=our_kart.id,
    )

    # ==============================
    # PILOTI
    # ==============================

    driver_1 = Driver(
        id=1,
        name="Marco",
        team_id=our_team.id,
    )

    driver_2 = Driver(
        id=2,
        name="Luca",
        team_id=our_team.id,
    )

    # ==============================
    # GARA
    # ==============================

    race = Race(
        config=config,
        teams=[our_team],
        karts=[our_kart],
        drivers=[driver_1, driver_2],
    )

    # ==============================
    # STINT 1
    # ==============================

    start_stint(
        race=race,
        kart_id=our_kart.id,
        driver_id=driver_1.id,
    )

    # ==============================
    # GIRI DI MARCO
    # ==============================

    register_lap(
        race=race,
        kart_id=our_kart.id,
        lap_number=41,
        lap_time_ms=53_200,
        race_time_ms=2_173_200,
    )

    register_lap(
        race=race,
        kart_id=our_kart.id,
        lap_number=42,
        lap_time_ms=53_100,
        race_time_ms=2_226_300,
    )

    register_lap(
        race=race,
        kart_id=our_kart.id,
        lap_number=43,
        lap_time_ms=53_400,
        race_time_ms=2_279_700,
    )

    # ==============================
    # PIT → CAMBIO A LUCA
    # ==============================

    register_pit_stop(
        race=race,
        kart_id=our_kart.id,
        lap_before=43,
        driver_in=driver_2.id,
        duration_ms=90_000,
    )

    # ==============================
    # GIRI DI LUCA
    # ==============================

    register_lap(
        race=race,
        kart_id=our_kart.id,
        lap_number=44,
        lap_time_ms=53_000,
        race_time_ms=2_369_700,
    )

    register_lap(
        race=race,
        kart_id=our_kart.id,
        lap_number=45,
        lap_time_ms=52_900,
        race_time_ms=2_422_600,
    )

    # ==============================
    # TEST GIRO DUPLICATO
    # ==============================

    print()
    print("TEST GIRO DUPLICATO")

    try:
        register_lap(
            race=race,
            kart_id=our_kart.id,
            lap_number=45,
            lap_time_ms=52_800,
        )

        print(
            "ERRORE - Il giro duplicato "
            "è stato accettato"
        )

    except ValueError as error:
        print(
            f"OK - Giro duplicato rifiutato: {error}"
        )

    # ==============================
    # TEST FINE STINT
    # ==============================

    print()
    print("TEST FINE STINT")

    finished_stint = finish_stint(
        race=race,
        kart_id=1,
        end_lap=45,
    )

    print(
        f"Stint {finished_stint.stint_number} | "
        f"Driver {finished_stint.driver_id} | "
        f"Start lap {finished_stint.start_lap} | "
        f"End lap {finished_stint.end_lap} | "
        f"End time {finished_stint.end_time_ms} ms"
    )

    if (
        finished_stint.end_lap == 45
        and finished_stint.end_time_ms == 2_422_600
    ):
        print("OK - Stint chiuso correttamente")
    else:
        print("ERRORE - Chiusura stint non corretta")

    # ==============================
    # RISULTATO REGISTRAZIONE GIRI
    # ==============================

    print("========================================")
    print("TEST REGISTRAZIONE GIRI")
    print("========================================")

    print()

    for lap in race.laps:

        driver_name = "SCONOSCIUTO"

        for driver in race.drivers:
            if driver.id == lap.driver_id:
                driver_name = driver.name
                break

        print(
            f"Giro {lap.lap_number} | "
            f"Lap time {lap.lap_time_ms} ms | "
            f"Race time {lap.race_time_ms} ms | "
            f"Pilota {driver_name} | "
            f"Driver ID {lap.driver_id}"
        )

    print()

    # ==============================
    # VERIFICA ASSEGNAZIONE PILOTI
    # ==============================

    expected = [
        (41, driver_1.id),
        (42, driver_1.id),
        (43, driver_1.id),
        (44, driver_2.id),
        (45, driver_2.id),
    ]

    result = [
        (lap.lap_number, lap.driver_id)
        for lap in race.laps
    ]

    if result == expected:
        print(
            "OK - I giri sono stati assegnati "
            "ai piloti corretti"
        )
    else:
        print(
            "ERRORE - Assegnazione dei piloti "
            "non corretta"
        )

    # ==============================
    # TEST DATI STINT
    # ==============================

    print()
    print("TEST DATI STINT")

    print(
        f"Stint {finished_stint.stint_number}"
    )

    print(
        f"Giri completati: "
        f"{finished_stint.laps_completed}"
    )

    print(
        f"Durata: "
        f"{finished_stint.duration_ms} ms"
    )

    if finished_stint.laps_completed == 2:
        print(
            "OK - Numero giri dello stint corretto"
        )
    else:
        print(
            "ERRORE - Numero giri dello stint errato"
        )

    print()
    print("TEMPI STINT")

    print(
        f"Stint 1 | "
        f"Start: {race.stints[0].start_time_ms} ms | "
        f"End: {race.stints[0].end_time_ms} ms | "
        f"Durata: {race.stints[0].duration_ms} ms"
    )

    print(
        f"Stint 2 | "
        f"Start: {race.stints[1].start_time_ms} ms | "
        f"End: {race.stints[1].end_time_ms} ms | "
        f"Durata: {race.stints[1].duration_ms} ms"
    )

    if finished_stint.duration_ms == 105_900:
        print(
            "OK - Durata dello stint corretta"
        )
    else:
        print(
            "ERRORE - Durata dello stint errata"
        )

    # ==============================
    # TEST ANALISI GIRI
    # ==============================

    print()
    print("TEST ANALISI GIRI")

    kart_laps = [
        lap
        for lap in race.laps
        if lap.kart_id == our_kart.id
    ]

    print(
        f"Giri disponibili: {len(kart_laps)}"
    )

    last = last_lap(kart_laps)
    best = best_lap(kart_laps)
    average_3 = average_last_laps(
        kart_laps,
        3,
    )
    consistency_value = consistency(
        kart_laps
    )

    print(
        f"Ultimo giro: "
        f"{last.lap_number} - "
        f"{last.lap_time_ms} ms"
    )

    print(
        f"Miglior giro: "
        f"{best.lap_number} - "
        f"{best.lap_time_ms} ms"
    )

    print(
        f"Media ultimi 3: "
        f"{average_3:.2f} ms"
    )

    print(
        f"Consistenza: "
        f"{consistency_value:.2f} ms"
    )

    # ==============================
    # TEST ANALISI PER STINT
    # ==============================

    print()
    print("TEST ANALISI PER STINT")

    stint_1 = race.stints[0]
    stint_2 = race.stints[1]

    stint_1_laps = get_stint_laps(
        race.laps,
        stint_1,
    )

    stint_2_laps = get_stint_laps(
        race.laps,
        stint_2,
    )

    print()
    print("STINT 1")

    for lap in stint_1_laps:
        print(
            f"Giro {lap.lap_number} | "
            f"{lap.lap_time_ms} ms"
        )

    print()
    print("STINT 2")

    for lap in stint_2_laps:
        print(
            f"Giro {lap.lap_number} | "
            f"{lap.lap_time_ms} ms"
        )

    if (
        [lap.lap_number for lap in stint_1_laps]
        == [41, 42, 43]
    ):
        print(
            "OK - Stint 1 contiene "
            "i giri corretti"
        )
    else:
        print(
            "ERRORE - Stint 1 errato"
        )

    if (
        [lap.lap_number for lap in stint_2_laps]
        == [44, 45]
    ):
        print(
            "OK - Stint 2 contiene "
            "i giri corretti"
        )
    else:
        print(
            "ERRORE - Stint 2 errato"
        )

    # ==============================
    # TEST ANALISI COMPLETA STINT
    # ==============================

    print()
    print("TEST ANALISI COMPLETA STINT")

    stint_1_analysis = analyze_laps(
        stint_1_laps
    )

    stint_2_analysis = analyze_laps(
        stint_2_laps
    )

    print()
    print("STINT 1")

    print(
        f"Giri: "
        f"{stint_1_analysis.lap_count}"
    )

    print(
        f"Best: "
        f"{stint_1_analysis.best_lap_ms} ms"
    )

    print(
        f"Media: "
        f"{stint_1_analysis.average_lap_ms:.2f} ms"
    )

    print(
        f"Consistenza: "
        f"{stint_1_analysis.consistency_ms:.2f} ms"
    )

    print()
    print("STINT 2")

    print(
        f"Giri: "
        f"{stint_2_analysis.lap_count}"
    )

    print(
        f"Best: "
        f"{stint_2_analysis.best_lap_ms} ms"
    )

    print(
        f"Media: "
        f"{stint_2_analysis.average_lap_ms:.2f} ms"
    )

    print(
        f"Consistenza: "
        f"{stint_2_analysis.consistency_ms:.2f} ms"
    )

    # ==============================
    # TEST ANALISI PILOTI
    # ==============================

    print()
    print("TEST ANALISI PILOTI")

    marco_analysis = analyze_driver_laps(
        race.laps,
        driver_1.id,
    )

    luca_analysis = analyze_driver_laps(
        race.laps,
        driver_2.id,
    )

    print()
    print("MARCO")

    print(
        f"Giri: "
        f"{marco_analysis.lap_count}"
    )

    print(
        f"Best: "
        f"{marco_analysis.best_lap_ms} ms"
    )

    print(
        f"Media: "
        f"{marco_analysis.average_lap_ms:.2f} ms"
    )

    print(
        f"Consistenza: "
        f"{marco_analysis.consistency_ms:.2f} ms"
    )

    print()
    print("LUCA")

    print(
        f"Giri: "
        f"{luca_analysis.lap_count}"
    )

    print(
        f"Best: "
        f"{luca_analysis.best_lap_ms} ms"
    )

    print(
        f"Media: "
        f"{luca_analysis.average_lap_ms:.2f} ms"
    )

    print(
        f"Consistenza: "
        f"{luca_analysis.consistency_ms:.2f} ms"
    )

    # ==============================
    # TEST CONFRONTO PILOTI
    # ==============================

    print()
    print("TEST CONFRONTO PILOTI")

    difference = compare_driver_analysis(
        marco_analysis,
        luca_analysis,
        race.config.driver_comparison_tolerance_ms,
    )

    print(
        f"Differenza media: "
        f"{difference:.2f} ms/giro"
    )

    if difference > 0:
        print(
            "OK - Luca è più veloce di Marco"
        )
    elif difference < 0:
        print(
            "OK - Marco è più veloce di Luca"
        )
    else:
        print(
            "OK - I piloti sono equivalenti"
        )

    # ==============================
    # TEST TOLLERANZA CONFRONTO
    # ==============================

    print()
    print("TEST TOLLERANZA CONFRONTO")

    test_driver_a = DriverAnalysis(
        driver_id=1,
        lap_count=10,
        best_lap_ms=52_900,
        average_lap_ms=53_000,
        consistency_ms=50,
    )

    test_driver_b = DriverAnalysis(
        driver_id=2,
        lap_count=10,
        best_lap_ms=52_950,
        average_lap_ms=53_030,
        consistency_ms=55,
    )

    test_difference = compare_driver_analysis(
        test_driver_a,
        test_driver_b,
        race.config.driver_comparison_tolerance_ms,
    )

    print(
        f"Differenza: "
        f"{test_difference:.2f} ms/giro"
    )

    if test_difference == 0:
        print(
            "OK - Differenza entro la tolleranza: "
            "piloti equivalenti"
        )
    else:
        print(
            "ERRORE - La tolleranza "
            "non è stata applicata"
        )


if __name__ == "__main__":
    main()
