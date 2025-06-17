#!/usr/bin/env python
"""
pokedex CLI – talk to the local FastAPI backend (main.py).

Dependencies
------------
pip install typer[all] requests python-dotenv \
            torch open_clip_torch pillow numpy

Environment variables (put these in .env or export them)
--------------------------------------------------------
BACKEND_URL   – default http://127.0.0.1:8000
USER_ID       – default "demo"
EMBED_DIM     – default 768  (change only if your embed size differs)
"""

import os
import sys
from typing import List, Optional

import requests
import typer
from dotenv import load_dotenv

# torch / open_clip are optional (only needed for embeddings)
try:
    import torch
    import open_clip
    from PIL import Image
    import numpy as np
except ImportError:
    torch = open_clip = Image = np = None  # graceful fallback for --image-less scans

# ────────────────────────────────
# Config
# ────────────────────────────────
load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_UID = os.getenv("USER_ID", "demo")

EMBED_DIM   = int(os.getenv("EMBED_DIM", "768"))

app = typer.Typer(add_help_option=True, rich_markup_mode="rich")

# ────────────────────────────────
# Helpers
# ────────────────────────────────
def post_json(endpoint: str, payload: dict):
    url = f"{BACKEND_URL}{endpoint}"
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        typer.secho(f"❌  request failed: {exc}", fg="red", err=True)
        sys.exit(1)


def embed_image_or_text(
    *, image_path: Optional[str], text: str
) -> Optional[List[float]]:
    """
    Returns a 768-dim CLIP vector *or* None (when libs are missing and no image).
    - If image_path provided: image embedding.
    - Else: text embedding (if torch/open_clip available).
    """
    if not torch or not open_clip:
        # No embedding capability installed
        return None

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="openai", device=device
    )
    model.eval()

    if image_path:
        img = Image.open(image_path).convert("RGB")
        with torch.no_grad():
            tensor = preprocess(img).unsqueeze(0).to(device)
            vec = model.encode_image(tensor).float().cpu().numpy()[0]
    else:
        with torch.no_grad():
            tokens = open_clip.tokenize([text]).to(device)
            vec = model.encode_text(tokens).float().cpu().numpy()[0]

    vec /= np.linalg.norm(vec)
    return vec.astype("float32").tolist()


# ────────────────────────────────
# Commands
# ────────────────────────────────
@app.command()
def scan(
    name: str = typer.Option(..., "--name", "-n", help="Object name (e.g., 'Quartz Crystal')"),
    family: str = typer.Option(..., "--family", "-f", help="Category / family (e.g., 'Minerals')"),
    image: Optional[str] = typer.Option(
        None, "--image", "-i", help="Path to image file (optional)"
    ),
    user_id: str = typer.Option(
        DEFAULT_UID, "--user", "-u", help="Catalog owner (defaults to USER_ID env var)"
    ),
    thumbnail_url: Optional[str] = typer.Option(
        None, "--thumb", help="Optional URL or data-URI to store as thumbnail"
    ),
):
    """
    Add / deduplicate an object in the backend.
    Works with or **without** an image:

      • With   --image → CLIP image embedding
      • Without          → CLIP text embedding of --name
      • If CLIP libs missing and no image → backend generates placeholder vector
    """
    typer.secho("📡  preparing scan …", fg="cyan")

    fingerprint = embed_image_or_text(image_path=image, text=name)
    if fingerprint is not None and len(fingerprint) != EMBED_DIM:
        typer.secho(
            f"❌  Expected {EMBED_DIM}-dim vector, got {len(fingerprint)}",
            fg="red",
            err=True,
        )
        raise typer.Exit(1)

    payload = {
        "user_id": user_id,
        "name": name,
        "family": family,
        "fingerprint": fingerprint,  # may be null
        "thumbnail_url": thumbnail_url,
    }

    result = post_json("/scan", payload)
    typer.secho(
        f"✅  {result['status'].upper()}  •  object_id: {result['object_id']}",
        fg="green",
    )


@app.command()
def ask(
    object_id: str = typer.Option(..., "--object-id", "-o", help="UUID returned by /scan"),
    question: str = typer.Option(..., "--question", "-q", help="Your question"),
    user_id: str = typer.Option(
        DEFAULT_UID, "--user", "-u", help="Catalog owner (defaults to USER_ID env var)"
    ),
):
    """
    Ask the backend (LLM) a question about a previously scanned object.
    """
    payload = {"user_id": user_id, "object_id": object_id, "question": question}

    typer.secho("🤔  querying LLM …", fg="cyan")
    result = post_json("/ask", payload)

    typer.echo("\n💡  Answer:\n" + result["answer"])


# ────────────────────────────────
# Entry-point
# ────────────────────────────────
if __name__ == "__main__":
    app()
