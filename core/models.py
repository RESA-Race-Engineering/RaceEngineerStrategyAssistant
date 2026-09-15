from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RaceConfig:
    """Configurazione della gara."""

    duration_ms: int = 360 * 60 * 1000
    drivers_per_team: int = 6
    min_stints: int = 15
    max_stint_ms: int = 45 * 60 * 1000
    min_pit_stops: int = 14
    min_pit_ms: int = 90 * 1000

    driver_comparison_tolerance_ms: int = 40


@dataclass
class Kart:
    """Kart utilizzato da una squadra."""

    id: int
    number: int


@dataclass
class Team:
    """Squadra partecipante alla gara."""

    id: int
    name: str
    kart_id: Optional[int] = None


@dataclass
class Driver:
    """Pilota."""

    id: int
    name: str
    team_id: int


@dataclass
class Lap:
    """Singolo giro cronometrato."""

    lap_number: int
    lap_time_ms: int

    # Momento della gara in cui il giro è stato completato.
    # È il riferimento temporale assoluto della gara.
    race_time_ms: Optional[int] = None

    driver_id: Optional[int] = None
    team_id: Optional[int] = None
    kart_id: Optional[int] = None


@dataclass
class Stint:
    """Stint di un pilota."""

    stint_number: int
    driver_id: int
    kart_id: int

    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None

    start_lap: Optional[int] = None
    end_lap: Optional[int] = None

    @property
    def duration_ms(self) -> Optional[int]:
        """Durata dello stint in millisecondi."""

        if self.start_time_ms is None or self.end_time_ms is None:
            return None

        return self.end_time_ms - self.start_time_ms

    @property
    def laps_completed(self) -> Optional[int]:
        """Numero di giri completati nello stint."""

        if self.start_lap is None or self.end_lap is None:
            return None

        return self.end_lap - self.start_lap


@dataclass
class PitStop:
    """Pit stop / cambio pilota."""

    kart_id: int
    lap_before: int

    driver_out: Optional[int] = None
    driver_in: Optional[int] = None

    duration_ms: Optional[int] = None

    refuel: bool = False
    tire_change: bool = False


@dataclass
class RaceEvent:
    """Evento avvenuto durante la gara."""

    time_ms: int
    description: str
    penalty_ms: int = 0


@dataclass
class Race:
    """Rappresenta una gara."""

    config: RaceConfig

    teams: list[Team] = field(default_factory=list)
    karts: list[Kart] = field(default_factory=list)
    drivers: list[Driver] = field(default_factory=list)

    laps: list[Lap] = field(default_factory=list)
    stints: list[Stint] = field(default_factory=list)
    pit_stops: list[PitStop] = field(default_factory=list)
    events: list[RaceEvent] = field(default_factory=list)