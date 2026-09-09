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
import re
import unicodedata
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


VOWEL_START = "aàâeéèêëiîïoôuùûü"


def display_word(entry):
    """For nouns, show the word with its article (e.g. 'la cigogne') so
    gender gets practiced as part of the same recall as the word itself —
    that's how gender actually gets used, not as separate trivia. Non-nouns
    (verbs, adjectives — anything with no 'gender' field) just show the
    bare word.

    Note: this only checks for a leading vowel to decide on "l'" elision.
    French also elides before a silent 'h' (l'homme) but not an aspirate
    'h' (le hibou), and there's no reliable rule-based way to tell those
    apart — it's memorized per word. Not handled here; none of the words
    added so far start with 'h', so it hasn't come up yet."""
    gender = entry.get("gender")
    word = entry["word"]
    if not gender:
        return word
    if word[0].lower() in VOWEL_START:
        return f"l'{word}"
    return f"{'le' if gender == 'm' else 'la'} {word}"


def review_card(entry):
    """'Recognize' mode: show the word, self-rate how well you recalled its
    meaning before revealing. Return the updated entry."""
    print("\n" + "=" * 50)
    print(f"  {display_word(entry)}")
    print("=" * 50)
    input("Press Enter to reveal...")

    print(f"\nEnglish:  {entry['translation_en']}")
    print(f"{entry['language'].upper()} definition:  {entry['definition_in_language']}")
    if entry.get("source_sentence"):
        print(f"\nFrom: \"{entry['source_sentence']}\"")
        if entry.get("source_title"):
            print(f"  — {entry['source_title']}")
    if entry.get("cultural_note"):
        print(f"\n📌 {entry['cultural_note']}")

    quality = ask_quality(["1", "2", "3", "4"])
    entry["srs"] = apply_sm2(entry["srs"], quality)
    return entry


# ---------------------------------------------------------------------------
# "Write" mode — see the English meaning, type the French word
# ---------------------------------------------------------------------------
# A stronger recall test than Recognize mode: production (typing the word
# from memory) rather than recognition (seeing the word and just judging
# whether you knew it). The typed answer is checked against the word's
# canonical display form (article included, for nouns — same gender-
# practice principle as Recognize mode), with some leeway for accent typos
# and missing/wrong articles, since those are judgment calls about whether
# something counts as "remembered," not clean rights or wrongs.

ARTICLE_RE = re.compile(r"^(le|la)\s+|^l['’]")


def _normalize_text(s):
    return " ".join(s.strip().lower().split())


def _strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _strip_article(s):
    return ARTICLE_RE.sub("", s, count=1)


def check_answer(typed, expected):
    """Compare a typed answer against the expected (canonical) form.
    Returns "exact", "close" (right word, but an accent slip and/or a
    missing/wrong article), or "wrong"."""
    norm_typed = _normalize_text(typed)
    norm_expected = _normalize_text(expected)

    if norm_typed == norm_expected:
        return "exact"

    stripped_typed = _strip_accents(_strip_article(norm_typed))
    stripped_expected = _strip_accents(_strip_article(norm_expected))
    if stripped_typed == stripped_expected:
        return "close"

    return "wrong"


QUALITY_LABELS = {"1": "Again", "2": "Hard", "3": "Good", "4": "Easy"}


def ask_quality(allowed_keys, header="How well did you remember it?"):
    """Prompt for a quality rating, restricted to `allowed_keys` (a subset
    of "1"-"4"). Used so, e.g., an exact-match answer can't be rated
    "Again" — you clearly did remember it."""
    menu = "   ".join(f"{k}) {QUALITY_LABELS[k]}" for k in allowed_keys)
    while True:
        answer = input(f"\n{header}\n  {menu}\n> ").strip()
        if answer in allowed_keys:
            return QUALITY_MAP[answer]
        print(f"Please enter one of: {', '.join(allowed_keys)}.")


def review_card_write(entry):
    """'Write' mode: show the English meaning, type the French word, get it
    checked. Return the updated entry."""
    print("\n" + "=" * 50)
    print(f"  {entry['translation_en']}")
    print("=" * 50)

    expected = display_word(entry)
    typed = input("Type the word (with le/la/l' if it's a noun): ").strip()
    result = check_answer(typed, expected)

    if result == "exact":
        print(f"\n✓ Correct! {expected}")
        quality = ask_quality(["2", "3", "4"])  # can't be "Again" — you got it
    elif result == "close":
        print(f'\n~ Close — you wrote "{typed}", correct is "{expected}"')
        quality = ask_quality(["1", "2", "3", "4"])
    else:
        print(f'\n✗ Not quite — the answer is: {expected}')
        quality = 0  # Again — wrong answers reset the streak automatically

    print(f"\n{entry['language'].upper()} definition:  {entry['definition_in_language']}")
    if entry.get("source_sentence"):
        print(f"\nFrom: \"{entry['source_sentence']}\"")
        if entry.get("source_title"):
            print(f"  — {entry['source_title']}")
    if entry.get("cultural_note"):
        print(f"\n📌 {entry['cultural_note']}")

    entry["srs"] = apply_sm2(entry["srs"], quality)
    return entry


def run_review():
    entries = load_vocab()
    cards = due_today(entries)

    if not cards:
        print("Nothing due for review right now. Nice work staying caught up!")
        return

    print(f"{len(cards)} card(s) due today.\n")
    print("How do you want to review today? (Enter for Write, the default)")
    print("  1) Recognize — see the word, recall the meaning yourself")
    print("  2) Write — see the meaning, type the word  [default]")
    mode = input("> ").strip()
    card_fn = review_card if mode == "1" else review_card_write

    reviewed = 0
    for entry in cards:
        entry = card_fn(entry)
        save_vocab(entries)  # save after every card, not just at the end
        reviewed += 1

    print(f"\nDone! Reviewed {reviewed} card(s). See you next time.")


if __name__ == "__main__":
    run_review()
