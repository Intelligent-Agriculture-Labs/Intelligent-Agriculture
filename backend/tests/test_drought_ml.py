import datetime as dt

import numpy as np

from fieldshift.science import drought_ml


def _series(days=9000, south=False, seed=0):
    d0 = dt.date(2000, 1, 1)
    dates = [d0 + dt.timedelta(days=i) for i in range(days)]
    doy = np.array([d.timetuple().tm_yday for d in dates])
    shift = 182 if south else 0
    rng = np.random.default_rng(seed)
    rain = rng.gamma(0.5, 4, days) * (1 + 0.8 * np.sin(2 * np.pi * (doy - shift) / 365))
    et0 = 3 + 2 * np.sin(2 * np.pi * (doy - 100 - shift) / 365)
    tmax = 20 + 10 * np.sin(2 * np.pi * (doy - 110 - shift) / 365) + rng.normal(0, 2, days)
    return dates, rain, et0, tmax


def test_v2_features_shape_and_ranges():
    dates, rain, et0, tmax = _series()
    X = drought_ml.feature_matrix_v2(dates, rain, et0, tmax)
    assert X.shape == (len(dates), len(drought_ml.FEATURES_V2))
    last = dict(zip(drought_ml.FEATURES_V2, X[-1], strict=True))
    assert np.isfinite(X[-1]).all()
    assert -4 < last["tmax_z30"] < 4
    assert abs(last["phase_sin"] ** 2 + last["phase_cos"] ** 2 - 1) < 1e-9
    assert 0 < last["aridity"] < 5


def test_v2_season_phase_is_hemisphere_agnostic():
    """The same climate shifted by half a year (southern hemisphere) gives the same phase half a year later."""
    dn, rn, en, tn = _series()
    ds, rs, es, ts = _series(south=True)
    Xn = drought_ml.feature_matrix_v2(dn, rn, en, tn)
    Xs = drought_ml.feature_matrix_v2(ds, rs, es, ts)
    i = drought_ml.FEATURES_V2.index("phase_cos")
    k = 8000  # some day; the southern site is in the same phase 26 weeks later
    assert abs(Xn[k, i] - Xs[k + 182, i]) < 0.25


def test_region_gating():
    assert drought_ml.region_of(42.0, -93.6) == "US"
    assert drought_ml.region_of(37.9, -4.8) == "EU"
    assert drought_ml.region_of(-1.5, 37.3) == "AFR"
    assert drought_ml.region_of(70.0, -150.0) is None
    assert drought_ml.in_validated_domain(42.0, -93.6, None)  # old metadata: U.S. only
    assert not drought_ml.in_validated_domain(37.9, -4.8, None)
    assert drought_ml.in_validated_domain(37.9, -4.8, {"model_regions": ["US", "EU"]})
    assert not drought_ml.in_validated_domain(-1.5, 37.3, {"model_regions": ["US", "EU"]})


def test_saved_model_matches_its_feature_set():
    loaded = drought_ml.load()
    if loaded is None:
        return
    model, meta = loaded
    assert model.n_features_in_ == len(meta["features"])
    fn = drought_ml.features_for(meta)
    dates, rain, et0, tmax = _series(days=3000)
    X = fn(dates, rain, et0, tmax)
    assert X.shape[1] == len(meta["features"])
    pr = drought_ml.predict(X[-1])
    assert pr is not None and 0 <= pr[0] <= 5 and abs(sum(pr[1]) - 1) < 1e-6
