"""Pod energy and reach: how far can HANUMAN get from here?

Deterministic core. Pure functions, SI units, no I/O.

Model (v0, point mass, steady flight):
  1. Optional speed/energy exchange at release. If the pod starts faster than its
     flight speed, a configurable fraction of the excess kinetic energy is credited
     as height (default 0: conservative). If it starts slower, the full deficit is
     debited, because it must dive to gain speed.
  2. Powered phase for the remaining endurance, flown at cruise EAS. If thrust
     covers cruise drag the pod holds altitude; otherwise it flies a shallow
     powered descent. Climb is never credited.
  3. Glide phase at best-glide EAS from wherever the powered phase ended down to
     the landing-site elevation.

Glide ratio L/D is horizontal distance over height lost. In still air the glide
leg is exactly height x L/D whatever the air density. Density matters through
airspeed: the pod flies at constant equivalent airspeed (EAS), so its true
airspeed is EAS / sqrt(sigma). Higher, hotter air means faster flight, less time
aloft, and therefore less wind drift. That is the density-altitude correction.

Wind is steady and uniform in v0. Along a chosen track the pod crabs into the
crosswind; ground speed = tailwind + sqrt(V_air^2 - crosswind^2). If the
crosswind exceeds the airspeed the track cannot be held and reach is zero.

Worked hand check (also a unit test):
  pod v0: L/D 8, cruise = glide = 61 m/s EAS, thrust 370 N >= 300*9.80665/8 = 367.7 N,
  so it cruises level. Released at 3200 m AMSL over a site at 200 m, calm, endurance 0:
      glide = (3200 - 200) * 8 = 24,000 m.
  Released at sea level over a sea-level site, calm, full 900 s endurance:
      powered = 61 * 900 = 54,900 m.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .atmosphere import G0, H_TOP, ISA, Atmosphere


# --------------------------------------------------------------------------- wind

@dataclass(frozen=True, slots=True)
class Wind:
    """Steady wind. from_deg is the meteorological direction the wind blows FROM."""
    speed_mps: float = 0.0
    from_deg: float = 0.0

    def __post_init__(self) -> None:
        if self.speed_mps < 0:
            raise ValueError("wind speed must be >= 0")
        if not 0.0 <= self.from_deg < 360.0:
            raise ValueError("wind from_deg must be in [0, 360)")

    def components(self, track_deg: float) -> tuple[float, float]:
        """(tailwind, crosswind) relative to a track. Tailwind positive, headwind negative."""
        rel = math.radians(self.from_deg + 180.0 - track_deg)
        return self.speed_mps * math.cos(rel), self.speed_mps * math.sin(rel)


CALM = Wind()


def ground_speed_mps(air_speed_mps: float, wind: Wind, track_deg: float) -> float | None:
    """Ground speed along track when crabbing into the crosswind; None if the track cannot be held."""
    tail, cross = wind.components(track_deg)
    if abs(cross) >= air_speed_mps:
        return None
    return tail + math.sqrt(air_speed_mps * air_speed_mps - cross * cross)


# --------------------------------------------------------------------------- pod

@dataclass(frozen=True, slots=True)
class PodPerformance:
    """Everything the reach model needs to know about the pod.

    Built from pod_v0.yaml (L/D and speeds given directly) or from an aero table
    (L/D and speeds derived from the drag polar). See sanjaya/pod/model.py.
    Speeds are equivalent airspeeds (sea-level-equivalent), in m/s.
    """
    mass_kg: float
    glide_ld: float
    glide_eas_mps: float
    cruise_ld: float
    cruise_eas_mps: float
    thrust_n: float
    endurance_s: float
    kinetic_energy_recovery: float = 0.0
    source: str = "config"

    def __post_init__(self) -> None:
        for name in ("mass_kg", "glide_ld", "glide_eas_mps", "cruise_ld", "cruise_eas_mps"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if self.thrust_n < 0 or self.endurance_s < 0:
            raise ValueError("thrust and endurance must be >= 0")
        if not 0.0 <= self.kinetic_energy_recovery <= 1.0:
            raise ValueError("kinetic_energy_recovery must be in [0, 1]")

    @property
    def weight_n(self) -> float:
        return self.mass_kg * G0

    @property
    def cruise_drag_n(self) -> float:
        return self.weight_n / self.cruise_ld

    @property
    def cruises_level(self) -> bool:
        return self.thrust_n >= self.cruise_drag_n

    @property
    def glide_angle_rad(self) -> float:
        return math.atan(1.0 / self.glide_ld)

    @property
    def powered_angle_rad(self) -> float:
        """Flight-path angle below horizontal with thrust on; 0 when it can hold level.

        Steady flight: W cos(g) / L_D - T = W sin(g). Solved exactly for g.
        """
        if self.thrust_n <= 0:
            return math.atan(1.0 / self.cruise_ld)
        a = 1.0 / self.cruise_ld
        c = (self.thrust_n / self.weight_n) / math.sqrt(a * a + 1.0)
        g = math.acos(min(1.0, c)) - math.atan2(1.0, a)
        return max(0.0, g)


# --------------------------------------------------------------------------- profile

@dataclass(frozen=True, slots=True)
class Segment:
    """A slice of the descent. alt_top == alt_bottom for level powered flight."""
    alt_top_m: float
    alt_bottom_m: float
    air_speed_mps: float      # horizontal component of true airspeed
    dt_s: float
    powered: bool


@dataclass(frozen=True, slots=True)
class Reach:
    track_deg: float
    distance_m: float         # along-track ground distance to touchdown at the site elevation
    powered_m: float
    glide_m: float
    time_s: float             # time from release to touchdown
    holds_track: bool         # False when the crosswind exceeds airspeed somewhere on the way


class DescentProfile:
    """The pod's descent from release down to a floor altitude.

    Built once per release state. Wind direction does not change it, so reach in
    every direction, and to sites at any elevation above the floor, is a cheap
    sum over the same segments.
    """

    def __init__(self, segments: tuple[Segment, ...], release_alt_m: float, start_alt_m: float, floor_m: float):
        self.segments = segments
        self.release_alt_m = release_alt_m
        self.start_alt_m = start_alt_m      # after the speed/energy exchange
        self.floor_m = floor_m

    @classmethod
    def build(
        cls,
        perf: PodPerformance,
        alt_m: float,
        floor_m: float = 0.0,
        atm: Atmosphere = ISA,
        endurance_s: float | None = None,
        initial_tas_mps: float | None = None,
        step_m: float = 50.0,
    ) -> "DescentProfile":
        if step_m <= 0:
            raise ValueError("step_m must be > 0")
        te = perf.endurance_s if endurance_s is None else endurance_s
        if te < 0:
            raise ValueError("endurance must be >= 0")

        start = alt_m
        if initial_tas_mps is not None:
            if initial_tas_mps < 0:
                raise ValueError("initial_tas_mps must be >= 0")
            target_eas = perf.cruise_eas_mps if te > 0 else perf.glide_eas_mps
            v_t = atm.tas_from_eas(target_eas, alt_m)
            dh = (initial_tas_mps ** 2 - v_t ** 2) / (2.0 * G0)
            start = alt_m + (dh * perf.kinetic_energy_recovery if dh > 0 else dh)
            start = min(start, H_TOP)

        segs: list[Segment] = []
        h = start

        # powered phase
        if te > 0:
            if perf.cruises_level:
                segs.append(Segment(h, h, atm.tas_from_eas(perf.cruise_eas_mps, h), te, True))
            else:
                g = perf.powered_angle_rad
                t_left = te
                while t_left > 0 and h > floor_m:
                    dh = min(step_m, h - floor_m)
                    tas = atm.tas_from_eas(perf.cruise_eas_mps, h - dh / 2.0)
                    sink = tas * math.sin(g)
                    dt = dh / sink
                    if dt > t_left:
                        dt, dh = t_left, t_left * sink
                    segs.append(Segment(h, h - dh, tas * math.cos(g), dt, True))
                    h -= dh
                    t_left -= dt

        # glide phase
        g = perf.glide_angle_rad
        while h > floor_m:
            dh = min(step_m, h - floor_m)
            tas = atm.tas_from_eas(perf.glide_eas_mps, h - dh / 2.0)
            segs.append(Segment(h, h - dh, tas * math.cos(g), dh / (tas * math.sin(g)), False))
            h -= dh

        return cls(tuple(segs), alt_m, start, floor_m)

    def reach(self, track_deg: float, wind: Wind = CALM, site_elev_m: float | None = None) -> Reach:
        site = self.floor_m if site_elev_m is None else site_elev_m
        if site < self.floor_m - 1e-9:
            raise ValueError(f"site elevation {site} below profile floor {self.floor_m}")
        if site > self.start_alt_m:
            return Reach(track_deg, 0.0, 0.0, 0.0, 0.0, True)

        powered = glide = t = 0.0
        for s in self.segments:
            if s.alt_top_m == s.alt_bottom_m:
                frac = 1.0
            elif s.alt_bottom_m >= site:
                frac = 1.0
            elif s.alt_top_m <= site:
                break
            else:
                frac = (s.alt_top_m - site) / (s.alt_top_m - s.alt_bottom_m)
            gs = ground_speed_mps(s.air_speed_mps, wind, track_deg)
            if gs is None:
                return Reach(track_deg, 0.0, 0.0, 0.0, 0.0, False)
            d = gs * s.dt_s * frac
            if s.powered:
                powered += d
            else:
                glide += d
            t += s.dt_s * frac
        return Reach(track_deg, max(0.0, powered + glide), powered, glide, t, True)


# --------------------------------------------------------------------------- convenience

def reach(
    perf: PodPerformance,
    alt_m: float,
    site_elev_m: float,
    track_deg: float,
    wind: Wind = CALM,
    atm: Atmosphere = ISA,
    endurance_s: float | None = None,
    initial_tas_mps: float | None = None,
) -> Reach:
    """Along-track reach from a release at alt_m (AMSL) to a site at site_elev_m (AMSL)."""
    prof = DescentProfile.build(perf, alt_m, floor_m=min(site_elev_m, alt_m), atm=atm,
                                endurance_s=endurance_s, initial_tas_mps=initial_tas_mps)
    return prof.reach(track_deg, wind, site_elev_m)


def footprint(
    perf: PodPerformance,
    alt_m: float,
    site_elev_m: float,
    wind: Wind = CALM,
    atm: Atmosphere = ISA,
    n_bearings: int = 36,
    endurance_s: float | None = None,
    initial_tas_mps: float | None = None,
) -> tuple[Reach, ...]:
    """Reach on n evenly spaced tracks starting at north. The reachable-area outline."""
    if n_bearings < 1:
        raise ValueError("n_bearings must be >= 1")
    prof = DescentProfile.build(perf, alt_m, floor_m=min(site_elev_m, alt_m), atm=atm,
                                endurance_s=endurance_s, initial_tas_mps=initial_tas_mps)
    return tuple(prof.reach(360.0 * i / n_bearings, wind, site_elev_m) for i in range(n_bearings))
