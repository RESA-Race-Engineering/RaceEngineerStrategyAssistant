from dataclasses import dataclass
from enum import Enum
import math
import statistics
from typing import Optional, Protocol

from core.models import Lap


class AnalysisWindowType(Enum):
    """Tipo di intervallo da analizzare."""

    LAST_LAPS = "last_laps"
    STINT = "stint"
    CURRENT_STINT = "current_stint"
    LAST_TIME = "last_time"


@dataclass
class AnalysisWindow:
    """
    Definisce l'intervallo di giri da analizzare.

    Il significato di value dipende dal tipo:
    - LAST_LAPS: numero di giri
    - STINT: numero dello stint
    - CURRENT_STINT: non usato
    - LAST_TIME: durata in millisecondi
    """

    window_type: AnalysisWindowType
    value: int = 0


# Finestre del menu "Analisi". La stessa finestra vale per la nostra
# squadra, per i concorrenti e per il grafico. "Stint selezionato"
# non compare: il numero dello stint lo sceglie l'operatore.
ANALYSIS_WINDOWS = {
    "Ultimo giro": AnalysisWindow(
        window_type=AnalysisWindowType.LAST_LAPS,
        value=1,
    ),
    "Ultimi 3": AnalysisWindow(
        window_type=AnalysisWindowType.LAST_LAPS,
        value=3,
    ),
    "Ultimi 5": AnalysisWindow(
        window_type=AnalysisWindowType.LAST_LAPS,
        value=5,
    ),
    "Ultimi 10": AnalysisWindow(
        window_type=AnalysisWindowType.LAST_LAPS,
        value=10,
    ),
    "Ultimi 20": AnalysisWindow(
        window_type=AnalysisWindowType.LAST_LAPS,
        value=20,
    ),
    "Stint corrente": AnalysisWindow(
        window_type=AnalysisWindowType.CURRENT_STINT,
    ),
    "Ultimi 5 minuti": AnalysisWindow(
        window_type=AnalysisWindowType.LAST_TIME,
        value=5 * 60 * 1000,
    ),
    "Ultimi 10 minuti": AnalysisWindow(
        window_type=AnalysisWindowType.LAST_TIME,
        value=10 * 60 * 1000,
    ),
    "Ultimi 15 minuti": AnalysisWindow(
        window_type=AnalysisWindowType.LAST_TIME,
        value=15 * 60 * 1000,
    ),
}


# Un giro più lento del 107% della mediana della finestra non
# rappresenta il passo: giro con il pit, bandiera gialla, incidente.
# Un errore di guida da uno o due secondi resta dentro.
CLEAN_LAP_MAX_RATIO = 1.07


class StintRange(Protocol):
    """
    Ciò che serve per selezionare i giri di uno stint.

    Lo soddisfano sia Stint sia gli stint dei concorrenti ricostruiti
    dal live timing, di cui non si conoscono pilota e kart.
    """

    stint_number: int
    start_lap: Optional[int]
    end_lap: Optional[int]


@dataclass
class LapAnalysis:
    """Risultato dell'analisi di un insieme di giri."""

    lap_count: int
    best_lap_ms: Optional[int]
    average_lap_ms: Optional[float]
    consistency_ms: Optional[float]

    # Ultimo giro della finestra, non necessariamente della gara:
    # con uno stint passato è l'ultimo giro di quello stint.
    last_lap_ms: Optional[int] = None


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
    stint: StintRange,
) -> list[Lap]:
    """
    Restituisce i giri appartenenti allo stint.

    start_lap = ultimo giro completato prima dello stint
    end_lap   = ultimo giro completato alla fine dello stint

    Uno stint ancora aperto (end_lap None) comprende tutti i giri
    completati dopo il suo inizio.
    """

    if stint.start_lap is None:
        return []

    if stint.end_lap is None:
        return [
            lap
            for lap in laps
            if lap.lap_number > stint.start_lap
        ]

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


def get_current_stint(
    stints: list[StintRange],
) -> Optional[StintRange]:
    """
    Restituisce lo stint in corso.

    Se nessuno stint è aperto restituisce l'ultimo: durante un pit
    non ancora confermato lo stint corrente resta quello appena
    concluso in pista.
    """

    if not stints:
        return None

    open_stints = [
        stint
        for stint in stints
        if stint.end_lap is None
    ]

    return max(
        open_stints or stints,
        key=lambda stint: stint.stint_number,
    )


