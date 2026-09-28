"""Write synthetic aero tables that reproduce pod_v0 exactly: L/D max 8 at 61 m/s EAS.

Parabolic drag polar CD = CD0 + k CL^2 has L/D max = 1 / (2 sqrt(CD0 k)) at
CL* = sqrt(CD0 / k). With CD0 = 0.04, L/D max = 8 gives k = 0.09765625 and
CL* = 0.64. The reference area is then chosen so that 300 kg flies CL* at
61 m/s EAS: S = 2 m g / (rho0 V^2 CL*).

Two formats are written so both reader paths are exercised:
  data/aero/synthetic_ld8.csv     canonical CSV
  data/aero/synthetic_ld8.polar   VSPAERO .polar style, whitespace, extra columns
A second Mach (0.25) has a slightly higher CD0, to prove nearest-Mach selection.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sanjaya.core.atmosphere import G0, RHO0  # noqa: E402

LD_MAX, CD0, MASS, V_EAS = 8.0, 0.04, 300.0, 61.0
K = 1.0 / (4.0 * LD_MAX ** 2 * CD0)
CL_STAR = (CD0 / K) ** 0.5
SREF = 2.0 * MASS * G0 / (RHO0 * V_EAS ** 2 * CL_STAR)
CLA, ALPHA0 = 0.08, -2.0     # per degree; zero-lift angle


def rows() -> list[tuple[float, float, float, float]]:
    out = []
    for mach, cd0 in ((0.15, CD0), (0.25, CD0 + 0.002)):
        for a in range(-4, 17):
            cl = CLA * (a - ALPHA0)
            cd = cd0 + K * cl * cl
            if a >= 15:                      # post-stall: lift falls, drag jumps
                cl = CLA * (14 - ALPHA0) - 0.15 * (a - 14)
                cd += 0.05 * (a - 14)
            out.append((mach, float(a), cl, cd))
    return out


def main() -> None:
    out_dir = ROOT / "data" / "aero"
    out_dir.mkdir(parents=True, exist_ok=True)
    head = [f"# synthetic polar reproducing pod_v0: L/D max {LD_MAX} at CL {CL_STAR:.4f}, {V_EAS} m/s EAS, {MASS:g} kg",
            f"# CD = CD0 + k CL^2, CD0 {CD0}, k {K}",
            f"# sref_m2: {SREF:.6f}"]
    r = rows()
    csv_lines = head + ["mach,alpha_deg,cl,cd"] + [f"{m},{a:g},{cl:.6f},{cd:.6f}" for m, a, cl, cd in r]
    (out_dir / "synthetic_ld8.csv").write_text("\n".join(csv_lines) + "\n")
    cols = "Beta Mach AoA Re/1e6 CLo CLi CLtot CDo CDi CDtot L/D E"
    pol = head + [cols] + [
        f"0.0 {m:.3f} {a:.3f} 4.500 0.000 {cl:.6f} {cl:.6f} {cd - K * cl * cl:.6f} {K * cl * cl:.6f} {cd:.6f} "
        f"{cl / cd:.4f} 0.9000" for m, a, cl, cd in r]
    (out_dir / "synthetic_ld8.polar").write_text("\n".join(pol) + "\n")
    print(f"k={K} CL*={CL_STAR:.4f} Sref={SREF:.4f} m^2 -> {out_dir}")


if __name__ == "__main__":
    main()
