"""GRACE/GRACE-FO water-storage asset and the trend model (data/grace.py, science/groundwater.py)."""

import datetime as dt

import numpy as np
import pytest

from fieldshift.data import grace
from fieldshift.science import groundwater as gw


def _monthly(n=240, start=(2002, 4)):
    y, m = start
    out = []
    for _ in range(n):
        out.append(dt.date(y, m, 15))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _synthetic(slope, noise=1.0, seed=0, gap=True):
    d = _monthly()
    t = np.array([gw.decimal_year(x) for x in d])
    rng = np.random.default_rng(seed)
    e = np.zeros(len(d))
    for k in range(1, len(d)):  # AR(1) noise like real GRACE residuals
        e[k] = 0.6 * e[k - 1] + rng.normal(0, noise)
    y = 5 + slope * (t - t.mean()) + 8 * np.sin(2 * np.pi * t) + e
    if gap:  # GRACE -> GRACE-FO gap
        keep = [k for k, x in enumerate(d) if not (dt.date(2017, 7, 1) <= x <= dt.date(2018, 5, 31))]
        d = [d[k] for k in keep]
        y = y[keep]
    return d, y


def test_trend_recovered_and_significant():
    d, y = _synthetic(-2.0)
    tr = gw.analyse(d, y)
    assert tr is not None
    assert tr.slope_cm_yr == pytest.approx(-2.0, abs=0.15)
    assert tr.p_value < 0.001 and tr.status == "declining"
    assert tr.change_cm < -30  # ~ -2 cm/yr over ~20 years since 2003


def test_no_trend_is_stable_and_small_trend_not_called():
    d, y = _synthetic(0.0, seed=3)
    assert gw.analyse(d, y).status == "stable"
    d, y = _synthetic(0.2, noise=0.05, seed=4)  # "significant" but below the 0.3 cm/yr floor
    assert gw.analyse(d, y).status == "stable"


def test_classify_thresholds():
    assert gw.classify(-1.0, 0.01) == "declining"
    assert gw.classify(-1.0, 0.10) == "likely_declining"
    assert gw.classify(-1.0, 0.30) == "stable"
    assert gw.classify(0.5, 0.04) == "rising"
    assert gw.classify(-0.2, 0.0001) == "stable"


def test_autocorrelation_widens_uncertainty():
    d, y = _synthetic(-1.0, noise=2.0, seed=5)
    tr = gw.analyse(d, y)
    assert tr.n_eff < tr.n_months
    beta, t, resid, t0 = gw.fit(d, y)
    X = gw._design(t, t0)
    naive = float(np.sqrt(resid @ resid / (len(y) - 6) * np.linalg.inv(X.T @ X)[1, 1]))
    assert tr.slope_se_cm_yr > naive


def test_as_of_date_ignores_future_months_and_short_records():
    d, y = _synthetic(-1.0)
    tr = gw.analyse(d, y, today=dt.date(2010, 1, 1))
    assert tr.last <= "2009-12"
    assert gw.analyse(d[:20], y[:20]) is None


def test_asset_lookup_worldwide():
    a = grace._load()
    assert a is not None and a["series"].shape[1] == len(a["days"]) >= 200
    india = grace.tws_at(
        29.5, 76.0
    )  # NW India: the best-known GRACE groundwater decline (Rodell et al. 2009)
    tr = gw.analyse(india["dates"], india["tws_cm"])
    assert tr.status == "declining" and tr.slope_cm_yr < -2
    sahel = grace.tws_at(13.5, 2.1)
    assert gw.analyse(sahel["dates"], sahel["tws_cm"]).slope_cm_yr > 0
    assert grace.tws_at(0.0, -140.0) is None  # open Pacific
    coast = grace.tws_at(36.95, -122.05)  # Santa Cruz coast: nearest land cell
    assert coast is not None


def test_cell_of_wraps_longitude():
    assert grace.cell_of(-89.9, -180.0) == (0, 360)
    assert grace.cell_of(89.9, 179.9) == (359, 359)
    assert grace.cell_of(10.0, -0.1) == (200, 719)
    assert grace.cell_of(0.1, 0.1) == (180, 0)
