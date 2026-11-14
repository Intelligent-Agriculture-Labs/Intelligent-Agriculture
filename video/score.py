"""Original score for the FieldShift film, synthesised from scratch (no samples, no generative-AI audio).

96 BPM, D minor, one bar = 2.5 s so every structural hit lands on the Space Apps template marks:
  0-5 s   intro: Earth from orbit. Shimmer, drone, Dm(add9) -> Bbmaj7 pads, riser into
  5 s     IMPACT: title. Bb -> F/A, piano motif
  10-20 s "how it works": pulse. Dm - Bb - F - C, kick, hats, 16th plucks, sub bass, sidechained pads
  20-25 s lift: Gm - Bb, claps, tom build, riser into
  25 s    BIG HIT: F major, then Bbmaj9 -> F with a long tail, fade by 30 s

    backend/.venv/bin/python video/score.py   -> video/build/score.wav (48 kHz stereo)
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 48_000
DUR = 30.0
N = int(SR * DUR)
BEAT = 60 / 96
BAR = 4 * BEAT  # 2.5 s
OUT = Path(__file__).resolve().parent / "build" / "score.wav"
rng = np.random.default_rng(2026)


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}
NOTE.update({"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10})


def m(name: str) -> int:
    """'D3' -> MIDI number."""
    return NOTE[name[:-1]] + 12 * (int(name[-1]) + 1)


def t_axis(n: int) -> np.ndarray:
    return np.arange(n) / SR


def place(buf: np.ndarray, sig: np.ndarray, start: float, gain: float = 1.0, pan: float = 0.0) -> None:
    """Add mono/stereo sig into stereo buf at time start (s), equal-power pan -1..1."""
    i0 = int(start * SR)
    if i0 < 0:  # starts before 0: drop the head
        sig, i0 = sig[-i0:], 0
    if i0 >= buf.shape[0]:
        return
    if sig.ndim == 1:
        a = (pan + 1) * np.pi / 4
        sig = np.stack([sig * np.cos(a), sig * np.sin(a)], axis=1)
    n = min(sig.shape[0], buf.shape[0] - i0)
    buf[i0 : i0 + n] += gain * sig[:n]


def env_adsr(n: int, a: float, d: float, s: float, r: float) -> np.ndarray:
    t = t_axis(n)
    dur = n / SR
    e = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    rel = np.clip((dur - t) / max(r, 1e-4), 0, 1)
    return e * rel**1.5


def lp(x: np.ndarray, f: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x, axis=0)


def hp(x: np.ndarray, f: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x, axis=0)


def bp(x: np.ndarray, lo: float, hi: float, order: int = 2) -> np.ndarray:
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x, axis=0)


# ---------------------------------------------------------------- instruments
def saw_pad(freq: float, dur: float, bright: float = 6.0) -> np.ndarray:
    """Warm detuned saw pad (additive, band-limited), stereo."""
    n = int(dur * SR)
    t = t_axis(n)
    out = np.zeros((n, 2))
    for k, (det, pan) in enumerate([(-0.11, -0.7), (0.0, 0.0), (0.12, 0.7)]):
        f = freq * 2 ** (det / 12)
        ph = rng.uniform(0, 2 * np.pi)
        s = np.zeros(n)
        for h in range(1, 24):
            if f * h > 9000:
                break
            s += np.sin(2 * np.pi * f * h * t + ph * h) / h * np.exp(-h / bright)
        a = (pan + 1) * np.pi / 4
        out[:, 0] += s * np.cos(a)
        out[:, 1] += s * np.sin(a)
    # slow movement
    lfo = 1 + 0.08 * np.sin(2 * np.pi * 0.21 * t + rng.uniform(0, 6))
    return out * (env_adsr(n, min(1.2, dur * 0.4), 1.5, 0.85, min(1.4, dur * 0.4)) * lfo)[:, None] / 3


def piano(freq: float, dur: float = 2.5) -> np.ndarray:
    n = int(dur * SR)
    t = t_axis(n)
    s = np.zeros(n)
    B = 0.0004  # slight inharmonicity
    for h in range(1, 12):
        fh = freq * h * np.sqrt(1 + B * h * h)
        if fh > 12000:
            break
        s += np.sin(2 * np.pi * fh * t) * (0.9**h) / h**0.7 * np.exp(-t * (0.9 + 0.55 * h))
    hammer = hp(rng.standard_normal(n), 2000) * np.exp(-t * 120) * 0.02
    e = np.minimum(1, t / 0.004) * np.clip((dur - t) / 0.3, 0, 1)
    return (s + hammer) * e


def pluck(freq: float, dur: float = 0.55) -> np.ndarray:
    n = int(dur * SR)
    t = t_axis(n)
    s = np.zeros(n)
    for h in range(1, 14):
        if freq * h > 11000:
            break
        s += np.sin(2 * np.pi * freq * h * t) / h * np.exp(-t * (5 + 2.2 * h))
    return s * np.minimum(1, t / 0.002)


def bell(freq: float, dur: float = 4.0) -> np.ndarray:
    n = int(dur * SR)
    t = t_axis(n)
    ratios = [(1, 1.0, 0.7), (2.76, 0.4, 1.6), (5.4, 0.18, 2.6), (8.93, 0.08, 4.0)]
    s = sum(a * np.sin(2 * np.pi * freq * r * t) * np.exp(-t * d) for r, a, d in ratios)
    return s * np.minimum(1, t / 0.003)


def sub(freq: float, dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = t_axis(n)
    s = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t) + 0.08 * np.sin(6 * np.pi * freq * t)
    return s * env_adsr(n, 0.02, 0.6, 0.8, 0.12)


def kick() -> np.ndarray:
    n = int(0.6 * SR)
    t = t_axis(n)
    f = 46 + 120 * np.exp(-t * 32)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * 5.5)
    click = hp(rng.standard_normal(n), 3000) * np.exp(-t * 400) * 0.25
    return np.tanh(1.6 * (body + click)) * 0.9


def hat(open_: bool = False) -> np.ndarray:
    n = int((0.25 if open_ else 0.06) * SR)
    t = t_axis(n)
    return hp(rng.standard_normal(n), 7000, 4) * np.exp(-t * (14 if open_ else 70)) * 0.5


def clap() -> np.ndarray:
    n = int(0.4 * SR)
    t = t_axis(n)
    nz = bp(rng.standard_normal(n), 900, 5000)
    e = sum(np.exp(-np.maximum(t - d, 0) * 60) * (t >= d) for d in (0, 0.011, 0.023)) + 0.6 * np.exp(-t * 14)
    return nz * e * 0.35


def tom(freq: float) -> np.ndarray:
    n = int(0.5 * SR)
    t = t_axis(n)
    f = freq * (1 + 0.6 * np.exp(-t * 25))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * 0.8


def impact(size: float = 1.0) -> np.ndarray:
    n = int(4.5 * SR)
    t = t_axis(n)
    f = 32 + 60 * np.exp(-t * 6)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.1)
    noise = lp(rng.standard_normal(n), 1800) * np.exp(-t * 3.5) * 0.5
    crack = hp(rng.standard_normal(n), 2500) * np.exp(-t * 30) * 0.3
    return np.tanh(1.3 * (boom + noise + crack)) * size


def crash(dur: float = 3.0) -> np.ndarray:
    n = int(dur * SR)
    t = t_axis(n)
    x = hp(rng.standard_normal((n, 2)), 4500, 3)
    shimmer = bp(rng.standard_normal((n, 2)), 6000, 14000)
    return (x * 0.6 + shimmer * 0.4) * (np.exp(-t * 1.6) * np.minimum(1, t / 0.002))[:, None] * 0.35


def riser(dur: float) -> np.ndarray:
    """Filtered noise that opens up + rising whistle, ends exactly at dur."""
    n = int(dur * SR)
    t = t_axis(n)
    x = rng.standard_normal(n)
    # sweep a band-pass by processing in chunks
    out = np.zeros(n)
    chunks = 40
    for c in range(chunks):
        a, b = c * n // chunks, (c + 1) * n // chunks
        frac = c / chunks
        lo = 300 + 4000 * frac**2
        out[a:b] = bp(x[a:b], lo, min(lo * 3, 20000))
    env = (t / dur) ** 2.2
    whistle = np.sin(2 * np.pi * np.cumsum(220 * 2 ** (2.2 * t / dur)) / SR) * 0.08 * env
    return (out * 0.5 + whistle) * env


def reverse_swell(dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = t_axis(n)
    x = hp(rng.standard_normal(n), 4000)
    return x * (t / dur) ** 3 * 0.35


def reverb_ir(seconds: float = 3.2, damp: float = 6000) -> np.ndarray:
    n = int(seconds * SR)
    t = t_axis(n)
    ir = np.stack([rng.standard_normal(n), rng.standard_normal(n)], axis=1)
    ir *= np.exp(-t * 6.9 / seconds)[:, None]
    ir = lp(ir, damp)
    ir[: int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))[:, None]  # pre-delay feel
    return ir / np.sqrt((ir**2).sum(axis=0))


# ---------------------------------------------------------------- arrangement
def chord(names: str) -> list[float]:
    return [hz(m(x)) for x in names.split()]


def compose() -> np.ndarray:
    dry = np.zeros((N + SR * 5, 2))
    pad = np.zeros_like(dry)
    send = np.zeros_like(dry)  # reverb send
    sc = np.ones(dry.shape[0])  # sidechain gain (kick ducking)

    # --- pads (bar -> chord)
    pads = [
        (0.0, 2.6, "D3 A3 E4 F4"),  # Dm add9
        (2.5, 2.6, "Bb2 F3 A3 D4"),  # Bbmaj7
        (5.0, 2.6, "Bb2 F3 D4 F4"),  # Bb (title)
        (7.5, 2.6, "A2 F3 C4 F4"),  # F/A
        (10.0, 2.6, "D3 A3 D4 F4"),  # Dm
        (12.5, 2.6, "Bb2 F3 Bb3 D4"),  # Bb
        (15.0, 2.6, "F2 C3 A3 F4"),  # F
        (17.5, 2.6, "C3 G3 C4 E4"),  # C
        (20.0, 2.6, "G2 D3 Bb3 D4"),  # Gm
        (22.5, 2.6, "Bb2 F3 D4 F4"),  # Bb
        (25.0, 2.6, "F2 C3 A3 F4 A4"),  # F (big)
        (27.5, 2.6, "Bb2 F3 A3 C4 F4"),  # Bbmaj9 -> tail
    ]
    for start, d, ch in pads:
        bright = 4.5 if start < 5 else 6.5 if start < 25 else 8.0
        for f in chord(ch):
            g = 0.10 if start < 5 else 0.12
            place(pad, saw_pad(f, d + 0.6, bright), start - 0.05, g)
    # final F/A resolution over the tail
    for f in chord("F2 C3 A3 F4 C5"):
        place(pad, saw_pad(f, 3.2, 7), 28.6, 0.07)

    # --- intro shimmer: bells + drone
    place(dry, sub(hz(m("D2")), 5.0) * np.linspace(0, 1, int(5 * SR)) ** 1.5, 0.0, 0.25)
    for k, (note, at, pan) in enumerate([("A5", 0.3, -0.5), ("E6", 1.1, 0.5), ("D6", 1.9, -0.2), ("F6", 2.7, 0.4), ("A6", 3.4, -0.4)]):
        b = bell(hz(m(note)), 4.0)
        place(dry, b, at, 0.05, pan)
        place(send, b, at, 0.10, pan)
    place(dry, riser(2.0), 3.0, 0.22)
    place(dry, reverse_swell(1.2), 3.8, 0.3)

    # --- impacts
    for at, size in [(5.0, 1.0), (10.0, 0.45), (20.0, 0.6), (25.0, 1.25)]:
        imp = impact(size)
        place(dry, imp, at, 0.55)
        place(send, imp, at, 0.35)
    for at, g in [(5.0, 0.5), (20.0, 0.4), (25.0, 0.6)]:
        c = crash()
        place(dry, c, at, g)
        place(send, c, at, g * 0.5)

    # --- piano motif over the title (5-10 s): D5 . F5 E5 | C5 . A4 .
    motif = [(5.0, "D5"), (5.0 + 2 * BEAT, "F5"), (5.0 + 3 * BEAT, "E5"), (7.5, "C5"), (7.5 + 2 * BEAT, "A4"), (7.5 + 3 * BEAT, "C5")]
    for at, note in motif:
        p = piano(hz(m(note)), 2.4)
        place(dry, p, at, 0.16, 0.1)
        place(send, p, at, 0.22, 0.1)
    for at, note in [(5.0, "Bb2"), (7.5, "A2")]:
        place(dry, piano(hz(m(note)), 2.6), at, 0.12, -0.2)

    # --- rhythm section 10-25 s
    k = kick()
    for i in range(int((25.0 - 10.0) / BEAT)):
        at = 10.0 + i * BEAT
        place(dry, k, at, 0.40)
        i0 = int(at * SR)
        dn = int(0.32 * SR)
        duck = 1 - 0.45 * np.exp(-np.linspace(0, 5, dn))
        sc[i0 : i0 + dn] = np.minimum(sc[i0 : i0 + dn], duck)
    for i in range(int((25.0 - 12.5) / (BEAT / 2))):
        at = 12.5 + i * BEAT / 2
        place(dry, hat(open_=(i % 2 == 1)), at, 0.10 if i % 2 else 0.07, 0.35 if i % 2 else -0.35)
    for i in range(int((25.0 - 15.0) / BEAT)):
        if i % 2 == 1:
            c = clap()
            place(dry, c, 15.0 + i * BEAT, 0.35)
            place(send, c, 15.0 + i * BEAT, 0.25)
    # tom build into 25 s
    for i, f in enumerate(np.geomspace(140, 70, 8)):
        place(dry, tom(float(f)), 22.5 + 1.25 + i * BEAT / 4, 0.25 + 0.05 * i, (-1) ** i * 0.3)
    place(dry, riser(2.5), 22.5, 0.3)
    place(dry, reverse_swell(1.5), 23.5, 0.35)

    # --- 16th plucks (arpeggios of the current chord), 10-25 s
    arp_chords = [
        (10.0, "D4 F4 A4 D5"),
        (12.5, "D4 F4 Bb4 D5"),
        (15.0, "C4 F4 A4 C5"),
        (17.5, "C4 E4 G4 C5"),
        (20.0, "D4 G4 Bb4 D5"),
        (22.5, "D4 F4 Bb4 F5"),
    ]
    pattern = [0, 2, 1, 3, 2, 1, 3, 2]
    for start, ch in arp_chords:
        notes = chord(ch)
        for s in range(16):
            at = start + s * BEAT / 4
            f = notes[pattern[s % 8]] * (2 if (s // 8) and start >= 20 else 1)
            pl = pluck(f)
            vel = 0.09 if s % 4 == 0 else 0.06
            pan = 0.4 * np.sin(s * 0.9)
            place(dry, pl, at, vel, pan)
            place(send, pl, at, vel * 0.8, pan)

    # --- sub bass 10-25 s (root, pumping eighths)
    roots = [(10.0, "D2"), (12.5, "Bb1"), (15.0, "F1"), (17.5, "C2"), (20.0, "G1"), (22.5, "Bb1")]
    for start, r in roots:
        for e in range(8):
            place(dry, sub(hz(m(r)), BEAT / 2 * 0.95), start + e * BEAT / 2, 0.16 if e % 2 == 0 else 0.11)
    place(dry, sub(hz(m("F1")), 5.0), 25.0, 0.3)

    # --- final melody statement at 25 s (piano + bell, octave)
    for at, note in [(25.0, "A5"), (25.0 + 2 * BEAT, "C6"), (25.0 + 3 * BEAT, "A5"), (27.5, "F5")]:
        p = piano(hz(m(note)), 3.0)
        place(dry, p, at, 0.15, 0.15)
        place(send, p, at, 0.25, 0.15)
        b = bell(hz(m(note)), 4)
        place(send, b, at, 0.06, -0.3)

    # --- mix
    pad *= sc[:, None] ** 1.0
    send += pad * 0.6
    wet = np.stack([fftconvolve(send[:, ch], reverb_ir()[:, ch])[: send.shape[0]] for ch in range(2)], axis=1)
    mix = dry + pad + wet * 0.55
    mix = hp(mix, 28)
    mix = mix[:N]
    # fades
    t = t_axis(N)
    mix *= np.clip(t / 0.25, 0, 1)[:, None]
    mix *= np.clip((DUR - t) / 2.2, 0, 1)[:, None] ** 1.3
    # gentle glue + limiter
    peak = np.abs(mix).max()
    mix = np.tanh(1.4 * mix / peak) / np.tanh(1.4)
    return mix * 10 ** (-1.0 / 20)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    x = compose()
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(OUT), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    rms = np.sqrt((x**2).mean())
    print(f"wrote {OUT} ({DUR:.0f} s, RMS {20 * np.log10(rms):.1f} dBFS)")


if __name__ == "__main__":
    main()
