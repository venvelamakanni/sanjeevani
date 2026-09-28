"""International Standard Atmosphere with a temperature offset.

Deterministic core. Pure functions, SI units, altitudes in metres.

Inputs are geometric altitude above mean sea level, the same datum as the DEM
and AircraftState.alt_m. They are converted to geopotential altitude internally,
which is what the standard tables are defined on. Skipping that step would put
pressure off by 0.25% at 10 km and 0.56% at 15 km.

Temperature offset (ISA+dT) is how hot or cold the day is. Pressure follows the
standard profile; density comes from the ideal gas law at the actual temperature.
The Thar in summer runs ISA+15 to ISA+30, which is why density altitude matters.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

G0 = 9.80665            # m/s^2
R_AIR = 287.05287       # J/(kg K)
T0 = 288.15             # K, sea-level ISA temperature
P0 = 101_325.0          # Pa
RHO0 = P0 / (R_AIR * T0)   # 1.2250 kg/m^3
LAPSE = 0.0065          # K/m, troposphere
H_TROPOPAUSE = 11_000.0
H_TOP = 20_000.0        # model ceiling (geometric); the isothermal layer ends near here
R_EARTH = 6_356_766.0   # m, effective earth radius used by the standard atmosphere

_EXP = G0 / (R_AIR * LAPSE)                  # 5.2559
T11 = T0 - LAPSE * H_TROPOPAUSE              # 216.65 K
P11 = P0 * (T11 / T0) ** _EXP                # 22632 Pa
RHO11_ISA = P11 / (R_AIR * T11)


def _check(h: float) -> None:
    if not -1_000.0 <= h <= H_TOP:
        raise ValueError(f"altitude {h} m outside the model range [-1000, {H_TOP}]")


def geopotential_m(h: float) -> float:
    """Geometric altitude to geopotential altitude."""
    return R_EARTH * h / (R_EARTH + h)


def isa_temperature_k(h: float) -> float:
    _check(h)
    return T0 - LAPSE * min(geopotential_m(h), H_TROPOPAUSE)


def isa_pressure_pa(h: float) -> float:
    _check(h)
    h = geopotential_m(h)
    if h <= H_TROPOPAUSE:
        return P0 * (1.0 - LAPSE * h / T0) ** _EXP
    return P11 * math.exp(-G0 * (h - H_TROPOPAUSE) / (R_AIR * T11))


@dataclass(frozen=True, slots=True)
class Atmosphere:
    """ISA shifted by isa_offset_c degrees at every altitude."""
    isa_offset_c: float = 0.0

    def __post_init__(self) -> None:
        if not -60.0 <= self.isa_offset_c <= 60.0:
            raise ValueError("isa_offset_c outside [-60, 60]")

    def temperature_k(self, h: float) -> float:
        return isa_temperature_k(h) + self.isa_offset_c

    def pressure_pa(self, h: float) -> float:
        return isa_pressure_pa(h)

    def density(self, h: float) -> float:
        return self.pressure_pa(h) / (R_AIR * self.temperature_k(h))

    def density_ratio(self, h: float) -> float:
        """sigma = rho / rho0. TAS = EAS / sqrt(sigma)."""
        return self.density(h) / RHO0

    def tas_from_eas(self, eas_mps: float, h: float) -> float:
        return eas_mps / math.sqrt(self.density_ratio(h))

    def density_altitude_m(self, h: float) -> float:
        """The ISA altitude whose density equals the actual density at h."""
        return density_altitude_for_density(self.density(h))


def density_altitude_for_density(rho: float) -> float:
    """Geometric altitude at which the standard atmosphere has density rho."""
    if rho <= 0:
        raise ValueError("density must be > 0")
    if rho >= RHO11_ISA:
        theta = (rho / RHO0) ** (1.0 / (_EXP - 1.0))
        hg = T0 * (1.0 - theta) / LAPSE
    else:
        hg = H_TROPOPAUSE - math.log(rho / RHO11_ISA) * R_AIR * T11 / G0
    return R_EARTH * hg / (R_EARTH - hg)


ISA = Atmosphere()
