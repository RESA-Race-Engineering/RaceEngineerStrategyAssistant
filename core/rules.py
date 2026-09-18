from dataclasses import dataclass
from enum import Enum

from core.models import Race, Stint


class RuleStatus(Enum):
    OK = "ok"
    WARNING = "warning"
    VIOLATION = "violation"


@dataclass
class RuleResult:
    status: RuleStatus
    rule_name: str
    message: str


def check_stint_duration(
    stint: Stint,
    race: Race,
) -> RuleResult:
    """
    Controlla che la durata dello stint non superi
    il limite massimo previsto dal regolamento.
    """

    if stint.duration_ms is None:
        return RuleResult(
            status=RuleStatus.WARNING,
            rule_name="Durata stint",
            message=(
                f"Stint {stint.stint_number}: "
                "durata non ancora disponibile."
            ),
        )

    if stint.duration_ms > race.config.max_stint_ms:
        return RuleResult(
            status=RuleStatus.VIOLATION,
            rule_name="Durata stint",
            message=(
                f"Stint {stint.stint_number}: "
                f"durata {stint.duration_ms} ms "
                f"superiore al limite di "
                f"{race.config.max_stint_ms} ms."
            ),
        )

    return RuleResult(
        status=RuleStatus.OK,
        rule_name="Durata stint",
        message=(
            f"Stint {stint.stint_number}: "
            "durata entro il limite."
        ),
    )


def check_pit_duration(
    pit_duration_ms: int | None,
    race: Race,
) -> RuleResult:
    """
    Controlla la durata minima del pit stop.
    """

    if pit_duration_ms is None:
        return RuleResult(
            status=RuleStatus.WARNING,
            rule_name="Durata pit",
            message="Durata pit non disponibile.",
        )

    if pit_duration_ms < race.config.min_pit_ms:
        return RuleResult(
            status=RuleStatus.VIOLATION,
            rule_name="Durata pit",
            message=(
                f"Pit da {pit_duration_ms} ms: "
                f"inferiore al minimo di "
                f"{race.config.min_pit_ms} ms."
            ),
        )

    return RuleResult(
        status=RuleStatus.OK,
        rule_name="Durata pit",
        message="Durata pit conforme.",
    )


def check_min_stints(race: Race) -> RuleResult:
    """
    Controlla il numero minimo di stint.
    """

    stint_count = len(race.stints)

    if stint_count < race.config.min_stints:
        return RuleResult(
            status=RuleStatus.WARNING,
            rule_name="Numero stint",
            message=(
                f"Stint effettuati: {stint_count}. "
                f"Minimo richiesto: {race.config.min_stints}."
            ),
        )

    return RuleResult(
        status=RuleStatus.OK,
        rule_name="Numero stint",
        message=(
            f"Stint effettuati: {stint_count}. "
            "Numero minimo raggiunto."
        ),
    )


def check_min_pit_stops(race: Race) -> RuleResult:
    """
    Controlla il numero minimo di pit stop.
    """

    pit_count = len(race.pit_stops)

    if pit_count < race.config.min_pit_stops:
        return RuleResult(
            status=RuleStatus.WARNING,
            rule_name="Numero pit stop",
            message=(
                f"Pit stop effettuati: {pit_count}. "
                f"Minimo richiesto: {race.config.min_pit_stops}."
            ),
        )

    return RuleResult(
        status=RuleStatus.OK,
        rule_name="Numero pit stop",
        message=(
            f"Pit stop effettuati: {pit_count}. "
            "Numero minimo raggiunto."
        ),
    )


def check_all_drivers_used(race: Race) -> RuleResult:
    """
    Controlla che tutti i piloti abbiano effettuato
    almeno uno stint.
    """

    used_driver_ids = {
        stint.driver_id
        for stint in race.stints
    }

    missing_drivers = [
        driver
        for driver in race.drivers
        if driver.id not in used_driver_ids
    ]

    if missing_drivers:
        names = ", ".join(
            driver.name
            for driver in missing_drivers
        )

        return RuleResult(
            status=RuleStatus.VIOLATION,
            rule_name="Piloti utilizzati",
            message=(
                f"Piloti che non hanno ancora guidato: {names}."
            ),
        )

    return RuleResult(
        status=RuleStatus.OK,
        rule_name="Piloti utilizzati",
        message="Tutti i piloti hanno effettuato almeno uno stint.",
    )


def validate_race(race: Race) -> list[RuleResult]:
    """
    Esegue tutti i controlli disponibili sulla gara.
    """

    results = []

    for stint in race.stints:
        results.append(
            check_stint_duration(stint, race)
        )

    for pit in race.pit_stops:
        results.append(
            check_pit_duration(
                pit.duration_ms,
                race,
            )
        )

    results.append(check_min_stints(race))
    results.append(check_min_pit_stops(race))
    results.append(check_all_drivers_used(race))

    return results