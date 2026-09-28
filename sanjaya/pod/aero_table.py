"""Reader for the pod's aerodynamic table (OpenVSP / VSPAERO output).

The 3D track owes the Brain one artifact: lift and drag coefficients against
angle of attack, at one or more Mach numbers. This module reads it and turns it
into the two numbers the reach model needs: the best glide ratio and the speed
that achieves it.

Accepted formats (header row required, column names case-insensitive):
  * comma-separated:   mach,alpha_deg,cl,cd
  * whitespace, VSPAERO .polar style: Beta Mach AoA ... CLtot ... CDtot ...
Lines starting with '#' are comments. A comment of the form '# sref_m2: 2.02'
declares the reference area; it can also be passed in.

Column aliases: mach <- Mach; alpha <- alpha_deg, alpha, AoA; cl <- cl, CLtot, CL;
cd <- cd, CDtot, CD. Other columns are ignored.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from sanjaya.core.atmosphere import G0, RHO0

_ALIASES = {
    "mach": ("mach",),
    "alpha": ("alpha_deg", "alpha", "aoa"),
    "cl": ("cl", "cltot", "cl_tot"),
    "cd": ("cd", "cdtot", "cd_tot"),
}


@dataclass(frozen=True)
class Polar:
    """CL and CD against alpha at one Mach number, alpha strictly increasing."""
    mach: float
    alpha_deg: np.ndarray
    cl: np.ndarray
    cd: np.ndarray

    def __post_init__(self) -> None:
        if len(self.alpha_deg) < 3:
            raise ValueError(f"polar at Mach {self.mach} needs at least 3 points")
        if np.any(np.diff(self.alpha_deg) <= 0):
            raise ValueError(f"polar at Mach {self.mach}: alpha must be strictly increasing (duplicate?)")
        if np.any(self.cd <= 0):
            raise ValueError(f"polar at Mach {self.mach}: CD must be > 0")

    def _fine(self, n: int = 20_001) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        a = np.linspace(self.alpha_deg[0], self.alpha_deg[-1], n)
        return a, np.interp(a, self.alpha_deg, self.cl), np.interp(a, self.alpha_deg, self.cd)

    def ld_max(self) -> tuple[float, float, float]:
        """(L/D max, CL at L/D max, alpha at L/D max), positive-lift branch only."""
        a, cl, cd = self._fine()
        ld = np.where(cl > 0, cl / cd, -np.inf)
        i = int(np.argmax(ld))
        if not np.isfinite(ld[i]):
            raise ValueError(f"polar at Mach {self.mach} has no positive lift")
        return float(ld[i]), float(cl[i]), float(a[i])

    def ld_at_cl(self, cl_target: float) -> float:
        """L/D at a given CL on the attached-flow branch (up to CL max)."""
        a, cl, cd = self._fine()
        top = int(np.argmax(cl))
        cl_b, cd_b = cl[: top + 1], cd[: top + 1]
        if not cl_b[0] <= cl_target <= cl_b[-1]:
            raise ValueError(f"CL {cl_target:.3f} outside the table's range {cl_b[0]:.3f}..{cl_b[-1]:.3f}")
        order = np.argsort(cl_b, kind="stable")
        return float(cl_target / np.interp(cl_target, cl_b[order], cd_b[order]))


@dataclass(frozen=True)
class AeroTable:
    polars: tuple[Polar, ...]
    sref_m2: float | None
    source: str = ""

    @property
    def machs(self) -> tuple[float, ...]:
        return tuple(p.mach for p in self.polars)

    def polar(self, mach: float) -> Polar:
        """The polar at the Mach number nearest to mach."""
        return min(self.polars, key=lambda p: (abs(p.mach - mach), p.mach))

    def eas_for_cl(self, mass_kg: float, cl: float) -> float:
        """Equivalent airspeed at which level flight needs this CL: sqrt(2W / (rho0 S CL))."""
        if self.sref_m2 is None:
            raise ValueError("reference area sref_m2 unknown: declare it in the file or in the pod config")
        return math.sqrt(2.0 * mass_kg * G0 / (RHO0 * self.sref_m2 * cl))

    def cl_for_eas(self, mass_kg: float, eas_mps: float) -> float:
        if self.sref_m2 is None:
            raise ValueError("reference area sref_m2 unknown: declare it in the file or in the pod config")
        return 2.0 * mass_kg * G0 / (RHO0 * self.sref_m2 * eas_mps ** 2)


def load_aero_table(path: Path | str, sref_m2: float | None = None) -> AeroTable:
    path = Path(path)
    header: list[str] | None = None
    rows: list[list[str]] = []
    meta: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            if ":" in body:
                k, v = body.split(":", 1)
                meta[k.strip().lower()] = v.strip()
            continue
        parts = [x.strip() for x in line.split(",")] if "," in line else line.split()
        if header is None:
            header = [x.lower() for x in parts]
        else:
            rows.append(parts)
    if header is None or not rows:
        raise ValueError(f"aero table {path} has no header or no data")

    idx: dict[str, int] = {}
    for key, names in _ALIASES.items():
        for n in names:
            if n in header:
                idx[key] = header.index(n)
                break
    missing = [k for k in ("alpha", "cl", "cd") if k not in idx]
    if missing:
        raise ValueError(f"aero table {path} missing columns {missing}; header was {header}")

    by_mach: dict[float, list[tuple[float, float, float]]] = {}
    for r in rows:
        if len(r) != len(header):
            raise ValueError(f"aero table {path}: row has {len(r)} fields, header has {len(header)}")
        m = float(r[idx["mach"]]) if "mach" in idx else 0.0
        by_mach.setdefault(m, []).append((float(r[idx["alpha"]]), float(r[idx["cl"]]), float(r[idx["cd"]])))

    polars = []
    for m in sorted(by_mach):
        pts = sorted(by_mach[m])
        arr = np.array(pts, dtype=np.float64)
        polars.append(Polar(mach=m, alpha_deg=arr[:, 0], cl=arr[:, 1], cd=arr[:, 2]))

    if sref_m2 is None and "sref_m2" in meta:
        sref_m2 = float(meta["sref_m2"])
    if sref_m2 is not None and sref_m2 <= 0:
        raise ValueError("sref_m2 must be > 0")
    return AeroTable(polars=tuple(polars), sref_m2=sref_m2, source=str(path))
