"""Rainy-season onset, cessation, false starts and sowing windows from daily rain and ET₀.

Published agroclimatic criteria (parameters in ``config/onset.yaml``; see docs/MODELS.md#rain-onset):

* **Climatological seasons** — anomalous accumulation of the daily rain climatology (Liebmann et al. 2012):
  a rainy season is a run of days whose smoothed climatological rain exceeds the annual mean (where the
  cumulative anomaly rises). Two seasons per year are allowed when the 2nd harmonic of the climatology is
  stronger than the 1st (Dunning, Black & Allan 2016). Works in both hemispheres and across New Year.
* **Onset** (Sivakumar 1988; Stern, Dennett & Garbutt 1981): first day of a 3-day period with ≥ 20 mm,
  starting with a wet day, with no dry spell longer than 7 days in the following 30 days.
* **False start**: an apparent onset (the rain criterion alone) followed by such a dry spell.
* **Cessation** (Stern et al. 1981; Frère & Popov 1979, FAO): first day after the earliest possible end on which
  a 100 mm soil store, filled by rain and emptied by ET₀, runs dry.

All functions are pure (numpy arrays + a contiguous daily date list), so they are unit-tested on synthetic series.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .climate import trend

CONFIG = Path(__file__).resolve().parents[1] / "config"
MONTH_LETTERS = "JFMAMJJASOND"


@lru_cache
def params() -> dict[str, Any]:
    with open(CONFIG / "onset.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class Criteria:
    onset_mm: float = 20.0
    onset_days: int = 3
    dry_day_mm: float = 1.0
    max_dry_spell_days: int = 7
    check_days: int = 30
    awc_mm: float = 100.0
    min_season_days: int = 20
    earliest_end_before_clim_end: int = 21
    end_confirm_days: int = 21

    @classmethod
    def from_config(cls) -> Criteria:
        return cls(**params()["criteria"])


# --------------------------------------------------------------------------- daily building blocks
def forward_sum(x: np.ndarray, n: int) -> np.ndarray:
    """acc[i] = x[i] + … + x[i+n-1]; NaN where the window runs past the end."""
    c = np.concatenate([[0.0], np.cumsum(np.nan_to_num(x))])
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[: len(x) - n + 1] = c[n:] - c[: len(x) - n + 1]
    return out


def is_trigger(rain: np.ndarray, acc: np.ndarray, i: int, crit: Criteria) -> bool:
    """Rain part of the onset criterion: ≥ onset_mm in onset_days, starting with a wet day."""
    return bool(rain[i] >= crit.dry_day_mm and np.isfinite(acc[i]) and acc[i] >= crit.onset_mm)


def dry_spell_failure(rain: np.ndarray, i: int, crit: Criteria, last: int | None = None) -> int | None:
    """Days after ``i`` at which a dry spell longer than the limit is complete within the check period,
    looking only at days up to index ``last`` (inclusive). None = no such spell (in the known days)."""
    last = len(rain) - 1 if last is None else min(last, len(rain) - 1)
    run = 0
    for j in range(1, crit.check_days + 1):
        k = i + j
        if k > last:
            return None
        run = run + 1 if rain[k] < crit.dry_day_mm else 0
        if run > crit.max_dry_spell_days:
            return j
    return None


def cessation_index(
    rain: np.ndarray, et0: np.ndarray, onset: int, earliest: int, limit: int, crit: Criteria
) -> tuple[int, bool]:
    """Water-balance end of season: first day ≥ ``earliest`` with an empty store that is not followed by a
    renewed onset-sized rain (``onset_mm`` in ``onset_days``) within ``end_confirm_days``. A store that runs
    dry in a mid-season dry spell and is refilled afterwards does not end the season (Stern et al. 1981
    practice; FAO length-of-growing-period logic). Returns (index, censored)."""
    s = 0.0
    limit = min(limit, len(rain) - 1)
    for k in range(onset, limit + 1):
        e = et0[k] if np.isfinite(et0[k]) else 5.0  # Stern et al. used a fixed 5 mm/day where E is unknown
        s = min(crit.awc_mm, max(0.0, s + float(rain[k]) - float(e)))
        if k >= earliest and s <= 0.0:
            ahead = rain[k + 1 : min(limit + 1, k + 1 + crit.end_confirm_days)]  # never look past ``limit``
            refill = len(ahead) >= crit.onset_days and bool(
                np.any(np.convolve(np.nan_to_num(ahead), np.ones(crit.onset_days), "valid") >= crit.onset_mm)
            )
            if not refill:
                return k, False
    return limit, True


# --------------------------------------------------------------------------- climatology of the seasons
def _doy(d: dt.date) -> int:
    return min(d.timetuple().tm_yday - 1, 364)


def daily_climatology(dates: list[dt.date], x: np.ndarray, smooth: int) -> np.ndarray:
    """365 mean values (complete years only), circularly smoothed with a ``smooth``-day moving average."""
    n = min(len(dates), len(x))
    doy = np.array([_doy(d) for d in dates[:n]])
    v = np.asarray(x[:n], float)
    ok = np.isfinite(v)
    s = np.bincount(doy[ok], weights=v[ok], minlength=365)
    c = np.bincount(doy[ok], minlength=365)
    clim = np.where(c > 0, s / np.maximum(c, 1), np.nan)
    clim = np.where(np.isfinite(clim), clim, np.nanmean(clim) if np.isfinite(clim).any() else 0.0)
    k = np.ones(smooth) / smooth
    ext = np.concatenate([clim[-smooth:], clim, clim[:smooth]])
    return np.convolve(ext, k, mode="same")[smooth:-smooth]


def harmonic_ratio(clim: np.ndarray) -> float:
    f = np.fft.rfft(clim - clim.mean())
    a1 = abs(f[1])
    return float(abs(f[2]) / a1) if a1 > 0 else 0.0


@dataclass
class ClimSeason:
    key: str  # "s1", "s2" (in calendar order of onset)
    label: str  # month initials of the climatological season, e.g. "MAM", "OND", "JJAS"
    onset_doy: int  # 0-based day of year of the climatological onset
    length: int  # days to the climatological cessation
    rain_share: float  # share of annual rain falling in the season
    search_before: int = 45
    search_after: int = 60
    gap_after: int = 365  # days from climatological cessation to the next season's climatological onset

    def anchor(self, year: int) -> dt.date:
        md = dt.date(2001, 1, 1) + dt.timedelta(days=self.onset_doy)  # same calendar day in leap years
        return dt.date(year, md.month, md.day)


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def _label(onset_doy: int, length: int) -> str:
    d0 = dt.date(2001, 1, 1) + dt.timedelta(days=onset_doy)
    d1 = d0 + dt.timedelta(days=max(0, length - 1))
    m0, m1 = d0.month - 1, d1.month - 1
    if d0.day > 20:  # season starting in the last third of a month is named from the next month
        m0 = (m0 + 1) % 12
    if d1.day < 10:
        m1 = (m1 - 1) % 12
    n = (m1 - m0) % 12 + 1
    return "".join(MONTH_LETTERS[(m0 + k) % 12] for k in range(min(n, 6)))


def climatological_seasons(
    dates: list[dt.date], rain: np.ndarray, cfg: dict[str, Any] | None = None
) -> tuple[list[ClimSeason], dict[str, Any]]:
    """Rainy seasons of the mean annual cycle (Liebmann et al. 2012; Dunning et al. 2016)."""
    cfg = cfg or params()["seasons"]
    clim = daily_climatology(dates, rain, int(cfg["smooth_days"]))
    ratio = harmonic_ratio(clim)
    bimodal = ratio > float(cfg["bimodal_ratio"])
    mean = float(clim.mean())
    i0 = int(np.argmin(clim))  # rotate so that the driest day is first: no run crosses the array edge
    rot = np.roll(clim, -i0)
    runs = _runs(rot > mean)
    gap = int(cfg["merge_gap_bimodal" if bimodal else "merge_gap_unimodal"])
    merged: list[tuple[int, int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < gap:
            merged[-1] = (merged[-1][0], r[1])
        else:
            merged.append(r)
    merged = [r for r in merged if r[1] - r[0] >= int(cfg["min_run_days"])]
    total = float(rot.sum()) or 1.0
    merged.sort(key=lambda r: -float(rot[r[0] : r[1]].sum()))
    keep = sorted(merged[: 2 if bimodal else 1])
    out: list[ClimSeason] = []
    for s, e in keep:
        od = (s + i0) % 365
        out.append(
            ClimSeason(
                key="",
                label=_label(od, e - s),
                onset_doy=od,
                length=e - s,
                rain_share=round(float(rot[s:e].sum()) / total, 3),
            )
        )
    out.sort(key=lambda c: c.onset_doy)
    for k, c in enumerate(out):
        c.key = f"s{k + 1}"
        prev = out[k - 1] if len(out) > 1 else c
        nxt = out[(k + 1) % len(out)]
        gap_before = (c.onset_doy - (prev.onset_doy + prev.length)) % 365 if len(out) > 1 else 365 - c.length
        c.gap_after = (nxt.onset_doy - (c.onset_doy + c.length)) % 365 if len(out) > 1 else 365 - c.length
        c.search_before = int(min(cfg["search_before_days"], max(10, gap_before - 10)))
        c.search_after = int(min(cfg["search_after_days"], max(20, c.length - 15)))
    info = {
        "harmonic_ratio": round(ratio, 2),
        "regime": "bimodal" if len(out) == 2 else ("unimodal" if out else "none"),
        "mean_mm_day": round(mean, 2),
        "clim": clim,
    }
    return out, info


# --------------------------------------------------------------------------- one season instance
@dataclass
class Event:
    """An apparent onset (rain criterion met). ``fail_day`` = day the damaging dry spell completed, or None."""

    offset: int  # days after the climatological onset date of that year
    fail_day: int | None


@dataclass
class SeasonYear:
    year: int
    onset: dt.date | None
    cessation: dt.date | None
    censored: bool
    first_apparent: dt.date | None
    first_false: bool | None
    false_starts: int
    events: list[Event] = field(default_factory=list)

    @property
    def length(self) -> int | None:
        return (self.cessation - self.onset).days if self.onset and self.cessation else None


def _window(cs: ClimSeason, year: int) -> tuple[dt.date, dt.date, dt.date]:
    a = cs.anchor(year)
    return a - dt.timedelta(days=cs.search_before), a + dt.timedelta(days=cs.search_after), a


def detect_season(
    dates: list[dt.date],
    rain: np.ndarray,
    et0: np.ndarray,
    cs: ClimSeason,
    year: int,
    crit: Criteria,
    last: int | None = None,
) -> SeasonYear | None:
    """Onset, false starts and cessation of season ``cs`` in ``year``, using data up to index ``last``.
    Returns None when the record does not cover the search window and the cessation horizon."""
    last = len(dates) - 1 if last is None else last
    ws, we, a = _window(cs, year)
    i_ws, i_we = (ws - dates[0]).days, (we - dates[0]).days
    cess_clim = (a - dates[0]).days + cs.length
    limit = cess_clim + min(90, max(30, cs.gap_after - 10))
    if i_ws < 0 or limit > last:
        return None
    acc = forward_sum(rain[: last + 1], crit.onset_days)
    onset_i: int | None = None
    events: list[Event] = []
    count_from = i_ws
    for i in range(i_ws, i_we + 1):
        if not is_trigger(rain, acc, i, crit):
            continue
        fail = dry_spell_failure(rain, i, crit, last)
        if i >= count_from:
            events.append(Event((dates[i] - a).days, fail))
            count_from = i + (fail or crit.check_days)
        if fail is None:
            onset_i = i
            break
    first = events[0] if events else None
    if onset_i is None:
        return SeasonYear(
            year,
            None,
            None,
            False,
            a + dt.timedelta(days=first.offset) if first else None,
            (first.fail_day is not None) if first else None,
            len(events),
            events,
        )
    earliest = max(onset_i + crit.min_season_days, cess_clim - crit.earliest_end_before_clim_end)
    ci, censored = cessation_index(rain, et0, onset_i, earliest, limit, crit)
    return SeasonYear(
        year,
        dates[onset_i],
        dates[ci],
        censored,
        a + dt.timedelta(days=first.offset) if first else None,
        (first.fail_day is not None) if first else None,
        sum(e.fail_day is not None for e in events),
        events,
    )


# --------------------------------------------------------------------------- climatology product
def _pct(vals: list[float], q: float) -> float | None:
    return float(np.percentile(vals, q)) if vals else None


def _md(d: dt.date) -> str:
    return d.strftime("%d %b")


@dataclass
class SeasonClimatology:
    season: ClimSeason
    years: list[SeasonYear]

    @property
    def onset_offsets(self) -> list[int]:
        return [(y.onset - self.season.anchor(y.year)).days for y in self.years if y.onset]

    @property
    def cessation_offsets(self) -> list[int]:
        return [(y.cessation - self.season.anchor(y.year)).days for y in self.years if y.cessation]

    @property
    def lengths(self) -> list[int]:
        return [y.length for y in self.years if y.length is not None]

    @property
    def events(self) -> list[Event]:
        return [e for y in self.years for e in y.events]

    def false_start_pct(self, years: list[SeasonYear] | None = None) -> float | None:
        ys = [y for y in (years or self.years) if y.first_false is not None]
        return round(100 * float(np.mean([y.first_false for y in ys])), 1) if ys else None

    def failed_pct(self) -> float | None:
        return round(100 * float(np.mean([y.onset is None for y in self.years])), 1) if self.years else None

    def date_at(self, offset: float, year: int) -> dt.date:
        return self.season.anchor(year) + dt.timedelta(days=round(offset))

    def summary(self, ref_year: int, split_year: int) -> dict[str, Any]:
        on, ce, ln = self.onset_offsets, self.cessation_offsets, self.lengths
        cs = self.season

        def dist(vals: list[int], as_date: bool) -> dict[str, Any] | None:
            if not vals:
                return None
            qs = {f"p{q}": _pct([float(v) for v in vals], q) for q in (10, 20, 50, 80, 90)}
            if as_date:
                return {k: _md(self.date_at(v, ref_year)) for k, v in qs.items() if v is not None}
            return {k: round(v) for k, v in qs.items() if v is not None}

        yrs = [y.year for y in self.years]
        onset_vals: list[float | None] = [
            float((y.onset - cs.anchor(y.year)).days) if y.onset else None for y in self.years
        ]
        len_vals: list[float | None] = [float(y.length) if y.length is not None else None for y in self.years]
        ces_vals: list[float | None] = [
            float((y.cessation - cs.anchor(y.year)).days) if y.cessation else None for y in self.years
        ]
        t_on, p_on = trend(yrs, onset_vals)
        t_len, p_len = trend(yrs, len_vals)
        t_ces, p_ces = trend(yrs, ces_vals)
        early = [y for y in self.years if y.year < split_year]
        late = [y for y in self.years if y.year >= split_year]
        return {
            "key": cs.key,
            "label": cs.label,
            "climatological_onset": _md(cs.anchor(ref_year)),
            "climatological_length_days": cs.length,
            "rain_share": cs.rain_share,
            "n_years": len(self.years),
            "onset": dist(on, True),
            "cessation": dist(ce, True),
            "length_days": dist(ln, False),
            "false_start_pct": self.false_start_pct(),
            "failed_pct": self.failed_pct(),
            "trend": {
                "onset_days_per_decade": round(t_on, 1),
                "onset_p": round(p_on, 3),
                "cessation_days_per_decade": round(t_ces, 1),
                "cessation_p": round(p_ces, 3),
                "length_days_per_decade": round(t_len, 1),
                "length_p": round(p_len, 3),
                "split_year": split_year,
                "false_start_pct_before": self.false_start_pct(early) if early else None,
                "false_start_pct_since": self.false_start_pct(late) if late else None,
                "median_onset_before": _md(self.date_at(np.median(o), ref_year))
                if (o := [(y.onset - cs.anchor(y.year)).days for y in early if y.onset])
                else None,
                "median_onset_since": _md(self.date_at(np.median(o2), ref_year))
                if (o2 := [(y.onset - cs.anchor(y.year)).days for y in late if y.onset])
                else None,
            },
            "years": [
                {
                    "year": y.year,
                    "onset": y.onset.isoformat() if y.onset else None,
                    "cessation": y.cessation.isoformat() if y.cessation else None,
                    "length_days": y.length,
                    "first_apparent_onset": y.first_apparent.isoformat() if y.first_apparent else None,
                    "false_start": y.first_false,
                    "false_starts": y.false_starts,
                }
                for y in self.years
            ],
        }


def false_start_probability(
    events: list[Event], offset: int, days_ok: int, window: int, min_events: int
) -> tuple[float | None, int]:
    """P(damaging dry spell | apparent onset near ``offset`` and no such spell in the first ``days_ok`` days),
    from the site's history of apparent onsets. Returns (probability 0–1, number of events used)."""
    near = [e for e in events if abs(e.offset - offset) <= window]
    if len(near) < min_events:
        near = events
    pool = [e for e in near if e.fail_day is None or e.fail_day > days_ok]
    if not pool:
        return None, 0
    return float(np.mean([e.fail_day is not None for e in pool])), len(pool)


