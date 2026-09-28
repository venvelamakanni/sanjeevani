"""Aero-table reader, tested on synthetic tables built to reproduce pod_v0 (L/D 8 at 61 m/s)."""
import math
from pathlib import Path

import pytest

from sanjaya.config import PodConfig, load_default
from sanjaya.core.energy import Wind, reach
from sanjaya.pod.aero_table import load_aero_table
from sanjaya.pod.model import performance_from_config

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "aero" / "synthetic_ld8.csv"
POLAR = ROOT / "data" / "aero" / "synthetic_ld8.polar"


@pytest.mark.parametrize("path", [CSV, POLAR], ids=["csv", "vspaero_polar"])
def test_synthetic_table_reproduces_ld8(path):
    t = load_aero_table(path)
    assert t.machs == (0.15, 0.25)
    assert t.sref_m2 == pytest.approx(2.016955, rel=1e-6)
    p = t.polar(0.18)
    assert p.mach == 0.15
    ld, cl, alpha = p.ld_max()
    assert ld == pytest.approx(8.0, rel=1e-3)
    assert cl == pytest.approx(0.64, rel=1e-2)
    assert alpha == pytest.approx(6.0, abs=0.2)
    assert t.eas_for_cl(300, cl) == pytest.approx(61.0, rel=1e-2)
    assert t.polar(0.3).ld_max()[0] < ld           # higher CD0 at Mach 0.25


def test_ld_at_cl_uses_attached_branch():
    p = load_aero_table(CSV).polar(0.15)
    cd = 0.04 + 0.09765625 * 0.4 ** 2
    assert p.ld_at_cl(0.4) == pytest.approx(0.4 / cd, rel=2e-3)
    with pytest.raises(ValueError):
        p.ld_at_cl(2.0)


def test_pod_from_table_matches_pod_from_config(tmp_path):
    base = load_default(PodConfig, "pod_v0.yaml")
    from_cfg = performance_from_config(base)
    from_tab = performance_from_config(base.model_copy(update={"aero_table": str(CSV)}))
    assert from_tab.source.startswith("aero_table:")
    assert from_tab.glide_ld == pytest.approx(8.0, rel=1e-3)
    assert from_tab.glide_eas_mps == pytest.approx(61.0, rel=1e-2)
    assert from_tab.cruise_ld == pytest.approx(8.0, rel=1e-2)
    for alt, w in ((3000, Wind()), (9000, Wind(20, 250))):
        a = reach(from_cfg, alt, 200, 70, wind=w).distance_m
        b = reach(from_tab, alt, 200, 70, wind=w).distance_m
        assert b == pytest.approx(a, rel=1e-2)


def test_relative_table_path_resolves_against_config_dir(tmp_path):
    (tmp_path / "t.csv").write_text(CSV.read_text())
    cfg = load_default(PodConfig, "pod_v0.yaml").model_copy(update={"aero_table": "t.csv"})
    assert performance_from_config(cfg, config_dir=tmp_path).glide_ld == pytest.approx(8.0, rel=1e-3)


def test_explicit_sref_overrides_file(tmp_path):
    t = load_aero_table(CSV, sref_m2=4.0)
    assert t.sref_m2 == 4.0
    assert t.eas_for_cl(300, 0.64) == pytest.approx(61.0 * math.sqrt(2.016955 / 4.0), rel=1e-3)


def test_missing_sref_is_reported(tmp_path):
    f = tmp_path / "nosref.csv"
    f.write_text("alpha_deg,cl,cd\n0,0.1,0.04\n2,0.3,0.05\n4,0.5,0.065\n")
    t = load_aero_table(f)
    assert t.machs == (0.0,)
    with pytest.raises(ValueError, match="sref"):
        t.eas_for_cl(300, 0.5)


@pytest.mark.parametrize("body,msg", [
    ("alpha,cl\n0,0.1\n", "missing columns"),
    ("alpha,cl,cd\n0,0.1,0.04\n0,0.2,0.05\n2,0.3,0.05\n", "strictly increasing"),
    ("alpha,cl,cd\n0,0.1,0.04\n1,0.2\n", "fields"),
    ("alpha,cl,cd\n0,0.1,0\n1,0.2,0.05\n2,0.3,0.06\n", "CD must be"),
    ("# only a comment\n", "no header"),
])
def test_malformed_tables(tmp_path, body, msg):
    f = tmp_path / "bad.csv"
    f.write_text(body)
    with pytest.raises(ValueError, match=msg):
        load_aero_table(f)
