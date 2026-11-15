from __future__ import annotations

import datetime as dt
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"
LANGS = ("en", "es", "fr", "sw", "hi", "de")

WEEKDAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
    "fr": ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."],
    "sw": ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"],
    "hi": ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
}

MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"],
    "fr": ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
    "sw": ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"],
    "hi": ["जन॰", "फ़र॰", "मार्च", "अप्रैल", "मई", "जून", "जुल॰", "अग॰", "सित॰", "अक्तू॰", "नव॰", "दिस॰"],
    "de": ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez."],
}
MONTHS_LONG = {
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "es": [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ],
    "fr": [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ],
    "sw": [
        "Januari",
        "Februari",
        "Machi",
        "Aprili",
        "Mei",
        "Juni",
        "Julai",
        "Agosti",
        "Septemba",
        "Oktoba",
        "Novemba",
        "Desemba",
    ],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्तूबर", "नवंबर", "दिसंबर"],
    "de": [
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ],
}


def day_month(d: dt.date, lang: str = "en") -> str:
    """Localised "15 Mar" (the strftime("%d %b") of every language)."""
    m = MONTHS.get(lang, MONTHS["en"])[d.month - 1]
    if lang == "de":
        return f"{d.day}. {m}"
    return f"{d.day:02d} {m}" if lang == "en" else f"{d.day} {m}"


def month_name(month: int, lang: str = "en") -> str:
    return MONTHS_LONG.get(lang, MONTHS_LONG["en"])[month - 1]


@lru_cache
def _messages() -> dict[str, Any]:
    """messages.yaml plus every config/messages/*.yaml (one file per module); keys must be unique."""
    with open(CONFIG / "messages.yaml", encoding="utf-8") as f:
        out: dict[str, Any] = yaml.safe_load(f)
    for p in sorted((CONFIG / "messages").glob("*.yaml")):
        with open(p, encoding="utf-8") as f:
            for k, v in (yaml.safe_load(f) or {}).items():
                if k in out:
                    raise ValueError(f"duplicate message key {k!r} in {p.name}")
                out[k] = v
    return out


def t(key: str, lang: str = "en", **kw: Any) -> str:
    """Message template `key` in `lang` (English fallback), filled with str.format (format specs allowed)."""
    m = _messages().get(key, {})
    tpl = m.get(lang) or m.get("en") or key
    return str(tpl).format(**kw)


@lru_cache
def _patterns(prefix: str) -> list[tuple[re.Pattern[str], str]]:
    """English templates of all keys with `prefix` as regexes (placeholders match any text)."""
    out = []
    for k, v in _messages().items():
        if not k.startswith(prefix) or not isinstance(v, dict) or "en" not in v:
            continue
        parts = re.split(r"\{(\w+)\}", str(v["en"]))
        rx = "".join(re.escape(p) if i % 2 == 0 else f"(?P<{p}>.+?)" for i, p in enumerate(parts))
        out.append((re.compile(f"^{rx}$", re.S), k))
    return out


def localize_text(s: str, prefix: str, lang: str) -> str:
    """Translate an English text produced from a `prefix*` template (e.g. a cached result) into `lang`."""
    if lang == "en":
        return s
    for rx, key in _patterns(prefix):
        m = rx.match(s)
        if m:
            kw = {k: localize_text(v, prefix, lang) for k, v in m.groupdict().items()}
            return t(key, lang, **kw)
    if ", " in s:  # lists such as "mean NDVI, peak NDVI"
        parts = [localize_text(x, prefix, lang) for x in s.split(", ")]
        return ", ".join(parts)
    return s


def localize_tree(obj: Any, prefix: str, lang: str) -> Any:
    """`localize_text` applied to every string in a JSON-like structure (dict keys untouched)."""
    if lang == "en":
        return obj
    if isinstance(obj, str):
        return localize_text(obj, prefix, lang)
    if isinstance(obj, list):
        return [localize_tree(x, prefix, lang) for x in obj]
    if isinstance(obj, dict):
        return {k: localize_tree(v, prefix, lang) for k, v in obj.items()}
    return obj


def has(key: str) -> bool:
    return key in _messages()


def word(prefix: str, ident: str, lang: str = "en") -> str:
    """Translated vocabulary item `<prefix>_<ident>` (e.g. stage_mid, irr_drip, soil_clay); the id if unknown."""
    key = f"{prefix}_{ident}"
    return t(key, lang) if key in _messages() else ident.replace("_", " ")


def crop_name(cid: str, lang: str = "en", fallback: str | None = None) -> str:
    """Crop display name in `lang` ("Name (detail)"); falls back to `fallback` or the id."""
    m = _messages().get(f"crop_{cid}")
    if not m:
        return fallback or cid.replace("_", " ")
    return str(m.get(lang) or m["en"])


def crop_short(cid: str, lang: str = "en", fallback: str | None = None) -> str:
    """Crop name without the parenthesised detail ("Maize (grain)" -> "Maize")."""
    return crop_name(cid, lang, fallback).split(" (")[0]


@lru_cache
def _crop_ids_by_name() -> dict[str, str]:
    return {
        str(v["en"]): k[5:] for k, v in _messages().items() if k.startswith("crop_") and isinstance(v, dict)
    }


def tr_crop(name: str, lang: str = "en") -> str:
    """Translate an English crop display name (crops.yaml `name`) to `lang`; unknown names pass through."""
    cid = _crop_ids_by_name().get(name)
    return crop_name(cid, lang, name) if cid else name


def crop_names(cid: str) -> dict[str, str]:
    m = _messages().get(f"crop_{cid}") or {}
    return {lg: str(m.get(lg) or m.get("en") or cid) for lg in LANGS}


def risk_word(risk: str, lang: str = "en") -> str:
    return str(_messages()["risk_words"][risk].get(lang) or _messages()["risk_words"][risk]["en"])


def day_label(d: dt.date, today: dt.date, lang: str = "en") -> str:
    delta = (d - today).days
    wd = WEEKDAYS.get(lang, WEEKDAYS["en"])[d.weekday()]
    if 0 <= delta <= 6:
        return f"{wd} {d.day}"
    return d.strftime("%d %b") if lang == "en" else f"{d.day}.{d.month}."
