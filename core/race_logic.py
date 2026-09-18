from core.models import Race, Stint, PitStop, Lap


def start_stint(
    race: Race,
    kart_id: int,
    driver_id: int,
    start_lap: int = 0,
    start_time_ms: int = 0,
    db=None,
    race_id: int | None = None,
) -> Stint:
    """Avvia un nuovo stint."""

    kart_exists = any(
        kart.id == kart_id
        for kart in race.karts
    )

    if not kart_exists:
        raise ValueError(
            f"Il Kart {kart_id} non esiste nella gara."
        )

    driver_exists = any(
        driver.id == driver_id
        for driver in race.drivers
    )

    if not driver_exists:
        raise ValueError(
            f"Il Pilota {driver_id} non esiste nella gara."
        )

    for stint in race.stints:
        if (
            stint.kart_id == kart_id
            and stint.end_lap is None
        ):
            raise ValueError(
                f"Il Kart {kart_id} ha già uno stint aperto."
            )

    next_stint_number = len(race.stints) + 1

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

    # Salvataggio DB.
    # Lo stint può essere aperto, quindi end_time/end_lap sono NULL.
    if db is not None and race_id is not None:
        db.create_stint(
            race_id=race_id,
            stint_number=stint.stint_number,
            kart_id=stint.kart_id,
            driver_id=stint.driver_id,
            start_time_ms=stint.start_time_ms,
            end_time_ms=stint.end_time_ms,
            start_lap=stint.start_lap,
            end_lap=stint.end_lap,
        )

    return stint


def register_pit_stop(
    race: Race,
    kart_id: int,
    new_kart_id: int,
    lap_before: int,
    driver_in: int,
    duration_ms: int | None = None,
    refuel: bool = False,
    tire_change: bool = False,
    db=None,
    race_id: int | None = None,
) -> PitStop:
    # ---------------------------------------------------------
    # Verifica kart attuale
    # ---------------------------------------------------------

    current_kart_exists = any(
        kart.id == kart_id
        for kart in race.karts
    )

    if not current_kart_exists:
        raise ValueError(
            f"Il Kart attuale {kart_id} non esiste nella gara."
        )

    # ---------------------------------------------------------
    # Verifica nuovo kart
    # ---------------------------------------------------------

    new_kart_exists = any(
        kart.id == new_kart_id
        for kart in race.karts
    )

    if not new_kart_exists:
        raise ValueError(
            f"Il nuovo Kart {new_kart_id} non esiste nella gara."
        )

    # ---------------------------------------------------------
    # Verifica pilota
    # ---------------------------------------------------------

    driver_exists = any(
        driver.id == driver_in
        for driver in race.drivers
    )

    if not driver_exists:
        raise ValueError(
            f"Il Pilota {driver_in} non esiste nella gara."
        )

    # ---------------------------------------------------------
    # Trova lo stint aperto del kart attuale
    # ---------------------------------------------------------

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

    # ---------------------------------------------------------
    # Controllo giro pit
    # ---------------------------------------------------------

    if (
        open_stint.start_lap is not None
        and lap_before < open_stint.start_lap
    ):
        raise ValueError(
            "Il giro del pit è precedente "
            "all'inizio dello stint."
        )

    # ---------------------------------------------------------
    # Controllo durata pit
    # ---------------------------------------------------------

    if duration_ms is not None and duration_ms < 0:
        raise ValueError(
            "La durata del pit non può essere negativa."
        )

    # ---------------------------------------------------------
    # Chiudi stint precedente
    # ---------------------------------------------------------

    open_stint.end_lap = lap_before

    for lap in race.laps:
        if (
            lap.kart_id == kart_id
            and lap.lap_number == lap_before
        ):
            open_stint.end_time_ms = lap.race_time_ms
            break

    # ---------------------------------------------------------
    # Crea PitStop
    # ---------------------------------------------------------

    pit_stop = PitStop(
        kart_out_id=kart_id,
        kart_in_id=new_kart_id,
        lap_before=lap_before,
        driver_out=open_stint.driver_id,
        driver_in=driver_in,
        duration_ms=duration_ms,
        refuel=refuel,
        tire_change=tire_change,
    )

    race.pit_stops.append(pit_stop)

    # ---------------------------------------------------------
    # Database: chiusura stint precedente
    # ---------------------------------------------------------

    if db is not None and race_id is not None:
        db.update_stint_end(
            race_id=race_id,
            kart_id=kart_id,
            stint_number=open_stint.stint_number,
            end_time_ms=open_stint.end_time_ms,
            end_lap=open_stint.end_lap,
        )

        # -----------------------------------------------------
        # Database: salva pit stop
        # -----------------------------------------------------

        db.create_pit_stop(
            race_id=race_id,
            kart_out_id=pit_stop.kart_out_id,
            kart_in_id=pit_stop.kart_in_id,
            lap_before=pit_stop.lap_before,
            driver_out=pit_stop.driver_out,
            driver_in=pit_stop.driver_in,
            duration_ms=pit_stop.duration_ms,
            refuel=pit_stop.refuel,
            tire_change=pit_stop.tire_change,
        )

    # ---------------------------------------------------------
    # Apri nuovo stint
    # ---------------------------------------------------------

    start_stint(
        race=race,
        kart_id=new_kart_id,
        driver_id=driver_in,
        start_lap=lap_before,
        db=db,
        race_id=race_id,
    )

    return pit_stop