def get_laps_in_last(
    laps: list[Lap],
    duration_ms: int,
    now_ms: Optional[int] = None,
) -> list[Lap]:
    """
    Restituisce i giri completati negli ultimi duration_ms di gara.

    now_ms è il tempo di gara attuale: per confrontare la nostra
    squadra con i concorrenti va passato lo stesso valore a entrambi,
    così le finestre coprono lo stesso tratto di gara. Se manca si
    misura dall'ultimo giro. I giri senza race_time_ms non si possono
    collocare nel tempo e vengono esclusi.
    """

    timed_laps = [
        lap
        for lap in laps
        if lap.race_time_ms is not None
    ]

    if not timed_laps or duration_ms <= 0:
        return []

    if now_ms is None:
        now_ms = max(
            lap.race_time_ms
            for lap in timed_laps
        )

    window_start_ms = now_ms - duration_ms

    return [
        lap
        for lap in timed_laps
        if lap.race_time_ms > window_start_ms
    ]


def get_laps_for_window(
    laps: list[Lap],
    stints: list[StintRange],
    window: AnalysisWindow,
    now_ms: Optional[int] = None,
) -> list[Lap]:
    """
    Seleziona i giri della finestra indicata.

    laps e stints devono appartenere a una sola squadra: la nostra
    (race.laps, race.stints) oppure un singolo concorrente. Non si
    filtra per kart, perché il kart cambia a ogni pit: una finestra
    di giri o di tempo attraversa i cambi di kart.
    """

    if window.window_type == AnalysisWindowType.LAST_LAPS:
        return get_last_laps(
            laps,
            window.value,
        )

    if window.window_type == AnalysisWindowType.LAST_TIME:
        return get_laps_in_last(
            laps,
            duration_ms=window.value,
            now_ms=now_ms,
        )

    if window.window_type == AnalysisWindowType.CURRENT_STINT:
        stint = get_current_stint(stints)

        if stint is None:
            return []

        return get_stint_laps(
            laps,
            stint,
        )

    if window.window_type == AnalysisWindowType.STINT:
        for stint in stints:
            if stint.stint_number == window.value:
                return get_stint_laps(
                    laps,
                    stint,
                )

        return []

    return []


def clean_laps(
    laps: list[Lap],
    max_ratio: float = CLEAN_LAP_MAX_RATIO,
) -> list[Lap]:
    """
    Toglie i giri che non rappresentano il passo.

    Il riferimento è la mediana dei giri stessi, che un giro con il
    pit dentro non riesce a spostare.
    """

    if not laps:
        return []

    median_ms = statistics.median(
        lap.lap_time_ms
        for lap in laps
    )

    return [
        lap
        for lap in laps
        if lap.lap_time_ms <= median_ms * max_ratio
    ]


def lap_time_trend(laps: list[Lap]) -> Optional[float]:
    """
    Pendenza dei tempi sul giro, in millisecondi per giro.

    Retta dei minimi quadrati sui giri indicati: positiva se il passo
    peggiora (fatica, kart che cala), negativa se migliora. Servono
    almeno tre giri; conviene passare giri puliti di un solo stint.
    """

    if len(laps) < 3:
        return None

    xs = [lap.lap_number for lap in laps]
    ys = [lap.lap_time_ms for lap in laps]

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)

    spread = sum(
        (x - mean_x) ** 2
        for x in xs
    )

    if spread == 0:
        return None

    return sum(
        (x - mean_x) * (y - mean_y)
        for x, y in zip(xs, ys)
    ) / spread


def analyze_window(
    laps: list[Lap],
    stints: list[StintRange],
    window: AnalysisWindow,
    now_ms: Optional[int] = None,
    clean: bool = False,
) -> LapAnalysis:
    """
    Seleziona i giri della finestra e li analizza.

    Con clean=True media, migliore e costanza si calcolano solo sui
    giri puliti (vedi clean_laps), mentre il numero di giri e l'ultimo
    giro restano quelli della finestra.
    """

    selected = get_laps_for_window(
        laps,
        stints,
        window,
        now_ms=now_ms,
    )

    if not clean:
        return analyze_laps(selected)

    analysis = analyze_laps(clean_laps(selected))

    analysis.lap_count = len(selected)
    analysis.last_lap_ms = (
        selected[-1].lap_time_ms
        if selected
        else None
    )

    return analysis


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
        last_lap_ms=laps[-1].lap_time_ms,
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