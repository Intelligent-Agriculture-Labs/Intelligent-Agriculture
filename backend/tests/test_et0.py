"""FAO-56 worked examples (Allen et al. 1998) as reference values."""

import math

import numpy as np
import pytest

from fieldshift.science import et0


def test_sat_vp_example():  # FAO-56 Table 2.3: e°(15 °C) = 1.705 kPa, e°(24.5 °C) = 3.075 kPa
    assert et0.sat_vp(15.0) == pytest.approx(1.705, abs=0.002)
    assert et0.sat_vp(24.5) == pytest.approx(3.075, abs=0.003)


def test_psychrometric_constant_example2():  # Example 2: z = 1800 m -> γ = 0.054 kPa/°C
    assert et0.psy_const(1800) == pytest.approx(0.054, abs=0.001)


def test_extraterrestrial_radiation_example8():  # Example 8: 20°S, 3 Sept (J=246) -> Ra = 32.2 MJ m-2 d-1
    assert float(et0.ra(-20.0, 246)) == pytest.approx(32.2, abs=0.1)


def test_wind_conversion_example14():  # Example 14: 3.2 m/s at 10 m -> 2.4 m/s at 2 m
    assert float(et0.wind_2m(3.2, 10)) == pytest.approx(2.4, abs=0.02)


def test_et0_example18_uccle():
    """Example 18: Uccle (Brussels), 6 July, lat 50°48'N, z=100 m -> ET0 = 3.9 mm/day.
    Tmax 21.5, Tmin 12.3, ea = 1.409 kPa, u2 = 2.078 m/s, Rs = 22.07 MJ m-2 d-1."""
    ea = 1.409
    tdew = 237.3 * math.log(ea / 0.6108) / (17.27 - math.log(ea / 0.6108))
    v = et0.et0_pm(
        np.array([21.5]),
        np.array([12.3]),
        np.array([22.07]),
        np.array([2.078]),
        50.8,
        100.0,
        np.array([187]),
        tdew=np.array([tdew]),
    )
    assert float(v[0]) == pytest.approx(3.9, abs=0.1)


def test_et0_nan_propagates_and_hargreaves_positive():
    v = et0.et0_pm(
        np.array([30.0, np.nan]),
        np.array([15.0, 15.0]),
        np.array([25.0, 25.0]),
        np.array([2.0, 2.0]),
        40.0,
        1000.0,
        np.array([180, 181]),
    )
    assert np.isfinite(v[0]) and np.isnan(v[1])
    h = et0.et0_hargreaves(np.array([30.0]), np.array([15.0]), 40.0, np.array([180]))
    assert 4 < float(h[0]) < 9
