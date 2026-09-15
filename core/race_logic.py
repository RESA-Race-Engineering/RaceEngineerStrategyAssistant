from core.models import Race, Stint, PitStop, Lap


def start_stint(
    race: Race,
    kart_id: int,
    driver_id: int,
    start_lap: int = 0,
    start_time_ms: int = 0,
) -> Stint:
    """
    Crea e apre un nuovo stint per un kart.
    """

    # Controlla che il kart esista.
    kart_exists = any(
        kart.id == kart_id
        for kart in race.karts
    )

    if not kart_exists:
        raise ValueError(
            f"Il Kart {kart_id} non esiste nella gara."
        )

    # Controlla che il pilota esista.
    driver_exists = any(
        driver.id == driver_id
        for driver in race.drivers
    )

    if not driver_exists:
        raise ValueError(
            f"Il Pilota {driver_id} non esiste nella gara."
        )

    # Controlla che non esista già uno stint aperto
    # per questo kart.
    for stint in race.stints:
        if (
            stint.kart_id == kart_id
            and stint.end_lap is None
        ):
            raise ValueError(
                f"Il Kart {kart_id} ha già uno stint aperto."
            )

    # Determina il prossimo numero di stint
    # per questo kart.
    kart_stints = [
        stint
        for stint in race.stints
        if stint.kart_id == kart_id
    ]

    next_stint_number = len(kart_stints) + 1

    # Crea il nuovo stint.
    stint = Stint(
        stint_number=next_stint_number,
        driver_id=driver_id,
        kart_id=kart_id,
        start_time_ms=start_time_ms,
        end_time_ms=None,
        start_lap=start_lap,
        end_lap=None,
    )

    race.stints.append(stint)

    return stint


def register_pit_stop(
    race: Race,
    kart_id: int,
    lap_before: int,
    driver_in: int,
    duration_ms: int | None = None,
    refuel: bool = False,
    tire_change: bool = False,
) -> PitStop:
    """
    Registra un pit stop e gestisce automaticamente
    la chiusura dello stint corrente e l'apertura
    dello stint successivo.
    """

    # Trova lo stint attualmente aperto del kart.
    open_stint = None

    for stint in race.stints:
        if (
            stint.kart_id == kart_id
            and stint.end_lap is None
        ):
            open_stint = stint
            break

    if open_stint is None:
        raise ValueError(
            f"Il Kart {kart_id} non ha uno stint aperto."
        )

    # Controlla che il pit avvenga dopo
    # l'inizio dello stint.
    if (
        open_stint.start_lap is not None
        and lap_before < open_stint.start_lap
    ):
        raise ValueError(
            "Il giro del pit è precedente all'inizio dello stint."
        )

    # Controlla la durata del pit.
    if duration_ms is not None and duration_ms < 0:
        raise ValueError(
            "La durata del pit non può essere negativa."
        )

    # Controlla che il nuovo pilota esista.
    driver_exists = any(
        driver.id == driver_in
        for driver in race.drivers
    )

    if not driver_exists:
        raise ValueError(
            f"Il Pilota {driver_in} non esiste nella gara."
        )

    # Chiude lo stint corrente.
    open_stint.end_lap = lap_before

    # Il termine dello stint coincide con il completamento
    # dell'ultimo giro prima del pit.
    for lap in race.laps:
        if (
            lap.kart_id == kart_id
            and lap.lap_number == lap_before
        ):
            open_stint.end_time_ms = lap.race_time_ms
            break

    # Crea il pit stop.
    pit_stop = PitStop(
        kart_id=kart_id,
        lap_before=lap_before,
        driver_out=open_stint.driver_id,
        driver_in=driver_in,
        duration_ms=duration_ms,
        refuel=refuel,
        tire_change=tire_change,
    )

    race.pit_stops.append(pit_stop)

    # Apre automaticamente il nuovo stint.
    start_stint(
        race=race,
        kart_id=kart_id,
        driver_id=driver_in,
        start_lap=lap_before,
    )

    return pit_stop