@dataclass
class SiteClimatology:
    seasons: list[SeasonClimatology]
    info: dict[str, Any]
    applicable: bool
    reason: str
    dry_days: int


def site_climatology(
    dates: list[dt.date],
    rain: np.ndarray,
    et0: np.ndarray,
    lat: float,
    last: int | None = None,
    crit: Criteria | None = None,
) -> SiteClimatology:
    """Seasons, per-year onsets/cessations and applicability for one location (data up to index ``last``)."""
    crit = crit or Criteria.from_config()
    last = len(dates) - 1 if last is None else min(last, len(dates) - 1)
    d, r, e = dates[: last + 1], np.nan_to_num(rain[: last + 1]), et0[: last + 1]
    # complete years only for the climatology
    y_last = d[-1].year - (0 if d[-1].month == 12 and d[-1].day == 31 else 1)
    n_cl = next((k for k in range(len(d) - 1, -1, -1) if d[k].year <= y_last), len(d) - 1) + 1
    cs_list, info = climatological_seasons(d[:n_cl], r[:n_cl])
    e_clim = daily_climatology(d[:n_cl], e[:n_cl], int(params()["seasons"]["smooth_days"]))
    dry_days = int(np.sum(info["clim"] < 0.5 * e_clim))
    app = params()["applicability"]
    if abs(lat) > float(app["max_abs_lat"]):
        applicable, reason = False, f"outside the tropics and subtropics (|latitude| > {app['max_abs_lat']}°)"
    elif not cs_list:
        applicable, reason = False, "no distinct rainy season in the climatology"
    elif dry_days < int(app["min_dry_days"]):
        applicable, reason = (
            False,
            f"no real dry season (only {dry_days} days with rain < half of ET₀), so rain onset rarely limits sowing",
        )
    else:
        applicable, reason = True, "rain-fed tropical/monsoon setting with a distinct dry season"
    seasons = []
    for cs in cs_list:
        ys = []
        for y in range(d[0].year - 1, d[-1].year + 1):
            sy = detect_season(d, r, e, cs, y, crit)
            if sy is not None:
                ys.append(sy)
        seasons.append(SeasonClimatology(cs, ys))
    return SiteClimatology(seasons, info, applicable, reason, dry_days)


