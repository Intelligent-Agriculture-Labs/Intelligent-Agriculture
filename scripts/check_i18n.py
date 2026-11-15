#!/usr/bin/env python3
"""Translation completeness checker for FieldShift (app + backend).

    python scripts/check_i18n.py            # report, exit 1 on any problem
    python scripts/check_i18n.py --quiet    # only the summary line per check

Checks
  1. app locales   app/src/i18n/locales/*.json: same keys as en.json, no empty values, same {{placeholders}}.
  2. backend catalogs  config/messages.yaml + config/messages/*.yaml + glossary.yaml + every other config YAML:
     any mapping with an `en` key is a translation node and must have every language (non-empty, same {placeholders}).
     Every crop in crops*.yaml needs a `crop_<id>` name entry whose English matches the crop's `name`.
  3. hard-coded English in backend Python (engine/ + science/ modules that build farmer-facing text): string literals
     and f-strings with two or more words outside docstrings, logging, exceptions, dict keys, subscripts and t() keys.
     Intentional English (citations, ids, developer text) carries an `# i18n: ok` comment on the same line.
  4. hard-coded English in app .tsx: JSX text and literal user-visible props (label/title/placeholder/...)
     outside t(); `{/* i18n: ok */}` or `// i18n: ok` on the line exempts it.

The same functions back backend/tests/test_i18n.py, so CI fails whenever a language misses a key.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP_LOCALES = ROOT / "app" / "src" / "i18n" / "locales"
APP_SRC = ROOT / "app" / "src"
BACKEND = ROOT / "backend" / "fieldshift"
CONFIG = BACKEND / "config"
LANGS = ("en", "es", "fr", "sw", "hi", "de")

# Python modules whose string literals can reach the farmer (cards, Why views, plans, labels).
PY_SCAN = [
    *sorted((BACKEND / "engine").glob("*.py")),
    *[
        BACKEND / "science" / f
        for f in (
            "rotation_plan.py",
            "pests.py",
            "globalrisk.py",
            "disease.py",
            "drought.py",
            "onset.py",
            "satellite.py",
        )
    ],
]
PY_SKIP_FILES = {"messages.py", "__init__.py"}
# Data tables / cached results whose English texts are translated by lookup (pest names and stages, drought levels,
# onset reasons, Sentinel-2 results localised when served): a literal is fine there if it equals the English of a
# catalog entry (placeholders compared as "{}").
PY_CATALOG_MATCHED = {
    "pests.py",
    "disease.py",
    "drought.py",
    "onset.py",
    "satellite.py",
    "satellite_service.py",
}
# Fields in YAML configs that are shown to farmers and must therefore be translation nodes (dict with `en`).
YAML_TEXT_FIELDS = {
    "pest_disease.yaml": ["summary", "caveats", "action", "name"],
}

_PY_PH = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?:[:!][^{}]*)?\}")
_APP_PH = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_WORD = re.compile(r"[A-Za-zÀ-ÿ]{2,}")


# ----------------------------------------------------------------------------------------------- app locales
def _flatten(d: dict[str, Any], p: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{p}.{k}" if p else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = str(v)
    return out


def check_app_locales() -> list[str]:
    errs: list[str] = []
    base = _flatten(json.loads((APP_LOCALES / "en.json").read_text(encoding="utf-8")))
    files = {p.stem: p for p in APP_LOCALES.glob("*.json")}
    for lg in LANGS:
        if lg not in files:
            errs.append(f"app: missing locale file {lg}.json")
            continue
        flat = _flatten(json.loads(files[lg].read_text(encoding="utf-8")))
        for k in sorted(set(base) - set(flat)):
            errs.append(f"app[{lg}]: missing key {k}")
        for k in sorted(set(flat) - set(base)):
            errs.append(f"app[{lg}]: extra key {k}")
        for k, v in flat.items():
            if not v.strip():
                errs.append(f"app[{lg}]: empty {k}")
            elif k in base and sorted(_APP_PH.findall(v)) != sorted(_APP_PH.findall(base[k])):
                errs.append(f"app[{lg}]: placeholders differ in {k}")
    return errs


# ----------------------------------------------------------------------------------------------- backend YAML
def _load(p: Path) -> Any:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _nodes(obj: Any, path: str) -> Iterator[tuple[str, dict[str, Any]]]:
    """Translation nodes (mappings with an `en` key) anywhere in a YAML tree."""
    if isinstance(obj, dict):
        if "en" in obj and all(isinstance(k, str) for k in obj):
            yield path, obj
            return
        for k, v in obj.items():
            yield from _nodes(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _nodes(v, f"{path}[{i}]")


def _leaf_strings(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [s for x in v.values() for s in _leaf_strings(x)]
    if isinstance(v, list):
        return [s for x in v for s in _leaf_strings(x)]
    return [] if v is None else [str(v)]


def _shape(v: Any) -> Any:
    if isinstance(v, dict):
        return {k: _shape(x) for k, x in v.items()}
    if isinstance(v, list):
        return len(v)
    return "s"


def check_node(where: str, node: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    en = node["en"]
    en_ph = sorted(p for s in _leaf_strings(en) for p in _PY_PH.findall(s))
    for lg in LANGS:
        v = node.get(lg)
        if v is None or not all(s.strip() for s in _leaf_strings(v)) or not _leaf_strings(v):
            errs.append(f"backend {where}: missing/empty '{lg}'")
            continue
        if _shape(v) != _shape(en):
            errs.append(f"backend {where}: '{lg}' has a different structure than 'en'")
        ph = sorted(p for s in _leaf_strings(v) for p in _PY_PH.findall(s))
        if ph != en_ph:
            errs.append(f"backend {where}: '{lg}' placeholders {ph} != en {en_ph}")
    return errs


def _text_field_errors(fname: str, obj: Any, fields: list[str], path: str = "") -> list[str]:
    errs: list[str] = []
    if isinstance(obj, dict):
        if "en" in obj:
            return errs
        for k, v in obj.items():
            if k in fields and (isinstance(v, str) or (isinstance(v, list) and v and isinstance(v[0], str))):
                errs.append(
                    f"backend {fname}{path}.{k}: English-only text (make it a {{en, es, ...}} mapping)"
                )
            else:
                errs.extend(_text_field_errors(fname, v, fields, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            errs.extend(_text_field_errors(fname, v, fields, f"{path}[{i}]"))
    return errs


def check_backend_catalogs() -> list[str]:
    errs: list[str] = []
    files = sorted(CONFIG.glob("*.yaml")) + sorted((CONFIG / "messages").glob("*.yaml"))
    seen: dict[str, str] = {}
    for p in files:
        data = _load(p) or {}
        rel = p.relative_to(CONFIG).as_posix()
        if p.parent.name == "messages" or p.name == "messages.yaml":
            for k, v in data.items():
                if k in seen:
                    errs.append(f"backend {rel}: duplicate key {k} (also in {seen[k]})")
                seen[k] = rel
                if not isinstance(v, dict) or "en" not in v:
                    # nested groups such as risk_words: {low: {en: ...}}
                    for w, n in _nodes(v, f"{rel}:{k}"):
                        errs.extend(check_node(w, n))
                    continue
                errs.extend(check_node(f"{rel}:{k}", v))
        else:
            for w, n in _nodes(data, rel):
                errs.extend(check_node(w, n))
        if p.name in YAML_TEXT_FIELDS:
            errs.extend(_text_field_errors(rel, data, YAML_TEXT_FIELDS[p.name]))
    names = {}
    for f in ("crops.yaml", "crops_extra.yaml"):
        names.update({k: v["name"] for k, v in (_load(CONFIG / f).get("crops") or {}).items()})
    cat = _load(CONFIG / "messages" / "crops.yaml") if (CONFIG / "messages" / "crops.yaml").exists() else {}
    for cid, name in names.items():
        node = cat.get(f"crop_{cid}")
        if not node:
            errs.append(f"backend crops: no translated name crop_{cid}")
        elif node.get("en") != name:
            errs.append(f"backend crops: crop_{cid}.en {node.get('en')!r} != crops.yaml name {name!r}")
    return errs


# ----------------------------------------------------------------------------------------------- Python literals
def _lit_text(n: ast.AST) -> str | None:
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    if isinstance(n, ast.JoinedStr):
        return "".join(
            v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}" for v in n.values
        )
    return None


def _call_name(n: ast.Call) -> str:
    f = n.func
    if isinstance(f, ast.Attribute):
        base = f.value.id if isinstance(f.value, ast.Name) else ""
        return f"{base}.{f.attr}"
    return f.id if isinstance(f, ast.Name) else ""


_SKIP_CALLS = re.compile(
    r"^(log|logger|logging|warnings|_log)\.\w+$|^(print|t|has|crop_name|crop_short|getattr|setattr|isinstance|open|re\.\w+|"
    r"\w+\.(get|startswith|endswith|split|rsplit|replace|strip|join|format|strftime|removesuffix|setdefault|"
    r"execute|executemany|cursor|fetchone|fetchall)|source_ref|cached|_cache_get|_cache_put|np\.\w+|Path|"
    r"dt\.date\.fromisoformat|ValueError|KeyError|RuntimeError|HTTPException|DataUnavailable)$"
)


def is_english_text(s: str) -> bool:
    if " " not in s.strip():
        return False
    if s.lstrip().startswith(("http", "SELECT", "INSERT", "UPDATE", "CREATE", "DELETE", "<", "%")):
        return False
    words = [w for w in _WORD.findall(s) if w.isascii()]
    return len(words) >= 2 and sum(1 for w in words if len(w) >= 3) >= 1


def scan_python(path: Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8")
    lines = src.splitlines()
    tree = ast.parse(src)
    skip: set[int] = set()

    def mark(node: ast.AST) -> None:
        for x in ast.walk(node):
            skip.add(id(x))

    for n in ast.walk(tree):
        body = getattr(n, "body", None)
        if isinstance(n, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                mark(first)
        if isinstance(n, ast.Raise | ast.Assert | ast.Compare):
            mark(n)
        elif isinstance(n, ast.Subscript):
            mark(n.slice)
        elif isinstance(n, ast.Dict):
            for k in n.keys:
                if k is not None:
                    mark(k)
        elif (isinstance(n, ast.Call) and _SKIP_CALLS.match(_call_name(n))) or (
            isinstance(n, ast.Assign)
            and any(isinstance(tg, ast.Name) and tg.id == "__all__" for tg in n.targets)
        ):
            mark(n)
        elif isinstance(n, ast.JoinedStr):
            for v in n.values:  # the f-string is judged as a whole
                if v is not n:
                    mark(v)
    out: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        if id(n) in skip:
            continue
        s = _lit_text(n)
        if s is None or not is_english_text(s):
            continue
        ln = getattr(n, "lineno", 0)
        end = getattr(n, "end_lineno", ln) or ln
        if any("i18n: ok" in lines[i - 1] for i in range(ln, end + 1) if 0 < i <= len(lines)):
            continue
        out.append((ln, s))
    return sorted(out)


def _skeleton(s: str) -> str:
    return re.sub(r"\{[^{}]*\}", "{}", s).strip()


def catalog_english() -> set[str]:
    """Skeletons of every English catalog text (messages + pest_disease names/stages)."""
    out: set[str] = set()
    files = [
        CONFIG / "messages.yaml",
        CONFIG / "pest_disease.yaml",
        *sorted((CONFIG / "messages").glob("*.yaml")),
    ]
    for p in files:
        data = _load(p) or {}
        for _, node in _nodes(data, p.name):
            out.update(_skeleton(x) for x in _leaf_strings(node["en"]))
        if p.name == "pest_disease.yaml":
            out.update(_skeleton(k) for k in (data.get("legacy_pest_events") or {}))
    return out


def check_python() -> list[str]:
    errs = []
    known = catalog_english()
    for p in PY_SCAN:
        if p.name in PY_SKIP_FILES or not p.exists():
            continue
        for ln, s in scan_python(p):
            sk = _skeleton(s)
            if p.name in PY_CATALOG_MATCHED and (sk in known or sk.removesuffix(" = {}") in known):
                continue
            short = s if len(s) < 90 else s[:87] + "..."
            errs.append(f"py {p.relative_to(ROOT).as_posix()}:{ln}: hard-coded text {short!r}")
    return errs


# ----------------------------------------------------------------------------------------------- app .tsx
_JSX_TEXT = re.compile(r">([^<>{}`]*[A-Za-z]{3,}[^<>{}`]*)<")
_JSX_PROP = re.compile(
    r"\b(label|title|subtitle|placeholder|accessibilityLabel|accessibilityHint|hint|message|text|caption)="
    r"(\"[^\"]*[A-Za-z]{2,}[^\"]*\"|\{\s*\"[^\"]*[A-Za-z]{2,}[^\"]*\"\s*\})"
)
_TSX_OK_VALUES = {'"OK"', '"YYYY-MM-DD"', '"XXXX-XXXX"'}


def scan_tsx(path: Path) -> list[tuple[int, str]]:
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if "i18n: ok" in line or s.startswith(("//", "*", "/*", "import ")):
            continue
        for m in _JSX_TEXT.finditer(line):
            txt = m.group(1).strip()
            # skip TS generics / comparisons that the regex catches (`a < b && c > d`)
            if txt and not re.search(r"[=&|;()]|=>", txt) and is_english_text(txt + " x"):
                out.append((i, txt))
        for m in _JSX_PROP.finditer(line):
            v = m.group(2).strip("{} ")
            if v not in _TSX_OK_VALUES:
                out.append((i, f"{m.group(1)}={v}"))
    return out


def check_tsx() -> list[str]:
    errs = []
    for p in sorted(APP_SRC.rglob("*.tsx")):
        if "__tests__" in p.parts:
            continue
        for ln, s in scan_tsx(p):
            errs.append(f"tsx {p.relative_to(ROOT).as_posix()}:{ln}: hard-coded text {s!r}")
    return errs


CHECKS = {
    "app locales": check_app_locales,
    "backend catalogs": check_backend_catalogs,
    "backend hard-coded text": check_python,
    "app hard-coded text": check_tsx,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--only", choices=list(CHECKS))
    a = ap.parse_args()
    bad = 0
    for name, fn in CHECKS.items():
        if a.only and name != a.only:
            continue
        errs = fn()
        bad += len(errs)
        if not a.quiet:
            for e in errs:
                print(e)
        print(f"[{'FAIL' if errs else ' OK '}] {name}: {len(errs)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
