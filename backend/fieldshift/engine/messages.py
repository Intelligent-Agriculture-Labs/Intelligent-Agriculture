from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config"

WEEKDAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "es": ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"],
    "fr": ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."],
    "sw": ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"],
    "hi": ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
    "de": ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"],
}


@lru_cache
def _messages() -> dict[str, Any]:
    with open(CONFIG / "messages.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def t(key: str, lang: str = "en", **kw: Any) -> str:
    m = _messages().get(key, {})
    tpl = m.get(lang) or m.get("en") or key
    return str(tpl).format(**kw)


def risk_word(risk: str, lang: str = "en") -> str:
    return str(_messages()["risk_words"][risk].get(lang) or _messages()["risk_words"][risk]["en"])


def day_label(d: dt.date, today: dt.date, lang: str = "en") -> str:
    delta = (d - today).days
    wd = WEEKDAYS.get(lang, WEEKDAYS["en"])[d.weekday()]
    if 0 <= delta <= 6:
        return f"{wd} {d.day}"
    return d.strftime("%d %b") if lang == "en" else f"{d.day}.{d.month}."