# --------------------------------------------------------------------------- live status
@dataclass
class Status:
    season: SeasonClimatology
    year: int
    phase: str  # before | not_started | forecast | started | false_start | established | ended | failed
    window_start: dt.date
    window_end: dt.date
    onset: dt.date | None = None
    onset_in_forecast: bool = False
    false_pct: float | None = None
    false_n: int = 0
    days_checked: int = 0
    last_false_start: dt.date | None = None
    cessation: dt.date | None = None
    rain_since_window_mm: float = 0.0
    notes: list[str] = field(default_factory=list)


def _instance(site: SiteClimatology, today: dt.date) -> tuple[SeasonClimatology, int] | None:
    """The season instance running now (from its search window to its late (p80) end), else the next one."""
    cands = []
    for sc in site.seasons:
        ce = sc.cessation_offsets
        end_off = _pct([float(c) for c in ce], 80) if ce else float(sc.season.length + 30)
        for y in (today.year - 1, today.year, today.year + 1):
            ws, we, a = _window(sc.season, y)
            end = max(we, a + dt.timedelta(days=round(end_off or 0)))
            cands.append((ws, end, sc, y))
    current = [c for c in cands if c[0] <= today <= c[1]]
    if current:
        c = max(current, key=lambda c: c[0])
        return c[2], c[3]
    upcoming = [c for c in cands if c[0] > today]
    if not upcoming:
        return None
    c = min(upcoming, key=lambda c: c[0])
    return c[2], c[3]


