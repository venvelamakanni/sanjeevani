"""Turn a pod config into the PodPerformance the reach model consumes.

Two sources, one output:
  * pod_v0.yaml alone: L/D and speed are given. Cruise and glide both at L/D max.
  * pod config + aero table: glide L/D and best-glide speed come from the polar;
    cruise stays at the configured speed, with its own L/D read off the polar.

Swapping the aero table file is the only change needed when the 3D track
delivers a new pod. Nothing in the core changes.
"""
from __future__ import annotations

from pathlib import Path

from sanjaya.config import CONFIG_DIR, PodConfig
from sanjaya.core.energy import PodPerformance
from sanjaya.pod.aero_table import AeroTable, load_aero_table

SPEED_OF_SOUND_SL = 340.294   # m/s, ISA sea level; only used to pick the nearest-Mach polar


def performance_from_table(cfg: PodConfig, table: AeroTable) -> PodPerformance:
    polar = table.polar(cfg.cruise_speed_mps / SPEED_OF_SOUND_SL)
    ld_max, cl_star, _ = polar.ld_max()
    glide_eas = table.eas_for_cl(cfg.mass_kg, cl_star)
    cruise_ld = polar.ld_at_cl(table.cl_for_eas(cfg.mass_kg, cfg.cruise_speed_mps))
    return PodPerformance(
        mass_kg=cfg.mass_kg, glide_ld=ld_max, glide_eas_mps=glide_eas,
        cruise_ld=cruise_ld, cruise_eas_mps=cfg.cruise_speed_mps,
        thrust_n=cfg.thrust_n, endurance_s=cfg.endurance_s,
        kinetic_energy_recovery=cfg.kinetic_energy_recovery,
        source=f"aero_table:{table.source}@M{polar.mach:g}",
    )


def performance_from_config(cfg: PodConfig, config_dir: Path | str = CONFIG_DIR) -> PodPerformance:
    if cfg.aero_table:
        p = Path(cfg.aero_table)
        if not p.is_absolute():
            p = Path(config_dir) / p
        return performance_from_table(cfg, load_aero_table(p, sref_m2=cfg.sref_m2))
    return PodPerformance(
        mass_kg=cfg.mass_kg, glide_ld=cfg.ld_ratio, glide_eas_mps=cfg.cruise_speed_mps,
        cruise_ld=cfg.ld_ratio, cruise_eas_mps=cfg.cruise_speed_mps,
        thrust_n=cfg.thrust_n, endurance_s=cfg.endurance_s,
        kinetic_energy_recovery=cfg.kinetic_energy_recovery, source=f"config:{cfg.name}",
    )
