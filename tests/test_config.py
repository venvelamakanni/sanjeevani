import pytest
from pydantic import ValidationError

from sanjaya.config import PodConfig, SectorConfig, WeightsConfig, load_default


def test_default_configs_load():
    pod = load_default(PodConfig, "pod_v0.yaml")
    sector = load_default(SectorConfig, "sector_thar.yaml")
    w = load_default(WeightsConfig, "weights.yaml")
    assert pod.name == "hanuman_v0" and pod.ld_ratio == 8
    assert sector.border_rule == "hard"
    assert w.threat_exposure > 0


def test_pod_rejects_nonpositive_mass():
    with pytest.raises(ValidationError):
        PodConfig(name="x", mass_kg=0, ld_ratio=8, thrust_n=1, endurance_s=1, cruise_speed_mps=1, stabilise_delay_s=0)


def test_sector_border_rule_must_be_hard():
    with pytest.raises(ValidationError):
        SectorConfig(name="t", country="IN", bbox={"lat_min": 0, "lat_max": 1, "lon_min": 0, "lon_max": 1},
                     border_rule="soft", min_border_margin_m=0, advisor_rate_hz=1)


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        WeightsConfig(reachability_confidence=1, surface_quality=1, distance=1, threat_exposure=1,
                      weather=1, medical_urgency=1, rescue_reachability=1, territory=99)
