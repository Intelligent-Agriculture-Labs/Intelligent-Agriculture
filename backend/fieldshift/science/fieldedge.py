"""Learned field-edge map: a tiny U-Net that predicts, per ~2.7 m pixel, the probability of a field boundary and of
field interior ("extent"). Trained on GPU with Fields of The World labels over open national orthophotos (see
docs/MODELS.md §11 and docs/EXPERIMENTS.md EXP-13); runs here on CPU in plain numpy (no deep-learning runtime).

Architecture: 4-level U-Net, channels 16-32-64-128, 3×3 conv + folded BatchNorm + ReLU, max-pool down,
nearest-neighbour up + 3×3 conv, skip concatenation, 1×1 head with 2 logits. ~0.54 M parameters, float16 weights
(~1 MB, ``models/fieldedge.npz``). Inference on a 256 × 256 window takes ~0.2–0.5 s on one laptop core set.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "fieldedge.npz"


@lru_cache(maxsize=1)
def _weights() -> dict[str, np.ndarray] | None:
    if not MODEL_PATH.exists():
        return None
    with np.load(MODEL_PATH) as z:
        return {k: z[k].astype(np.float32) for k in z.files}


def available() -> bool:
    return _weights() is not None


def _conv3(x: np.ndarray, w: np.ndarray, b: np.ndarray, relu: bool = True) -> np.ndarray:
    """3×3 'same' convolution, channels-last. x: (H, W, C); w: (O, C, 3, 3)."""
    h, wd, c = x.shape
    xp = np.pad(x, ((1, 1), (1, 1), (0, 0)))
    s = xp.strides
    cols = np.lib.stride_tricks.as_strided(xp, (h, wd, 3, 3, c), (s[0], s[1], s[0], s[1], s[2]))
    wm = w.transpose(2, 3, 1, 0).reshape(9 * c, -1)
    y = cols.reshape(h * wd, 9 * c) @ wm + b
    if relu:
        np.maximum(y, 0, out=y)
    return y.reshape(h, wd, -1)


def _block(x: np.ndarray, W: dict[str, np.ndarray], p: str) -> np.ndarray:
    x = _conv3(x, W[p + "a_w"], W[p + "a_b"])
    return _conv3(x, W[p + "b_w"], W[p + "b_b"])


def _pool(x: np.ndarray) -> np.ndarray:
    h, w, c = x.shape
    return x[: h // 2 * 2, : w // 2 * 2].reshape(h // 2, 2, w // 2, 2, c).max(axis=(1, 3))


def predict(rgb_small: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """rgb_small: (H, W, 3) uint8 at ~2.7 m/pixel. Returns (boundary_prob, extent_prob), each (H, W) float32,
    or None when the model file is missing (the caller then uses the classical edge map only)."""
    W = _weights()
    if W is None:
        return None
    levels = int(W["levels"])
    h0, w0 = rgb_small.shape[:2]
    m = 2 ** (levels - 1)
    H, Wd = -(-h0 // m) * m, -(-w0 // m) * m
    x = (rgb_small.astype(np.float32) / 255.0 - W["mean"]) / W["std"]
    x = np.pad(x, ((0, H - h0), (0, Wd - w0), (0, 0)), mode="reflect")
    skips = []
    for i in range(levels):
        x = _block(x if i == 0 else _pool(x), W, f"enc{i}_")
        skips.append(x)
    x = skips.pop()
    for i in range(levels - 1):
        x = x.repeat(2, axis=0).repeat(2, axis=1)
        x = _conv3(x, W[f"up{i}_w"], W[f"up{i}_b"])
        x = _block(np.concatenate([x, skips.pop()], axis=2), W, f"dec{i}_")
    hw = W["head_w"][:, :, 0, 0]  # (2, C)
    logits = x.reshape(-1, x.shape[2]) @ hw.T + W["head_b"]
    prob = (1.0 / (1.0 + np.exp(-logits))).reshape(H, Wd, 2)[:h0, :w0]
    return prob[..., 0].astype(np.float32), prob[..., 1].astype(np.float32)
