import numpy as np

from fieldshift.science import fielddetect


def test_detects_rectangular_field_bounded_by_road():
    rng = np.random.default_rng(1)
    img = np.zeros((300, 300, 3), np.uint8)
    img[:] = (160, 140, 100)  # neighbouring bare fields
    img[60:220, 50:200] = (40, 110, 40)  # green field 160 x 150 px
    img[100:110, 50:200] = (45, 118, 44)  # irrigation border inside the field (texture)
    img[:, 230:236] = (200, 200, 200)  # road
    img = np.clip(img.astype(int) + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    r = fielddetect.detect(img, (140, 120), pixel_m=1.0)
    assert r is not None and not r["touches_border"]
    assert abs(r["area_px"] - 160 * 150) / (160 * 150) < 0.2
    rows = [p[0] for p in r["polygon_rc"]]
    cols = [p[1] for p in r["polygon_rc"]]
    assert min(rows) > 45 and max(rows) < 235 and min(cols) > 35 and max(cols) < 215
