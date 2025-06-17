#!/usr/bin/env python3
"""main.py — World‑Dex object ingester (OpenAI‑client ≥ 1.0 & DeepSeek)
──────────────────────────────────────────────────────────────────────────
Add a new object (e.g. a plant, rock, animal) to your World‑Dex catalogue:

    python main.py "Giant Sequoia"

Key features
─────────────
1. **LLM‑driven categorisation** – Ask an LLM for the best *broad, plural*
   category (e.g. "trees", "minerals", "mammals").
2. **Provider‑agnostic** – Works with OpenAI *or* DeepSeek (or any other
   OpenAI‑compatible endpoint) using the **≥ 1.0** client API.
3. **.env auto‑loading** – Secrets can live in `.env` (variable names are
   case‑insensitive, e.g. `deepseek_api_key`).
4. **Self‑building catalogue** – Each category lives in its own JSON file in
   `./data`, created on‑the‑fly when first used.
5. **Duplicate‑safe & legacy‑aware** – Detects duplicates even if old JSON
   files store entries as plain strings (pre‑v2 format).
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
import pathlib as _pl
import sys as _sys
from typing import List as _List, Tuple as _Tuple

# ───────────────────────────── Optional .env loader ─────────────────────────────
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv()
except ModuleNotFoundError:
    # No local secrets file – rely on process env.
    pass

# ───────────────────────────── OpenAI‑compatible client ─────────────────────────
try:
    from openai import OpenAI as _OpenAI  # ≥ 1.0 style client
except ModuleNotFoundError as exc:
    _sys.stderr.write("❗️ Install the 'openai' package (>=1.0):  pip install --upgrade openai\n")
    raise exc

# Case‑insensitive env lookup helper
_getenv = _os.getenv

def _env(name: str) -> str | None:
    return _getenv(name) or _getenv(name.lower())

# Gather credentials / endpoints
_OPENAI_KEY = _env("OPENAI_API_KEY")
_OPENAI_BASE = _env("OPENAI_API_BASE") or "https://api.openai.com/v1"
_DEEPSEEK_KEY = _env("DEEPSEEK_API_KEY")
_DEEPSEEK_BASE = _env("DEEPSEEK_API_BASE") or "https://api.deepseek.com/v1"

if _OPENAI_KEY:
    _CLIENT = _OpenAI(api_key=_OPENAI_KEY, base_url=_OPENAI_BASE)
elif _DEEPSEEK_KEY:
    _CLIENT = _OpenAI(api_key=_DEEPSEEK_KEY, base_url=_DEEPSEEK_BASE)
else:
    raise RuntimeError(
        "Set OPENAI_API_KEY/openai_api_key or DEEPSEEK_API_KEY/deepseek_api_key (via env vars or .env file)."
    )

_DEFAULT_MODEL = _env("LLM_MODEL") or ("gpt-4o-mini" if _OPENAI_KEY else "deepseek-chat")

# ─────────────────────────────── I/O helpers ────────────────────────────────────

_DATA_DIR = _pl.Path(__file__).with_suffix("").parent / "data"
_DATA_DIR.mkdir(exist_ok=True)

# unified chat helper (OpenAI client v1 style)

def _chat(
    system: str,
    user: str,
    *,
    max_tokens: int = 64,
    temperature: float = 0.3,
    model: str | None = None,
) -> str:
    """Send a chat completion request and return the assistant's text."""
    resp = _CLIENT.chat.completions.create(
        model=model or _DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()

# ─────────────────────── Taxonomy + description helpers ─────────────────────────

def _pluralise(noun: str) -> str:
    noun = noun.lower().strip()
    if noun.endswith("s"):
        return noun
    if noun.endswith("y") and noun[-2] not in "aeiou":
        return noun[:-1] + "ies"
    if noun.endswith(("sh", "ch", "x", "z")):
        return noun + "es"
    return noun + "s"


def infer_category(obj_name: str, existing: _List[str]) -> str:
    """Ask LLM for best category; ensures plural, lowercase."""
    system = (
        "You are a taxonomist for a handheld field notebook named World‑Dex. "
        "Given an object name and a list of existing categories, reply with the single best category for the object. "
        "Use lowercase, plural nouns (e.g. 'trees', 'minerals', 'mammals'). "
        "If none of the existing categories suit the object, invent a new one following the same format. "
        "Reply with only the category word, nothing else."
    )
    user = f"Object: {obj_name}\nExisting categories: {', '.join(existing) if existing else '(none)'}"
    suggestion = _chat(system, user, max_tokens=8)
    return _pluralise(suggestion)


def generate_description(obj_name: str) -> str:
    system = (
        "You are a concise but vivid field guide. In 1–2 sentences, describe the object so a curious hiker "
        "would recognise it in the wild. Avoid encyclopaedic dryness; keep it practical and engaging."
    )
    user = f"Describe: {obj_name}"
    return _chat(system, user, max_tokens=96, temperature=0.7)

# ─────────────────────────────── JSON persistence ───────────────────────────────

def _load(path: _pl.Path) -> list:
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            return _json.load(f)
    return []


def _save(path: _pl.Path, data: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)

# ────────────────────────────── Legacy migration ────────────────────────────────

def _upgrade_entries(entries: list) -> _Tuple[list, bool]:
    """Ensure each entry is a dict with 'name'. Return (new_entries, changed)."""
    changed = False
    upgraded: list = []
    for e in entries:
        if isinstance(e, dict) and "name" in e:
            upgraded.append(e)
        elif isinstance(e, str):  # pre‑v2 simple string format
            upgraded.append({
                "name": e,
                "description": "",  # unknown old description
                "added": "",  # unknown timestamp
            })
            changed = True
        else:
            # Skip unrecognised items but mark as changed so we rewrite clean list
            changed = True
    return upgraded, changed

# ─────────────────────────────────── main() ─────────────────────────────────────

def main() -> None:
    if len(_sys.argv) != 2:
        _sys.stderr.write("Usage: python main.py \"Object Name\"\n")
        _sys.exit(1)

    obj_name = _sys.argv[1].strip()
    if not obj_name:
        _sys.stderr.write("Object name cannot be empty.\n")
        _sys.exit(1)

    existing_cats = [p.stem for p in _DATA_DIR.glob("*.json")]
    category = infer_category(obj_name, existing_cats)
    file_path = _DATA_DIR / f"{category}.json"

    entries = _load(file_path)
    entries, upgraded = _upgrade_entries(entries)
    if upgraded:
        _save(file_path, entries)  # write back migrated data before further ops

    # Duplicate check (case‑insensitive)
    if any(e["name"].lower() == obj_name.lower() for e in entries):
        print(f"⚠️  '{obj_name}' already exists in category '{category}'. Nothing was added.")
        return

    description = generate_description(obj_name)
    new_entry = {
        "name": obj_name,
        "description": description,
        "added": _dt.datetime.utcnow().isoformat(timespec="seconds"),
    }
    entries.append(new_entry)
    _save(file_path, entries)

    rel = file_path.relative_to(_DATA_DIR.parent)
    print(f"✔ Added '{obj_name}' to {rel}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
