"""ISA checked against published standard-atmosphere tables, not against itself."""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sanjaya.core.atmosphere import ISA, Atmosphere, density_altitude_for_density

# US Standard Atmosphere 1976, tabulated at GEOMETRIC altitude: m -> (T K, p Pa, rho kg/m^3)
TABLE = {
    0: (288.150, 101_325.0, 1.2250),
    1_000: (281.651, 89_874.6, 1.1117),
    5_000: (255.676, 54_048.3, 0.73643),
    10_000: (223.252, 26_499.9, 0.41351),
    15_000: (216.650, 12_111.8, 0.19476),
}


@pytest.mark.parametrize("h", sorted(TABLE))
def test_isa_matches_standard_table(h):
    t, p, rho = TABLE[h]
    assert ISA.temperature_k(h) == pytest.approx(t, abs=0.01)
    assert ISA.pressure_pa(h) == pytest.approx(p, rel=5e-4)
    assert ISA.density(h) == pytest.approx(rho, rel=5e-4)


def test_sea_level_tas_equals_eas():
    assert ISA.tas_from_eas(61.0, 0.0) == pytest.approx(61.0, rel=1e-9)


def test_hot_day_density_altitude_matches_rule_of_thumb():
    # Pilots' rule: ~120 ft (36.6 m) of density altitude per degC above ISA.
    da = Atmosphere(isa_offset_c=20).density_altitude_m(0.0)
    assert 0.8 * 20 * 36.6 < da < 1.2 * 20 * 36.6


def test_hot_day_is_thinner_same_pressure():
    hot = Atmosphere(isa_offset_c=25)
    assert hot.pressure_pa(3000) == ISA.pressure_pa(3000)
    assert hot.density(3000) < ISA.density(3000)
    assert hot.density(3000) == pytest.approx(ISA.density(3000) * ISA.temperature_k(3000) / hot.temperature_k(3000))


@settings(max_examples=200, deadline=None)
@given(h=st.floats(0.0, 19_000.0))
def test_density_altitude_roundtrip_on_standard_day(h):
    assert ISA.density_altitude_m(h) == pytest.approx(h, abs=0.01)


@settings(max_examples=100, deadline=None)
@given(h=st.floats(0.0, 15_000.0), d1=st.floats(-30, 30), d2=st.floats(-30, 30))
def test_hotter_means_higher_density_altitude(h, d1, d2):
    if d2 > d1 + 0.1:
        assert Atmosphere(d2).density_altitude_m(h) > Atmosphere(d1).density_altitude_m(h)


def test_range_checks():
    with pytest.raises(ValueError):
        ISA.density(25_000)
    with pytest.raises(ValueError):
        Atmosphere(isa_offset_c=90)
    with pytest.raises(ValueError):
        density_altitude_for_density(0.0)
