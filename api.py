"""
api.py — Lexi's web UI backend.

A thin FastAPI wrapper around review.py's existing SM-2 and data-loading
logic — no algorithm code is duplicated here, only reused. That's
deliberate: it keeps a future mobile version (a PWA installed on a phone)
cheap to add later, since it would talk to this same API rather than
needing its own copy of the review logic.

Run with:
    python3 run_ui.py
"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import review

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="Lexi")

# This never leaves your machine (runs on localhost only), so a wide-open
# CORS policy costs nothing in safety here — it just avoids browser
# same-origin friction between the page and the API during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache(request, call_next):
    """Tell the browser never to cache anything from this app, including
    the static frontend files (app.js, index.html, style.css). Without
    this, a plain refresh after a UI update can keep serving a stale
    cached copy of app.js even once the server's running the new code --
    only a hard refresh forces a re-fetch. There's no perf cost worth
    worrying about here (one user, localhost, tiny files)."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


class CheckRequest(BaseModel):
    id: int
    typed: str


class ReviewRequest(BaseModel):
    id: int
    quality: str  # one of "1"-"4", same keys as review.QUALITY_MAP


class TogglePriorityRequest(BaseModel):
    id: int


def _find_entry(entries, entry_id):
    for e in entries:
        if e["id"] == entry_id:
            return e
    return None


def _entry_payload(e):
    """The fields either review mode needs, minus internal srs bookkeeping."""
    return {
        "id": e["id"],
        "word": e["word"],
        "display_word": review.display_word(e),
        "translation_en": e["translation_en"],
        "definition_in_language": e["definition_in_language"],
        "language": e["language"],
        "source_sentence": e.get("source_sentence", ""),
        "source_title": e.get("source_title", ""),
        "cultural_note": e.get("cultural_note", ""),
        "priority": "priority" in e.get("tags", []),
        "era": review.era_badge(e),
    }


@app.get("/api/due")
def get_due():
    """Everything due today, in the same order review.py would show it."""
    entries = review.load_vocab()
    cards = review.due_today(entries)
    return [_entry_payload(e) for e in cards]


@app.get("/api/backlog")
def get_backlog(language: str, limit: Optional[int] = None):
    """The entire remaining backlog for a language, beyond today's normal
    cap -- powers the "keep going" / "continue backlog" options. Returns
    everything in one go by default (there's no need to re-gate it once
    you've deliberately opted in; stopping partway is always safe, since
    every review saves immediately) -- pass `limit` for a capped chunk
    instead."""
    entries = review.load_vocab()
    cards = review.backlog_cards(entries, language, limit)
    return [_entry_payload(e) for e in cards]


@app.get("/api/status")
def get_status():
    """Languages with nothing left to show right now AND some review
    actually happened today for them -- lets the UI say "done for today"
    instead of just silently making the language disappear. Also reports
    any language whose backlog is big enough to take more than one day
    to clear at the daily cap, so a large backlog is visible rather than
    just quietly deferring a bit more each day forever."""
    entries = review.load_vocab()
    return {
        "completed_languages": review.completed_languages_today(entries),
        "backlog": review.backlog_by_language(entries),
    }


@app.post("/api/check")
def check(req: CheckRequest):
    """Write mode: check a typed answer. Doesn't touch the SRS state yet —
    that only happens once a quality rating comes in via /api/review."""
    entries = review.load_vocab()
    entry = _find_entry(entries, req.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found")

    expected = review.display_word(entry)
    result = review.check_answer(req.typed, expected)

    if result == "exact":
        allowed = ["2", "3", "4"]  # can't be "Again" — you got it right
    elif result == "close":
        allowed = ["1", "2", "3", "4"]
    else:
        allowed = []  # wrong answers auto-rate as "Again"

    return {
        "result": result,
        "expected": expected,
        "allowed_qualities": allowed,
        "definition_in_language": entry["definition_in_language"],
        "source_sentence": entry.get("source_sentence", ""),
        "source_title": entry.get("source_title", ""),
        "cultural_note": entry.get("cultural_note", ""),
    }


@app.post("/api/review")
def submit_review(req: ReviewRequest):
    """Apply an SM-2 update for the given quality rating and save — the
    same effect as review.py saving after every card."""
    if req.quality not in review.QUALITY_MAP:
        raise HTTPException(status_code=400, detail="quality must be '1'-'4'")

    entries = review.load_vocab()
    entry = _find_entry(entries, req.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found")

    quality_score = review.QUALITY_MAP[req.quality]
    priority = "priority" in entry.get("tags", [])
    entry["srs"] = review.apply_sm2(entry["srs"], quality_score, priority=priority)
    review.save_vocab(entries)
    return {"ok": True, "next_review": entry["srs"]["next_review"]}


@app.post("/api/toggle_priority")
def toggle_priority(req: TogglePriorityRequest):
    """Flip whether a card is marked priority (reviewed more often, on
    every future review, not just once)."""
    entries = review.load_vocab()
    entry = _find_entry(entries, req.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Word not found")

    tags = entry.setdefault("tags", [])
    if "priority" in tags:
        tags.remove("priority")
        now_priority = False
    else:
        tags.append("priority")
        now_priority = True

    review.save_vocab(entries)
    return {"ok": True, "priority": now_priority}


# Serve the frontend last, so it doesn't shadow the /api/* routes above.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
