"""Core state types shared across SANJAYA.

Deterministic core. Plain immutable data, validated on construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .geodesy import LatLon


@dataclass(frozen=True, slots=True)
class HealthFlags:
    """Aircraft health as seen by the trigger logic. All False means healthy."""
    engine_out: bool = False
    hydraulics_lost: bool = False
    controls_unresponsive: bool = False
    fire: bool = False
    structural_failure: bool = False

    @property
    def unrecoverable(self) -> bool:
        """Conservative: any of these alone is treated as unrecoverable for v0.

        Trigger logic (Phase 9) will refine this into a multi-condition rule.
        """
        return (
            self.controls_unresponsive
            or self.structural_failure
            or self.fire
            or (self.engine_out and self.hydraulics_lost)
        )


@dataclass(frozen=True, slots=True)
class AircraftState:
    """Truth or belief about the host aircraft at time t (seconds since engine start)."""
    t: float
    pos: LatLon
    alt_m: float          # altitude above mean sea level
    speed_mps: float      # ground speed
    heading_deg: float    # true heading, [0, 360)
    fuel_kg: float
    health: HealthFlags = field(default_factory=HealthFlags)

    def __post_init__(self) -> None:
        if self.t < 0:
            raise ValueError("t must be >= 0")
        if self.speed_mps < 0:
            raise ValueError("speed must be >= 0")
        if not 0.0 <= self.heading_deg < 360.0:
            raise ValueError("heading must be in [0, 360)")
        if self.fuel_kg < 0:
            raise ValueError("fuel must be >= 0")