def season_status(
    dates: list[dt.date],
    rain: np.ndarray,
    et0: np.ndarray,
    i_today: int,
    site: SiteClimatology,
    crit: Criteria | None = None,
) -> Status | None:
    """Where this season stands today. Days after ``i_today`` are forecast (up to the end of the arrays)."""
    crit = crit or Criteria.from_config()
    cfg = params()["advice"]
    today = dates[i_today]
    inst = _instance(site, today)
    if inst is None:
        return None
    sc, year = inst
    ws, we, a = _window(sc.season, year)
    st = Status(sc, year, "before", ws, we)
    if today < ws:
        return st
    r = np.nan_to_num(rain)
    last = len(dates) - 1
    i_ws, i_we = (ws - dates[0]).days, (we - dates[0]).days
    st.rain_since_window_mm = round(float(r[max(0, i_ws) : i_today + 1].sum()), 1)
    acc = forward_sum(r, crit.onset_days)
    found = None
    for i in range(max(0, i_ws), min(i_we, last - crit.onset_days + 1) + 1):
        if not is_trigger(r, acc, i, crit):
            continue
        fail = dry_spell_failure(r, i, crit, last)
        if fail is not None:
            if i + fail <= i_today:
                st.last_false_start = dates[i]
            continue
        found = i
        break
    if found is None:
        if st.last_false_start is not None and today <= we + dt.timedelta(days=crit.check_days):
            st.phase = "false_start"
        else:
            st.phase = "failed" if today > we else "not_started"
        return st
    st.onset = dates[found]
    st.onset_in_forecast = found + crit.onset_days - 1 > i_today
    st.days_checked = min(crit.check_days, last - found)
    if st.onset_in_forecast:
        st.phase = "forecast"
        return st
    if found + crit.check_days <= i_today:
        st.phase = "established"
        earliest = max(
            found + crit.min_season_days,
            (a - dates[0]).days + sc.season.length - crit.earliest_end_before_clim_end,
        )
        ci, censored = cessation_index(r, et0, found, earliest, i_today, crit)
        if not censored:
            st.phase, st.cessation = "ended", dates[ci]
        return st
    st.phase = "started"
    p, n = false_start_probability(
        sc.events,
        (st.onset - a).days,
        st.days_checked,
        int(cfg["conditional_window_days"]),
        int(cfg["min_events"]),
    )
    st.false_pct = round(100 * p) if p is not None else None
    st.false_n = n
    return st