def register_lap(
    race: Race,
    kart_id: int,
    lap_number: int,
    lap_time_ms: int,
    race_time_ms: int | None = None,
    db=None,
    race_id: int | None = None,
) -> Lap:
    """Registra un giro e, se presente, lo salva nel database."""

    kart_exists = any(
        kart.id == kart_id
        for kart in race.karts
    )

    if not kart_exists:
        raise ValueError(
            f"Il Kart {kart_id} non esiste nella gara."
        )

    if lap_time_ms <= 0:
        raise ValueError(
            "Il tempo sul giro deve essere maggiore di zero."
        )

    if (
        race_time_ms is not None
        and race_time_ms < 0
    ):
        raise ValueError(
            "Il tempo gara non può essere negativo."
        )

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
                f"l'ultimo giro registrato è "
                f"il {last_lap_number}."
            )

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

    if (
        open_stint.start_lap is not None
        and lap_number <= open_stint.start_lap
    ):
        raise ValueError(
            f"Il giro {lap_number} non appartiene "
            f"allo stint {open_stint.stint_number}."
        )

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

    lap = Lap(
        lap_number=lap_number,
        lap_time_ms=lap_time_ms,
        race_time_ms=race_time_ms,
        driver_id=driver_id,
        team_id=driver.team_id,
        kart_id=kart_id,
    )

    # Se è il primo giro dello stint, possiamo ricavare
    # l'istante di partenza dello stint.
    if (
        open_stint.start_lap is not None
        and lap_number == open_stint.start_lap + 1
        and open_stint.start_time_ms == 0
        and race_time_ms is not None
    ):
        open_stint.start_time_ms = (
            race_time_ms - lap_time_ms
        )

    race.laps.append(lap)

    # Salvataggio DB.
    if db is not None and race_id is not None:
        db.create_lap(
            race_id=race_id,
            kart_id=lap.kart_id,
            driver_id=lap.driver_id,
            team_id=lap.team_id,
            lap_number=lap.lap_number,
            lap_time_ms=lap.lap_time_ms,
            race_time_ms=lap.race_time_ms,
        )

        # Se questo è il primo giro di uno stint,
        # aggiorniamo il suo start_time nel DB.
        if (
            open_stint.start_lap is not None
            and lap_number == open_stint.start_lap + 1
            and open_stint.start_time_ms == (
                race_time_ms - lap_time_ms
                if race_time_ms is not None
                else 0
            )
        ):
            db.update_stint_start(
                race_id=race_id,
                kart_id=kart_id,
                stint_number=open_stint.stint_number,
                start_time_ms=open_stint.start_time_ms,
            )

    return lap


def finish_stint(
    race: Race,
    kart_id: int,
    end_lap: int,
    end_time_ms: int | None = None,
    db=None,
    race_id: int | None = None,
) -> Stint:
    """Chiude lo stint attualmente aperto."""

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

    if (
        open_stint.start_lap is not None
        and end_lap <= open_stint.start_lap
    ):
        raise ValueError(
            "Il giro finale deve essere successivo "
            "al giro iniziale dello stint."
        )

    if end_time_ms is None:
        for lap in race.laps:
            if (
                lap.kart_id == kart_id
                and lap.lap_number == end_lap
            ):
                if lap.race_time_ms is None:
                    raise ValueError(
                        f"Il giro {end_lap} non ha "
                        "un race_time_ms."
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

    if db is not None and race_id is not None:
        db.update_stint_end(
            race_id=race_id,
            kart_id=kart_id,
            stint_number=open_stint.stint_number,
            end_time_ms=open_stint.end_time_ms,
            end_lap=open_stint.end_lap,
        )

    return open_stint
