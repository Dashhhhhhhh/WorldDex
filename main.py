"""
TinyDB-based “World-Dex” backend
────────────────────────────────
• One JSON file per user (DATA_DIR/pokedex_<user>.json)
• /scan :  check-or-add  object  (category auto-creates)
• /ask  :  ask LLM about that object
"""

from datetime import datetime
from typing import List, Optional
import os, uuid, random

import numpy as np
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from tinydb import TinyDB, Query

# ─── ENV / CONFIG ──────────────────────────────────────────────────────────
load_dotenv()
DATA_DIR        = os.getenv("DATA_DIR", "./data")
OPENAI_KEY      = os.getenv("OPENAI_API_KEY")
DEEPSEEK_KEY    = os.getenv("DEEPSEEK_API_KEY")
EMBED_DIM       = int(os.getenv("EMBED_DIM", "768"))
SIM_THRESHOLD   = float(os.getenv("SIM_THRESHOLD", "0.85"))

os.makedirs(DATA_DIR, exist_ok=True)


# ─── UTILS ─────────────────────────────────────────────────────────────────
def db_for(user_id: str) -> TinyDB:
    """Return (and auto-create) TinyDB file for this user."""
    return TinyDB(os.path.join(DATA_DIR, f"worlddex_{user_id}.json"),
                  indent=2, ensure_ascii=False)

def get_category_db(category_name: str) -> TinyDB:
    """Return TinyDB for a specific category."""
    return TinyDB(os.path.join(DATA_DIR, f"{category_name}.json"),
                  indent=2, ensure_ascii=False)

def cosine(a: List[float], b: List[float]) -> float:
    a, b = np.asarray(a), np.asarray(b)
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))

async def call_llm(context: str, question: str) -> str:
    """Minimal wrapper around OpenAI or DeepSeek chat-completion."""
    if OPENAI_KEY:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=256,
            messages=[
                {"role":"system",
                 "content":"You are a concise, factual object encyclopedia."},
                {"role":"user",
                 "content":f"Context:\n{context}\n\nQuestion: {question}"}])
        return resp.choices[0].message.content.strip()

    if DEEPSEEK_KEY:
        import httpx, json
        r = httpx.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {DEEPSEEK_KEY}"},
            json={
                "model":"deepseek-chat",
                "max_tokens":256,
                "messages":[
                    {"role":"system",
                     "content":"You are a concise, factual object encyclopedia."},
                    {"role":"user",
                     "content":f"Context:\n{context}\n\nQuestion: {question}"}
                ]},
            timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    raise RuntimeError("No LLM key configured")


# ─── Pydantic I/O MODELS ──────────────────────────────────────────────────
class ScanIn(BaseModel):
    user_id: str
    name: str
    family: str
    fingerprint: Optional[List[float]] = Field(
        None, description="768-dim CLIP vector; null allowed")
    thumbnail_url: Optional[str] = None

class ScanOut(BaseModel):
    object_id: str
    status: str            # “new” or “known”

class AskIn(BaseModel):
    user_id: str
    object_id: str
    question: str

class AskOut(BaseModel):
    answer: str


# ─── FASTAPI APP ──────────────────────────────────────────────────────────
app = FastAPI(title="World-Dex JSON backend")

@app.post("/scan", response_model=ScanOut)
async def scan(item: ScanIn):
    db   = db_for(item.user_id)
    ObjQ = Query()

    # 1. deduplicate only if we actually have a fingerprint
    if item.fingerprint:
        for row in db.table("objects"):
            if cosine(row["fingerprint"], item.fingerprint) >= SIM_THRESHOLD:
                return ScanOut(object_id=row["id"], status="known")

    # 2. ensure / create category
    cat_tbl = db.table("categories")
    cat     = cat_tbl.get(ObjQ.name == item.family)
    if not cat:
        cat = {"id": str(uuid.uuid4()), "name": item.family}
        cat_tbl.insert(cat)

    # 3. add object
    obj_id = str(uuid.uuid4())
    vec    = item.fingerprint or np.random.default_rng().normal(
                size=EMBED_DIM).astype("float32").tolist()

    db.table("objects").insert({
        "id": obj_id,
        "name": item.name,
        "category_id": cat["id"],
        "fingerprint": vec,
        "thumbnail_url": item.thumbnail_url,
        "date_first_seen": datetime.utcnow().isoformat(),
        "facts": [f"{item.name} was first scanned on "
                  f"{datetime.utcnow():%B %d %Y}."]
    })
    return ScanOut(object_id=obj_id, status="new")


@app.post("/ask", response_model=AskOut)
async def ask(q: AskIn):
    db   = db_for(q.user_id)
    ObjQ = Query()
    obj  = db.table("objects").get(ObjQ.id == q.object_id)
    if not obj:
        raise HTTPException(404, "object not found")

    cat  = db.table("categories").get(ObjQ.id == obj["category_id"])
    context = (
        f"Object: {obj['name']}\n"
        f"Category: {cat['name'] if cat else 'Unknown'}\n"
        f"First seen: {obj['date_first_seen']}\n"
        f"Thumbnail: {obj.get('thumbnail_url','N/A')}\n"
        "Known facts:\n" + "\n".join("• "+f for f in obj["facts"])
    )

    answer = await call_llm(context, q.question)
    return AskOut(answer=answer)