# --------------------------------------------------------------------------- sowing windows per crop
def need_days(stages: list[float]) -> int:
    """Days from sowing to the end of the mid-season (grain fill); the late (ripening) stage of FAO-56
    can run on stored soil water after the rains end."""
    return int(round(sum(stages[:3])))


def sowing_windows(
    sc: SeasonClimatology,
    year: int,
    start: dt.date,
    crops: list[tuple[str, str, list[float]]],
    reliability: float,
) -> dict[str, Any]:
    """Sowing window per crop, from ``start``: the crop must reach the end of grain fill (FAO-56 stages)
    before the season's water-balance end. ``fit_pct`` = share of past seasons in which sowing on ``start``
    would have achieved that; ``sow_until`` = last date that still works in ``reliability`` of seasons;
    ``max_variety_days`` = the longest total cycle that fits in ``reliability`` of seasons."""
    ce = sc.cessation_offsets
    if not ce:
        return {"end_of_season": None, "reliability": reliability, "max_cycle_days": None, "crops": []}
    ends = sorted(sc.date_at(float(c), year) for c in ce)
    q = 100 * (1 - reliability)
    end = sc.date_at(_pct([float(c) for c in ce], q) or 0.0, year)
    avail = (end - start).days
    avail_med = (sc.date_at(float(np.median(ce)), year) - start).days
    rows = []
    for cid, name, stages in crops:
        total = int(round(sum(stages)))
        need = need_days(stages)
        until = end - dt.timedelta(days=need)
        fits = until >= start
        fit_pct = round(100 * float(np.mean([(e - start).days >= need for e in ends])))
        rows.append(
            {
                "crop": cid,
                "name": name,
                "cycle_days": total,
                "need_days": need,
                "sow_from": start.isoformat(),
                "sow_until": until.isoformat() if fits else None,
                "fits": fits,
                "fit_pct": fit_pct,
                "max_variety_days": max(0, int(avail * total / need)) if need else None,
                "max_variety_days_half": max(0, int(avail_med * total / need)) if need else None,
            }
        )
    return {
        "end_of_season": end.isoformat(),
        "reliability": reliability,
        "max_cycle_days": max(0, avail),
        "crops": rows,
    }
