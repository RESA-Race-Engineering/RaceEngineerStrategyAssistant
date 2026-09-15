from dataclasses import dataclass
from enum import Enum
import math
from typing import Optional

from core.models import Lap, Stint


class AnalysisWindowType(Enum):
    """Tipo di intervallo da analizzare."""

    LAST_LAPS = "last_laps"
    STINT = "stint"


@dataclass
class AnalysisWindow:
    """Definisce l'intervallo di giri da analizzare."""

    window_type: AnalysisWindowType
    value: int


@dataclass
class LapAnalysis:
    """Risultato dell'analisi di un insieme di giri."""

    lap_count: int
    best_lap_ms: Optional[int]
    average_lap_ms: Optional[float]
    consistency_ms: Optional[float]


def last_lap(laps: list[Lap]) -> Optional[Lap]:
    """Restituisce l'ultimo giro registrato."""

    if not laps:
        return None

    return laps[-1]


def best_lap(laps: list[Lap]) -> Optional[Lap]:
    """Restituisce il giro più veloce."""

    if not laps:
        return None

    return min(laps, key=lambda lap: lap.lap_time_ms)


def average_last_laps(
    laps: list[Lap],
    count: int,
) -> Optional[float]:
    """Calcola la media degli ultimi N giri in millisecondi."""

    if not laps or count <= 0:
        return None

    selected_laps = laps[-count:]

    total = sum(
        lap.lap_time_ms
        for lap in selected_laps
    )

    return total / len(selected_laps)


def get_last_laps(
    laps: list[Lap],
    count: int,
) -> list[Lap]:
    """Restituisce gli ultimi N giri disponibili."""

    if count <= 0:
        return []

    return laps[-count:]


def get_stint_laps(
    laps: list[Lap],
    stint: Stint,
) -> list[Lap]:
    """
    Restituisce i giri appartenenti allo stint.

    start_lap = ultimo giro completato prima dello stint
    end_lap   = ultimo giro completato alla fine dello stint
    """

    if stint.start_lap is None or stint.end_lap is None:
        return []

    return [
        lap
        for lap in laps
        if stint.start_lap < lap.lap_number <= stint.end_lap
    ]


def consistency(laps: list[Lap]) -> Optional[float]:
    """
    Calcola la deviazione standard dei tempi sul giro.

    Il risultato è espresso in millisecondi.
    Un valore più basso indica maggiore consistenza.
    """

    if not laps:
        return None

    times = [
        lap.lap_time_ms
        for lap in laps
    ]

    mean = sum(times) / len(times)

    variance = sum(
        (time - mean) ** 2
        for time in times
    ) / len(times)

    return math.sqrt(variance)


def get_laps_for_window(
    laps: list[Lap],
    stints: list[Stint],
    window: AnalysisWindow,
    kart_id: int,
) -> list[Lap]:
    """
    Seleziona i giri da analizzare per uno specifico kart.
    """

    kart_laps = [
        lap
        for lap in laps
        if lap.kart_id == kart_id
    ]

    if window.window_type == AnalysisWindowType.LAST_LAPS:
        return get_last_laps(
            kart_laps,
            window.value,
        )

    if window.window_type == AnalysisWindowType.STINT:
        for stint in stints:
            if (
                stint.stint_number == window.value
                and stint.kart_id == kart_id
            ):
                return get_stint_laps(
                    kart_laps,
                    stint,
                )

        return []

    return []

def analyze_laps(laps: list[Lap]) -> LapAnalysis:
    """
    Analizza un insieme di giri e restituisce
    tutte le principali statistiche.
    """

    if not laps:
        return LapAnalysis(
            lap_count=0,
            best_lap_ms=None,
            average_lap_ms=None,
            consistency_ms=None,
        )

    best = best_lap(laps)

    average = sum(
        lap.lap_time_ms
        for lap in laps
    ) / len(laps)

    consistency_value = consistency(laps)

    return LapAnalysis(
        lap_count=len(laps),
        best_lap_ms=best.lap_time_ms if best else None,
        average_lap_ms=average,
        consistency_ms=consistency_value,
    )

@dataclass
class DriverAnalysis:
    """Analisi delle prestazioni di un pilota."""

    driver_id: int
    lap_count: int
    best_lap_ms: Optional[int]
    average_lap_ms: Optional[float]
    consistency_ms: Optional[float]


def analyze_driver_laps(
    laps: list[Lap],
    driver_id: int,
) -> DriverAnalysis:
        """
        Analizza i giri registrati da uno specifico pilota.
        """

        driver_laps = [
        lap
        for lap in laps
        if lap.driver_id == driver_id
        ]

        analysis = analyze_laps(driver_laps)

        return DriverAnalysis(
            driver_id=driver_id,
            lap_count=analysis.lap_count,
            best_lap_ms=analysis.best_lap_ms,
            average_lap_ms=analysis.average_lap_ms,
            consistency_ms=analysis.consistency_ms,
    )


def compare_driver_analysis(
    driver_a: DriverAnalysis,
    driver_b: DriverAnalysis,
    tolerance_ms: int = 0,
) -> Optional[float]:
    """
    Confronta la media sul giro di due piloti.

    Restituisce:
    - valore positivo se B è più veloce
    - valore negativo se A è più veloce
    - 0 se la differenza rientra nella tolleranza
    - None se non è possibile confrontare i piloti
    """

    if (
        driver_a.average_lap_ms is None
        or driver_b.average_lap_ms is None
    ):
        return None

    difference = (
        driver_a.average_lap_ms
        - driver_b.average_lap_ms
    )

    if abs(difference) <= tolerance_ms:
        return 0.0

    return difference