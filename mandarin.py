"""Mandarin character practice.

Each word is a triangle: the characters (hanzi), the sound (pinyin, plus
audio the browser speaks), and the meaning. Every directed edge of that
triangle has its own SM-2 schedule, so "I can read 谢谢" and "I can write
谢谢 from 'thank you'" are tracked separately.

Words live in mandarin.json, separate from vocab.json, because their cards
work differently: six schedules per word instead of one.

Two rules keep a day's practice honest and small:
  * At most one edge per word per day ("sibling burying", as Anki calls
    it). Seeing 谢谢 → "thank you" would give away "thank you" → 谢谢 a few
    cards later.
  * New words are rationed (NEW_WORDS_PER_DAY). A new word starts with its
    easiest edge (characters → meaning); its other edges are introduced
    one a day, on days when none of its edges are due for review.
"""

import json
import unicodedata
from datetime import date
from pathlib import Path

from review import apply_sm2

MANDARIN_FILE = Path(__file__).parent / "mandarin.json"

NEW_WORDS_PER_DAY = 3

# Every edge, in the order a new word's edges are introduced: easiest
# (recognizing) first, hardest (producing characters from sound) last.
EDGES = [
    "hanzi>meaning",
    "sound>meaning",
    "hanzi>pinyin",
    "meaning>pinyin",
    "meaning>hanzi",
    "sound>hanzi",
]

# What each edge asks you to produce. Meaning edges are self-graded (there's
# no single right English wording); pinyin and hanzi answers are typed and
# checked.
EDGE_ANSWER = {
    "hanzi>meaning": "meaning",
    "sound>meaning": "meaning",
    "hanzi>pinyin": "pinyin",
    "meaning>pinyin": "pinyin",
    "meaning>hanzi": "hanzi",
    "sound>hanzi": "hanzi",
}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def load():
    if not MANDARIN_FILE.exists():
        return []
    with open(MANDARIN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save(words):
    with open(MANDARIN_FILE, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)


def _new_srs():
    return {
        "repetitions": 0,
        "easiness": 2.5,
        "interval": 0,
        "next_review": date.today().isoformat(),
        "last_reviewed": None,
        "first_reviewed_on": None,
    }


def find(words, word_id):
    return next((w for w in words if w["id"] == word_id), None)


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def _reviewed(srs):
    return srs is not None and srs.get("last_reviewed") is not None


def _todays_edge(word, today):
    """The one edge this (already introduced) word should show today, or
    None. A due review comes first (most overdue, then easiest); with
    nothing due, the next edge not yet introduced."""
    edges = word.get("edges", {})
    due = [e for e in EDGES if _reviewed(edges.get(e)) and edges[e]["next_review"] <= today]
    if due:
        return min(due, key=lambda e: (edges[e]["next_review"], EDGES.index(e)))
    fresh = [e for e in EDGES if not _reviewed(edges.get(e))]
    return fresh[0] if fresh else None


def prompt_payload(word, edge, is_new=False):
    return {
        "word_id": word["id"],
        "edge": edge,
        "answer": EDGE_ANSWER[edge],
        "hanzi": word["hanzi"],
        "pinyin": word["pinyin"],
        "meaning": word["meaning"],
        "note": word.get("note", ""),
        "is_new": is_new,
    }


def due_prompts(words):
    """Today's prompts: one per introduced word that has something to show,
    then up to today's remaining allowance of brand-new words (oldest id
    first)."""
    today = date.today().isoformat()
    introduced_today = sum(1 for w in words if w.get("introduced_on") == today)

    reviews, new_words = [], []
    for w in sorted(words, key=lambda w: w["id"]):
        edges = w.get("edges", {})
        if any(s.get("last_reviewed") == today for s in edges.values()):
            continue  # this word already had its one edge today
        if not w.get("introduced_on"):
            new_words.append(w)
            continue
        edge = _todays_edge(w, today)
        if edge:
            reviews.append(prompt_payload(w, edge))

    allowance = max(0, NEW_WORDS_PER_DAY - introduced_today)
    new = [prompt_payload(w, EDGES[0], is_new=True) for w in new_words[:allowance]]
    return reviews + new


def record(words, word_id, edge, correct):
    """Apply one first-attempt result to a word's edge and mark the word
    introduced if this was its first prompt. Returns the updated word."""
    word = find(words, word_id)
    if word is None or edge not in EDGES:
        return None
    edges = word.setdefault("edges", {})
    edges[edge] = apply_sm2(edges.get(edge) or _new_srs(), 4 if correct else 0)
    if not word.get("introduced_on"):
        word["introduced_on"] = date.today().isoformat()
    return word


def status(words):
    today = date.today().isoformat()
    due = due_prompts(words)
    reviewed_today = any(
        s.get("last_reviewed") == today for w in words for s in w.get("edges", {}).values()
    )
    waiting = sum(1 for w in words if not w.get("introduced_on")) - sum(1 for p in due if p["is_new"])
    return {
        "words": len(words),
        "due": len(due),
        "done_today": reviewed_today and not due,
        "new_waiting": max(0, waiting),
    }


# ---------------------------------------------------------------------------
# Answer checking
# ---------------------------------------------------------------------------

# Combining marks for the four tones, as they appear after NFD normalization.
_TONE_MARKS = {"̄": 1, "́": 2, "̌": 3, "̀": 4}


def pinyin_key(s):
    """Split pinyin into (letters, tones) so tone marks and tone numbers
    compare equal: "nǐ hǎo", "ni3 hao3" and "Ni3hao3" all give
    ("nihao", [3, 3]). Neutral tones (unmarked, or written 5 or 0) add
    nothing to the tone list. "v" and "u:" are typed stand-ins for ü."""
    s = s.lower().replace("u:", "ü").replace("v", "ü")
    letters, tones = [], []
    for ch in unicodedata.normalize("NFD", s):
        if ch in _TONE_MARKS:
            tones.append(_TONE_MARKS[ch])
        elif ch in "1234":
            tones.append(int(ch))
        elif ch.isalpha() or ch == "̈":  # keep ü's diaeresis
            letters.append(ch)
    return unicodedata.normalize("NFC", "".join(letters)), tones


def check_pinyin(typed, expected):
    """exact, tones (right syllables, wrong or missing tones) or wrong."""
    t_letters, t_tones = pinyin_key(typed)
    e_letters, e_tones = pinyin_key(expected)
    if t_letters != e_letters:
        return "wrong"
    return "exact" if t_tones == e_tones else "tones"


def _strip_hanzi(s):
    return "".join(
        ch for ch in s if not ch.isspace() and not unicodedata.category(ch).startswith("P")
    )


def check_hanzi(typed, expected):
    return "exact" if _strip_hanzi(typed) == _strip_hanzi(expected) else "wrong"


def check(word, edge, typed):
    kind = EDGE_ANSWER.get(edge)
    if kind == "pinyin":
        return check_pinyin(typed, word["pinyin"])
    if kind == "hanzi":
        return check_hanzi(typed, word["hanzi"])
    return None  # meaning edges are self-graded