def register_lap(
    race: Race,
    kart_id: int,
    lap_number: int,
    lap_time_ms: int,
    race_time_ms: int | None = None,
) -> Lap:
    """
    Registra un giro per un kart.

    Il pilota viene determinato automaticamente
    dallo stint attualmente aperto.
    """

    # ==============================
    # CONTROLLO KART
    # ==============================

    kart_exists = any(
        kart.id == kart_id
        for kart in race.karts
    )

    if not kart_exists:
        raise ValueError(
            f"Il Kart {kart_id} non esiste nella gara."
        )

    # ==============================
    # CONTROLLO TEMPO GIRO
    # ==============================

    if lap_time_ms <= 0:
        raise ValueError(
            "Il tempo sul giro deve essere maggiore di zero."
        )

    # ==============================
    # CONTROLLO TEMPO GARA
    # ==============================

    if race_time_ms is not None and race_time_ms < 0:
        raise ValueError(
            "Il tempo gara non può essere negativo."
        )

    # ==============================
    # CONTROLLO NUMERO GIRO
    # ==============================

    existing_lap = any(
        lap.kart_id == kart_id
        and lap.lap_number == lap_number
        for lap in race.laps
    )

    if existing_lap:
        raise ValueError(
            f"Il giro {lap_number} del Kart {kart_id} "
            "è già stato registrato."
        )

    # Trova l'ultimo giro del kart.
    kart_laps = [
        lap
        for lap in race.laps
        if lap.kart_id == kart_id
    ]

    if kart_laps:
        last_lap_number = max(
            lap.lap_number
            for lap in kart_laps
        )

        if lap_number <= last_lap_number:
            raise ValueError(
                f"Il giro {lap_number} non è valido: "
                f"l'ultimo giro registrato è il {last_lap_number}."
            )

    # ==============================
    # STINT APERTO
    # ==============================

    open_stint = None

    for stint in race.stints:
        if (
            stint.kart_id == kart_id
            and stint.end_lap is None
        ):
            open_stint = stint
            break

    if open_stint is None:
        raise ValueError(
            f"Il Kart {kart_id} non ha uno stint aperto."
        )

    # ==============================
    # CONTROLLO GIRO / STINT
    # ==============================

    if (
        open_stint.start_lap is not None
        and lap_number <= open_stint.start_lap
    ):
        raise ValueError(
            f"Il giro {lap_number} non appartiene "
            f"allo stint {open_stint.stint_number}."
        )

    # ==============================
    # TROVA PILOTA
    # ==============================

    driver_id = open_stint.driver_id

    driver = None

    for item in race.drivers:
        if item.id == driver_id:
            driver = item
            break

    if driver is None:
        raise ValueError(
            f"Pilota {driver_id} non trovato nella gara."
        )

    # ==============================
    # CREA GIRO
    # ==============================

    lap = Lap(
        lap_number=lap_number,
        lap_time_ms=lap_time_ms,
        race_time_ms=race_time_ms,
        driver_id=driver_id,
        team_id=driver.team_id,
        kart_id=kart_id,
    )

    # Se questo è il primo giro dello stint,
    # possiamo determinare automaticamente l'inizio
    # dello stint dal race time e dal lap time.
    if (
        open_stint.start_lap is not None
        and lap_number == open_stint.start_lap + 1
        and open_stint.start_time_ms == 0
        and race_time_ms is not None
    ):
        open_stint.start_time_ms = race_time_ms - lap_time_ms

    # Salva il giro.
    race.laps.append(lap)

    return lap



def finish_stint(
    race: Race,
    kart_id: int,
    end_lap: int,
    end_time_ms: int | None = None,
) -> Stint:
    open_stint = None

    for stint in race.stints:
        if stint.kart_id == kart_id and stint.end_lap is None:
            open_stint = stint
            break

    if open_stint is None:
        raise ValueError(
            f"Il Kart {kart_id} non ha uno stint aperto."
        )

    if (
        open_stint.start_lap is not None
        and end_lap <= open_stint.start_lap
    ):
        raise ValueError(
            "Il giro finale deve essere successivo "
            "al giro iniziale dello stint."
        )

    # Se non viene fornito manualmente, ricaviamo
    # il tempo di fine dallo stesso giro registrato.
    if end_time_ms is None:
        for lap in race.laps:
            if (
                lap.kart_id == kart_id
                and lap.lap_number == end_lap
            ):
                if lap.race_time_ms is None:
                    raise ValueError(
                        f"Il giro {end_lap} non ha un race_time_ms."
                    )

                end_time_ms = lap.race_time_ms
                break

    if end_time_ms is None:
        raise ValueError(
            f"Impossibile determinare il tempo di fine "
            f"dello stint dal giro {end_lap}."
        )

    open_stint.end_lap = end_lap
    open_stint.end_time_ms = end_time_ms

    return open_stint

