import numpy as np
import pytest

from fieldshift.science import terrain


def test_plane_slope_and_aspect():
    # plane rising to the north by 10 m per 100 m (10 %): downslope faces south (180°)
    h, w, cell = 60, 60, 10.0
    rows = np.arange(h)[:, None] * np.ones((1, w))
    dem = (h - rows) * cell * 0.10  # row 0 = north = highest
    slope, aspect = terrain.slope_aspect(dem, cell)
    inner = (slice(2, -2), slice(2, -2))
    assert np.allclose(100 * np.tan(slope[inner]), 10.0, atol=0.01)
    assert np.allclose(aspect[inner], 180.0, atol=0.5)


def test_flow_concentrates_in_valley():
    # V-shaped valley along the middle column, sloping south
    h, w, cell = 40, 41, 10.0
    yy, xx = np.mgrid[0:h, 0:w]
    dem = np.abs(xx - 20) * 2.0 + (h - yy) * 0.5
    acc = terrain.d8_accumulation(dem, cell)
    assert acc[-1, 20] > 0.5 * h * w  # most of the catchment drains to the valley outlet
    assert acc[5, 0] < 3


def test_rusle_r_factor_formula():
    assert terrain.rusle_r_factor(500) == pytest.approx(0.0483 * 500**1.61)
    assert terrain.rusle_r_factor(1000) == pytest.approx(587.8 - 1.219 * 1000 + 0.004105 * 1000**2)


def test_layers_flat_field_has_no_erosion():
    dem = np.full((50, 50), 100.0)
    L = terrain.terrain_layers(dem, 10.0, 600, "loam", 0.38)
    assert float(L["soil_loss"].max()) < 0.01
    assert float(L["slope_pct"].max()) < 0.01


def test_polygon_mask_square():
    m = terrain.polygon_mask((10, 10), [(2, 2), (8, 2), (8, 8), (2, 8)])
    assert m.sum() == 36
