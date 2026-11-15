import numpy as np
import pytest
from scipy import ndimage

from fieldshift.science import fielddetect, fieldedge


def _synthetic_field(seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.zeros((300, 300, 3), np.uint8)
    img[:] = (160, 140, 100)  # neighbouring bare fields
    img[60:220, 50:200] = (40, 110, 40)  # green field 160 x 150 px
    img[100:110, 50:200] = (45, 118, 44)  # irrigation border inside the field (texture)
    img[:, 230:236] = (200, 200, 200)  # road
    return np.clip(img.astype(int) + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)


def _check_rectangle(r: dict | None) -> None:
    assert r is not None and not r["touches_border"]
    assert abs(r["area_px"] - 160 * 150) / (160 * 150) < 0.2
    rows = [p[0] for p in r["polygon_rc"]]
    cols = [p[1] for p in r["polygon_rc"]]
    assert min(rows) > 45 and max(rows) < 235 and min(cols) > 35 and max(cols) < 215


def test_classical_detects_rectangular_field_bounded_by_road():
    _check_rectangle(fielddetect.detect_classical(_synthetic_field(), (140, 120), pixel_m=1.0))


def test_learned_detects_rectangular_field_bounded_by_road():
    assert fieldedge.available(), "model file fieldshift/models/fieldedge.npz is missing"
    r = fielddetect.detect(_synthetic_field(), (140, 120), pixel_m=1.0)
    assert r is not None and r["params"]["method"] == "learned"
    _check_rectangle(r)
    assert 0.05 <= r["confidence"] <= 0.95


def test_falls_back_to_classical_without_model(monkeypatch):
    monkeypatch.setattr(fieldedge, "_weights", lambda: None)
    r = fielddetect.detect(_synthetic_field(), (140, 120), pixel_m=1.0)
    assert r is not None and r["params"]["method"] == "classical"
    _check_rectangle(r)


def test_numpy_conv_matches_reference():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(9, 11, 4)).astype(np.float32)
    w = rng.normal(size=(5, 4, 3, 3)).astype(np.float32)
    b = rng.normal(size=5).astype(np.float32)
    y = fieldedge._conv3(x, w, b, relu=False)
    for o in range(5):
        ref = sum(ndimage.correlate(x[..., c], w[o, c], mode="constant") for c in range(4)) + b[o]
        np.testing.assert_allclose(y[..., o], ref, rtol=1e-4, atol=1e-4)


def test_edge_model_outputs_probabilities_and_is_small():
    rng = np.random.default_rng(0)
    out = fieldedge.predict(rng.integers(0, 255, (70, 90, 3), dtype=np.uint8))  # odd size -> padding path
    assert out is not None
    for p in out:
        assert p.shape == (70, 90) and float(p.min()) >= 0 and float(p.max()) <= 1
    assert fieldedge.MODEL_PATH.stat().st_size < 3_000_000
    assert fielddetect.SELECT_PATH.stat().st_size < 1_000_000


def test_numpy_trees_match_sklearn(monkeypatch):
    sk = pytest.importorskip("sklearn.ensemble")
    rng = np.random.default_rng(0)
    X = rng.normal(size=(400, len(fielddetect.FEATS)))
    y = np.sin(X[:, 0]) + 0.5 * (X[:, 3] > 0.2) + rng.normal(0, 0.05, 400)
    m = sk.GradientBoostingRegressor(n_estimators=20, max_depth=3, random_state=0).fit(X, y)
    trees = [e[0].tree_ for e in m.estimators_]
    n = max(t.node_count for t in trees)

    def pad(a, fill):
        return np.array([np.pad(v, (0, n - len(v)), constant_values=fill) for v in a])

    sel = {
        "left": pad([t.children_left for t in trees], -1),
        "right": pad([t.children_right for t in trees], -1),
        "feature": pad([t.feature for t in trees], -2),
        "threshold": pad([t.threshold for t in trees], 0),
        "value": pad([t.value[:, 0, 0] for t in trees], 0),
        "lr": np.float32(m.learning_rate),
        "init": np.float32(m.init_.constant_[0][0]),
    }
    monkeypatch.setattr(fielddetect, "_selector", lambda: sel)
    np.testing.assert_allclose(fielddetect._predict_iou(X), m.predict(X), atol=1e-4)


def test_fast_fill_holes_matches_scipy():
    rng = np.random.default_rng(3)
    for _ in range(20):
        m = ndimage.binary_opening(rng.random((40, 50)) > 0.45)
        np.testing.assert_array_equal(fielddetect._fill_holes(m), ndimage.binary_fill_holes(m))


def test_cropped_opening_matches_full_image_opening():
    rng = np.random.default_rng(5)
    E = ndimage.gaussian_filter(rng.random((80, 90)), 2)
    cands, (sr, sc) = fielddetect.candidates(E, (40, 45), max_frac=1.0)
    assert cands
    for t, r, reg in cands:
        low = np.less_equal(E, t)
        m = ndimage.binary_opening(low, structure=fielddetect._disk(r)) if r else low
        lab, _ = ndimage.label(m)
        np.testing.assert_array_equal(reg, lab == lab[sr, sc])
