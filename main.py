"""world_dex/main.py
─────────────────────
A minimal backend + CLI for the World-Dex gadget.

NEW 2025-06-17
──────────────
• Fingerprints are now written as a Base-64 string (≈ 4 KB) instead of a
  768-element float list (≈ 30 KB).  Legacy list-style vectors remain
  readable for smooth migration.

Environment variables (all optional)
────────────────────────────────────
    DATA_DIR        – where ``*.json`` files live (default: ./data)
    OPENAI_API_KEY  – for descriptions / Q&A
    DEEPSEEK_API_KEY
    EMBED_DIM       – embedding length (default 768)
    SIM_THRESHOLD   – cosine dedupe threshold (0.85)
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import re
import uuid
from datetime import datetime
from typing import List, Optional, Union

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field  # noqa: F401  (Field kept for possible future use)
from tinydb import TinyDB, Query

# ─── ENV ───────────────────────────────────────────────────────────────────
load_dotenv()
DATA_DIR      = os.getenv("DATA_DIR", "./data")
OPENAI_KEY    = os.getenv("OPENAI_API_KEY")
DEEPSEEK_KEY  = os.getenv("DEEPSEEK_API_KEY")
EMBED_DIM     = int(os.getenv("EMBED_DIM", "768"))
SIM_THRESHOLD = float(os.getenv("SIM_THRESHOLD", "0.85"))

os.makedirs(DATA_DIR, exist_ok=True)

# ─── FINGERPRINT ENC/DEC ──────────────────────────────────────────────────
def _encode_fp(vec: List[float] | np.ndarray) -> str:
    """float32 → bytes → b64 str."""
    return base64.b64encode(np.asarray(vec, np.float32).tobytes()).decode("ascii")


def _decode_fp(b64: str) -> np.ndarray:
    """b64 str → float32 ndarray."""
    return np.frombuffer(base64.b64decode(b64.encode("ascii")), dtype=np.float32)


def _fp_to_array(fp: Union[str, List[float]]) -> np.ndarray:
    """Return an ndarray regardless of storage style (b64 str or raw list)."""
    if isinstance(fp, str):
        return _decode_fp(fp)
    return np.asarray(fp, dtype=np.float32)


# ─── DB HELPERS ───────────────────────────────────────────────────────────
def _slug(name: str) -> str:
    """Convert *Trees & Shrubs* → *trees_shrubs* for filenames."""
    return re.sub(r"[^A-Za-z0-9]+", "_", name.strip().lower()).strip("_")


def db_for_category(category: str) -> TinyDB:
    """Return TinyDB bound to ``./data/<slug>.json`` (creates if missing)."""
    fname = f"{_slug(category)}.json"
    return TinyDB(os.path.join(DATA_DIR, fname), indent=2, ensure_ascii=False)


# ─── NUMERIC ───────────────────────────────────────────────────────────────
def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


# ─── LLM CALL ─────────────────────────────────────────────────────────────
async def call_llm(context: str, prompt: str) -> str:
    """Ask OpenAI or DeepSeek; falls back if no key is set."""
    if OPENAI_KEY:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=OPENAI_KEY)
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=128,
            messages=[
                {"role": "system", "content": "You are a concise, factual object encyclopedia."},
                {"role": "user", "content": f"{context}\n\n{prompt}"},
            ],
            timeout=20,
        )
        return r.choices[0].message.content.strip()

    if DEEPSEEK_KEY:
        import httpx  # type: ignore
        r = httpx.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"},
            json={
                "model": "deepseek-chat",
                "max_tokens": 128,
                "messages": [
                    {"role": "system", "content": "You are a concise, factual object encyclopedia."},
                    {"role": "user", "content": f"{context}\n\n{prompt}"},
                ],
            },
            timeout=20,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    raise RuntimeError("No LLM key configured.")


# ─── QUICK-ADD (CLI) ──────────────────────────────────────────────────────
def quick_add(name: str, category: str) -> str:
    """Insert ``name`` into ``category`` JSON file (creates file if needed)."""
    db   = db_for_category(category)
    ObjQ = Query()

    # 1) deduplicate by name
    existing = db.table("objects").get(ObjQ.name == name)
    if existing:
        return existing["id"]

    # 2) placeholder embedding
    vec = np.random.default_rng().normal(size=EMBED_DIM).astype("float32")

    # 3) description
    try:
        desc = asyncio.run(
            call_llm(f"Object: {name}", "Give a one-sentence encyclopedic description.")
        )
    except Exception:
        desc = f"{name} recorded in the World-Dex."

    obj_id = str(uuid.uuid4())
    db.table("objects").insert(
        {
            "id": obj_id,
            "name": name,
            "fingerprint": _encode_fp(vec),  # << clean storage
            "thumbnail_url": None,
            "date_first_seen": datetime.utcnow().isoformat(),
            "facts": [desc],
        }
    )
    return obj_id


# ─── FASTAPI TYPES ────────────────────────────────────────────────────────
class ScanIn(BaseModel):
    name: str
    category: str
    fingerprint: Optional[List[float]] = None      # caller can still send raw list
    thumbnail_url: Optional[str] = None


class ScanOut(BaseModel):
    object_id: str
    status: str  # "new" or "known"


class AskIn(BaseModel):
    object_id: str
    category: str
    question: str


class AskOut(BaseModel):
    answer: str


# ─── FASTAPI APP ──────────────────────────────────────────────────────────
app = FastAPI(title="World-Dex backend (one-file-per-category)")


@app.post("/scan", response_model=ScanOut)
async def scan(item: ScanIn):
    db   = db_for_category(item.category)
    ObjQ = Query()

    # Normalise incoming fingerprint (if provided) for comparisons
    incoming_vec: Optional[np.ndarray] = (
        None if item.fingerprint is None else np.asarray(item.fingerprint, dtype=np.float32)
    )

    # 1) duplicate detection – by fingerprint
    if incoming_vec is not None:
        for row in db.table("objects"):
            row_vec = _fp_to_array(row["fingerprint"])
            if cosine(row_vec, incoming_vec) >= SIM_THRESHOLD:
                return ScanOut(object_id=row["id"], status="known")

    # 2) duplicate detection – by name
    existing = db.table("objects").get(ObjQ.name == item.name)
    if existing:
        return ScanOut(object_id=existing["id"], status="known")

    # 3) new entry
    obj_id = str(uuid.uuid4())
    vec    = incoming_vec if incoming_vec is not None else np.random.default_rng().normal(
        size=EMBED_DIM
    ).astype("float32")

    db.table("objects").insert(
        {
            "id":      obj_id,
            "name":    item.name,
            "fingerprint": _encode_fp(vec),          # << clean storage
            "thumbnail_url": item.thumbnail_url,
            "date_first_seen": datetime.utcnow().isoformat(),
            "facts":   [f"{item.name} was first scanned on {datetime.utcnow():%B %d %Y}."],
        }
    )
    return ScanOut(object_id=obj_id, status="new")


@app.post("/ask", response_model=AskOut)
async def ask(q: AskIn):
    db   = db_for_category(q.category)
    ObjQ = Query()
    obj  = db.table("objects").get(ObjQ.id == q.object_id)
    if not obj:
        raise HTTPException(404, "object not found in this category")

    context = (
        f"Object: {obj['name']}\n"
        f"Category: {q.category}\n"
        f"First seen: {obj['date_first_seen']}\n"
        f"Thumbnail: {obj.get('thumbnail_url', 'N/A')}\n"
        "Known facts:\n" + "\n".join("• " + f for f in obj["facts"])
    )
    answer = await call_llm(context, q.question)
    return AskOut(answer=answer)


# ─── CLI ENTRY-POINT ──────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="World-Dex CLI (category-file)")
    parser.add_argument("name", help="Object name, e.g. 'Maple Tree'")
    parser.add_argument(
        "--category",
        "-c",
        help="Category (default: last word pluralised)",
    )
    args = parser.parse_args()

    category = args.category or (args.name.split()[-1].capitalize() + "s")
    oid = quick_add(args.name, category)
    print(f"✅ {args.name} added to '{category}'  → id: {oid}")
