"""
review.py — Lexi's flashcard review engine.

Implements SM-2, the spaced-repetition algorithm behind Anki (and originally
SuperMemo). The core idea: every time you review a card, we decide how many
days to wait before showing it again, based on how well you remembered it.
Remember it easily? Wait longer next time. Forget it? Reset and see it again
soon. Over many reviews, this converges on showing you each word right around
the moment you're about to forget it — which is where spaced repetition gets
its power.

Run with:
    python3 review.py
"""

import json
from datetime import date, timedelta
from pathlib import Path

VOCAB_FILE = Path(__file__).parent / "vocab.json"


# ---------------------------------------------------------------------------
# Data loading / saving
# ---------------------------------------------------------------------------

def load_vocab():
    with open(VOCAB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_vocab(entries):
    with open(VOCAB_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# SM-2 algorithm
# ---------------------------------------------------------------------------
# Each card tracks three numbers under "srs":
#   repetitions — how many times in a row you've remembered it successfully
#   easiness    — a multiplier (starts at 2.5) that grows if a word is easy
#                 for you and shrinks if it's hard; never drops below 1.3
#   interval    — how many days until the next review
#
# "quality" is a 0-5 score for how well you recalled the card this time.
# We map a simple 4-option prompt (Again/Hard/Good/Easy) onto that scale
# rather than asking you to pick a number, since that's both faster to use
# and matches how most modern SRS apps (Anki included) present it.

QUALITY_MAP = {
    "1": 0,  # Again — didn't remember it at all, start over
    "2": 3,  # Hard — remembered, but it was a struggle
    "3": 4,  # Good — remembered with some effort
    "4": 5,  # Easy — remembered instantly
}


def apply_sm2(srs, quality):
    """Given a card's current srs state and a 0-5 quality score, return the
    updated srs state (repetitions, easiness, interval, next_review)."""
    repetitions = srs["repetitions"]
    easiness = srs["easiness"]

    if quality < 3:
        # Forgot it — reset the streak and see it again tomorrow.
        repetitions = 0
        interval = 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(srs["interval"] * easiness)
        repetitions += 1

    # Update easiness. This is the standard SM-2 formula — it nudges
    # easiness up for a 5 (very easy), down for a 3 (hard), and never lets
    # it drop below 1.3 (below that, intervals would shrink too aggressively).
    easiness = easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    easiness = max(1.3, easiness)

    today = date.today()
    return {
        "repetitions": repetitions,
        "easiness": round(easiness, 2),
        "interval": interval,
        "next_review": (today + timedelta(days=interval)).isoformat(),
        "last_reviewed": today.isoformat(),
    }


# ---------------------------------------------------------------------------
# Review session
# ---------------------------------------------------------------------------

def due_today(entries):
    today = date.today().isoformat()
    return [e for e in entries if e["srs"]["next_review"] <= today]


def review_card(entry):
    """Show one card, take a rating, and return the updated entry."""
    print("\n" + "=" * 50)
    print(f"  {entry['word']}")
    print("=" * 50)
    input("Press Enter to reveal...")

    print(f"\nEnglish:  {entry['translation_en']}")
    print(f"{entry['language'].upper()} definition:  {entry['definition_in_language']}")
    if entry.get("source_sentence"):
        print(f"\nFrom: \"{entry['source_sentence']}\"")
        if entry.get("source_title"):
            print(f"  — {entry['source_title']}")

    while True:
        answer = input(
            "\nHow well did you remember it?\n"
            "  1) Again   2) Hard   3) Good   4) Easy\n> "
        ).strip()
        if answer in QUALITY_MAP:
            break
        print("Please enter 1, 2, 3, or 4.")

    quality = QUALITY_MAP[answer]
    entry["srs"] = apply_sm2(entry["srs"], quality)
    return entry


def run_review():
    entries = load_vocab()
    cards = due_today(entries)

    if not cards:
        print("Nothing due for review right now. Nice work staying caught up!")
        return

    print(f"{len(cards)} card(s) due today.\n")

    reviewed = 0
    for entry in cards:
        entry = review_card(entry)
        save_vocab(entries)  # save after every card, not just at the end
        reviewed += 1

    print(f"\nDone! Reviewed {reviewed} card(s). See you next time.")


if __name__ == "__main__":
    run_review()
