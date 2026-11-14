import datetime as dt

import numpy as np

from fieldshift.science import satellite as sat


def _season():
    d0 = dt.date(2025, 1, 1)
    dates = [d0 + dt.timedelta(days=k) for k in range(0, 365, 10)]
    doy = np.array([(d - d0).days for d in dates])
    v = 0.15 + 0.65 * np.exp(-(((doy - 200) / 40.0) ** 2))  # single season peaking ~19 Jul
    return dates, v


def test_phenology_single_season():
    dates, v = _season()
    days, sm = sat.smooth_series(dates, list(v))
    ph = sat.phenology(days, sm)
    peak = dt.date.fromisoformat(ph["peak"])
    assert abs((peak - dt.date(2025, 7, 20)).days) <= 6
    assert ph["greenup"] < ph["peak"] < ph["senescence"]
    assert ph["season_type"] == "single season"
    assert ph["bare_periods"], "winter bare period detected"


def test_phenology_three_cuttings():
    d0 = dt.date(2025, 3, 1)
    dates = [d0 + dt.timedelta(days=k) for k in range(0, 220, 5)]
    v = [0.35 + 0.4 * abs(np.sin(np.pi * k / 70)) for k in range(0, 220, 5)]
    days, sm = sat.smooth_series(dates, v)
    assert (
        "growth cycles" in sat.phenology(days, sm)["season_type"]
        or "double" in sat.phenology(days, sm)["season_type"]
    )


def test_kcb_from_ndvi_bounds():
    assert sat.kcb_from_ndvi(0.1, 1.15) == 0.15
    assert sat.kcb_from_ndvi(0.85, 1.15) == 1.15
    assert 0.15 < sat.kcb_from_ndvi(0.45, 1.15) < 1.15


def test_kmeans_zones_recover_two_patches():
    rng = np.random.default_rng(0)
    h, w, n = 30, 30, 6
    stack = np.empty((n, h, w))
    for t in range(n):
        stack[t] = 0.7 + rng.normal(0, 0.02, (h, w))
        stack[t, :, 15:] = 0.35 + rng.normal(0, 0.02, (h, 15))
    mask = np.ones((h, w), bool)
    z = sat.management_zones(stack, mask, None, None)
    assert z is not None and z["k"] == 2 and z["silhouette"] > 0.6
    assert z["zones"][0]["ndvi_mean"] > z["zones"][1]["ndvi_mean"]
    assert (z["labels"][:, :15] == 0).mean() > 0.95
