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


PRIORITY_INTERVAL_FACTOR = 0.5


def apply_sm2(srs, quality, priority=False):
    """Given a card's current srs state and a 0-5 quality score, return the
    updated srs state (repetitions, easiness, interval, next_review).

    `priority` marks a card you've deliberately chosen to see more often —
    unlike easiness (which the algorithm derives from how you actually
    perform), this is a standing multiplier you set yourself, applied on
    every review for the life of the card, not just a one-time nudge."""
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

    if priority:
        interval = max(1, round(interval * PRIORITY_INTERVAL_FACTOR))

    # Update easiness. This is the standard SM-2 formula — it nudges
    # easiness up for a 5 (very easy), down for a 3 (hard), and never lets
    # it drop below 1.3 (below that, intervals would shrink too aggressively).
    easiness = easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    easiness = max(1.3, easiness)

    today = date.today()

    # Record the calendar date a card was FIRST ever reviewed, once, and
    # never touch it again after that. This is what lets due_today()'s
    # new-card cap hold across multiple sessions in the same day — without
    # it, a card exits "brand new" (last_reviewed stops being None) the
    # moment it's reviewed, which would quietly let the next batch of new
    # cards in on the very next /api/due call, defeating the cap entirely.
    first_reviewed_on = srs.get("first_reviewed_on")
    if srs["last_reviewed"] is None:
        first_reviewed_on = today.isoformat()

    return {
        "repetitions": repetitions,
        "easiness": round(easiness, 2),
        "interval": interval,
        "next_review": (today + timedelta(days=interval)).isoformat(),
        "last_reviewed": today.isoformat(),
        "first_reviewed_on": first_reviewed_on,
    }


# ---------------------------------------------------------------------------
# Review session
# ---------------------------------------------------------------------------

NEW_CARDS_PER_DAY = 10
# Caps how many never-reviewed cards can surface per language per day, so
# a big batch of freshly-added words (e.g. a whole chapter's worth) doesn't
# flood a single session. New cards are let in oldest-id-first, so the
# backlog drains in a steady, predictable order rather than a different
# random subset each day. Tune this constant directly; no UI for it yet.

TOTAL_CARDS_PER_DAY = 40
# Caps the total number of cards (new + in-progress reviews combined)
# shown per language per day -- Anki itself has an equivalent "maximum
# reviews/day" setting, for the same reason: without one, a big in-progress
# backlog can balloon a single session indefinitely, since due reviews
# used to have no cap at all (only new cards did). In-progress reviews are
# prioritized first, most-overdue first -- skipping one doesn't erase the
# need to review it, just defers it, since it'll still be due tomorrow --
# with new cards filling whatever slots remain, still bounded by
# NEW_CARDS_PER_DAY. If a language's true backlog exceeds this cap on a
# given day, the overflow simply rolls forward to the next day rather than
# vanishing or being force-fit into one sitting.

PRIORITY_RETRY_THRESHOLD = 3
# How many times you have to get a word wrong (first attempt + retries,
# cumulative within one session) before it's auto-flagged priority — see
# run_review()'s wrong_counts tracking. This is the replacement for manual
# Hard/Good/Easy self-rating: that scale went mostly unused in practice,
# since you only ever rated a word AFTER getting it right, by which point
# it rarely felt "hard" even when it genuinely was. Behavior (how many
# times you actually missed it) is a more honest signal than in-the-
# moment self-report.


def due_today(entries):
    today = date.today().isoformat()
    due = [e for e in entries if e["srs"]["next_review"] <= today]

    brand_new = [e for e in due if e["srs"]["last_reviewed"] is None]
    in_progress = [e for e in due if e["srs"]["last_reviewed"] is not None]

    # How many new cards has each language already spent today's cap on?
    # Checked against ALL entries, not just `due` — a card introduced this
    # morning may no longer be due again this afternoon (a miss pushes
    # next_review to tomorrow), but it still used up a cap slot for today.
    already_introduced_today = {}
    for e in entries:
        if e["srs"].get("first_reviewed_on") == today:
            lang = e["language"]
            already_introduced_today[lang] = already_introduced_today.get(lang, 0) + 1

    # How many cards (new or in-progress) has each language already had
    # REVIEWED today, across every earlier call to due_today() today --
    # not just what's still due right now. Without this, once a reviewed
    # card's next_review moves past today, it drops out of `due`, quietly
    # making room for more of the backlog to slip in under the same cap on
    # the very next /api/due call -- which would let a single day's cap be
    # re-spent over and over as the backlog shrinks, instead of actually
    # deferring the overflow to tomorrow the way the cap is meant to.
    reviewed_today = {}
    for e in entries:
        if e["srs"].get("last_reviewed") == today:
            lang = e["language"]
            reviewed_today[lang] = reviewed_today.get(lang, 0) + 1

    allowed = []
    for lang in sorted(set(e["language"] for e in due)):
        remaining_total = max(0, TOTAL_CARDS_PER_DAY - reviewed_today.get(lang, 0))

        # In-progress reviews get priority, most-overdue first, up to
        # whatever's left of today's total cap.
        lang_in_progress = sorted(
            (e for e in in_progress if e["language"] == lang),
            key=lambda e: e["srs"]["next_review"],
        )
        shown_in_progress = lang_in_progress[:remaining_total]
        allowed.extend(shown_in_progress)

        # New cards fill whatever's left, bounded by both the remaining
        # total-cap slots and the existing new-card-per-day cap.
        remaining_total -= len(shown_in_progress)
        remaining_new_cap = max(0, NEW_CARDS_PER_DAY - already_introduced_today.get(lang, 0))
        remaining_new = min(remaining_total, remaining_new_cap)

        lang_new = sorted(
            (e for e in brand_new if e["language"] == lang), key=lambda e: e["id"]
        )
        allowed.extend(lang_new[:remaining_new])

    return allowed


def backlog_cards(entries, language, limit=None):
    """`language`'s entire backlog beyond today's normal caps, by default
    in one go -- for when you deliberately choose to keep going rather
    than stop for the day. There's no re-gating once you've opted in,
    for either cap: not TOTAL_CARDS_PER_DAY, and not NEW_CARDS_PER_DAY
    either -- both exist to keep an ordinary day from ballooning by
    default, not to second-guess a deliberate choice to do more. Closing
    the tab or clicking "Back to start" is always a safe way to stop
    partway through, since every review saves immediately, so there was
    never a real need to force any of this into gated chunks. Pass an
    explicit `limit` if a caller specifically wants a capped chunk
    instead of the whole thing.

    Same priority order as due_today() -- most-overdue in-progress
    first, then new cards oldest-id-first."""
    today = date.today().isoformat()
    due = [
        e for e in entries
        if e["language"] == language and e["srs"]["next_review"] <= today
    ]
    brand_new = [e for e in due if e["srs"]["last_reviewed"] is None]
    in_progress = [e for e in due if e["srs"]["last_reviewed"] is not None]

    lang_in_progress = sorted(in_progress, key=lambda e: e["srs"]["next_review"])
    lang_new = sorted(brand_new, key=lambda e: e["id"])

    combined = lang_in_progress + lang_new
    return combined if limit is None else combined[:limit]


def backlog_by_language(entries):
    """How many days of cap-limited reviewing it'd take to clear each
    language's current backlog, for languages where that's genuinely
    more than a single day's work -- i.e. due_today()'s cap would defer
    some of it past today even if you reviewed every card it offers.
    Deliberately omits languages whose whole due pile fits in one day's
    cap, since there's nothing multi-day to flag there."""
    today = date.today().isoformat()
    due_counts = {}
    for e in entries:
        if e["srs"]["next_review"] <= today:
            lang = e["language"]
            due_counts[lang] = due_counts.get(lang, 0) + 1

    backlog = {}
    for lang, due_count in due_counts.items():
        days = -(-due_count // TOTAL_CARDS_PER_DAY)  # ceiling division
        if days > 1:
            backlog[lang] = {"due": due_count, "days": days}
    return backlog


def completed_languages_today(entries):
    """Which languages have genuinely nothing more to show right now, but
    only count as "done" (as opposed to just having an empty deck) if some
    review actually happened today -- covers both a fully drained backlog
    and a backlog that's hit today's cap and rolled the rest to tomorrow.
    Used by the UI to tell those two "zero cards right now" cases apart."""
    today = date.today().isoformat()
    reviewed_today = {}
    for e in entries:
        if e["srs"].get("last_reviewed") == today:
            lang = e["language"]
            reviewed_today[lang] = reviewed_today.get(lang, 0) + 1

    still_due_langs = {c["language"] for c in due_today(entries)}
    return sorted(lang for lang in reviewed_today if lang not in still_due_langs)


# ---------------------------------------------------------------------------
# Era tagging
# ---------------------------------------------------------------------------
# An entry's optional "era" field is a visual signal during review, not a
# scheduling input — it never touches SM-2. Controlled vocabulary (rather
# than a free-text tag) so the color-coding stays consistent: add a new key
# here whenever vocab grows into a period this set doesn't cover yet, rather
# than letting callers invent new era strings ad hoc.

ERAS = {
    "serfdom_era": {"label": "Serfdom era", "color": "#8b5a2b"},
    "archaic": {"label": "Archaic / dated", "color": "#8a8578"},
}


def era_badge(entry):
    """The {key, label, color} to render for this entry's era, or None if
    it isn't tagged (most entries won't be — this is for words that are
    genuinely tied to a specific bygone period, not everyday vocabulary)."""
    key = entry.get("era")
    if key not in ERAS:
        return None
    return {"key": key, **ERAS[key]}


VOWEL_START = "aàâeéèêëiîïoôuùûü"


def display_word(entry):
    """For French nouns, show the word with its article (e.g. 'la cigogne')
    so gender gets practiced as part of the same recall as the word itself —
    that's how gender actually gets used, not as separate trivia. Non-nouns
    (verbs, adjectives — anything with no 'gender' field) just show the
    bare word, and so does every non-French language: Russian has grammatical
    gender too but no articles, so there's nothing to prepend regardless of
    what 'gender' says. This function is the only place that ever attaches
    an article, so gating it here is enough — nowhere else needs to know
    which language it's looking at.

    Note: the article logic only checks for a leading vowel to decide on
    "l'" elision. French also elides before a silent 'h' (l'homme) but not
    an aspirate 'h' (le hibou), and there's no reliable rule-based way to
    tell those apart — it's memorized per word. Not handled here; none of
    the French words added so far start with 'h', so it hasn't come up yet."""
    gender = entry.get("gender")
    word = entry["word"]
    if not gender or entry.get("language") != "fr":
        return word
    if word[0].lower() in VOWEL_START:
        return f"l'{word}"
    return f"{'le' if gender == 'm' else 'la'} {word}"


def review_card(entry):
    """'Recognize' mode, first attempt for this due-appearance: show the
    word, self-report whether you knew it, update SM-2 automatically from
    that. Returns (entry, missed) — `missed` tells the caller (run_review)
    whether this needs to go into the session's retry queue.

    No 1-4 self-rating anymore — in practice that scale barely got used
    (you only ever rated a word AFTER getting it right, by which point it
    rarely felt "hard" even if it genuinely was). Difficulty is now judged
    by behavior instead: see PRIORITY_RETRY_THRESHOLD in run_review()."""
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
        print(f"\n🌿 {entry['cultural_note']}")

    while True:
        answer = input("\nDid you know it? (y/n)\n> ").strip().lower()
        if answer in ("y", "n"):
            break
        print("Please enter y or n.")

    quality = 5 if answer == "y" else 0  # Easy (clean recall) or Again
    entry["srs"] = apply_sm2(entry["srs"], quality, priority="priority" in entry.get("tags", []))
    return entry, quality == 0


def review_card_retry(entry):
    """'Recognize' mode retry drill — shown again because a previous
    attempt this session was missed. Same word, but self-rated as a simple
    got-it-or-not instead of the full 1-4 scale, and no further SM-2
    update — the real spaced-repetition outcome was already locked in on
    the genuine first attempt. Returns True if correct this time (drop
    from the retry queue), False if it should come back around again."""
    print("\n" + "=" * 50)
    print(f"  {display_word(entry)}  (retry)")
    print("=" * 50)
    input("Press Enter to reveal...")
    print(f"\nEnglish:  {entry['translation_en']}")

    while True:
        answer = input("\nGot it this time? (y/n)\n> ").strip().lower()
        if answer in ("y", "n"):
            return answer == "y"
        print("Please enter y or n.")


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


def review_card_write(entry):
    """'Write' mode, first attempt for this due-appearance: show the
    English meaning, type the word, get it checked, update SM-2
    automatically from the result. Returns (entry, missed) — see
    review_card for what that's for.

    No self-rating here either (see review_card's docstring) — an exact
    match is automatically Easy, a close match (accent/article slip) is
    automatically Good, and anything else is Again."""
    print("\n" + "=" * 50)
    print(f"  {entry['translation_en']}")
    print("=" * 50)

    expected = display_word(entry)
    typed = input("Type the word (with le/la/l' if it's a noun, or just press Enter if you don't know it): ").strip()
    result = check_answer(typed, expected)

    if result == "exact":
        print(f"\n✓ Correct! {expected}")
        quality = 5  # Easy -- a clean, unaided recall
    elif result == "close":
        print(f'\n~ Close — you wrote "{typed}", correct is "{expected}"')
        quality = 4  # Good -- right, but a minor typo/accent/article slip
    elif typed == "":
        print(f"\nNo worries — the answer is: {expected}")
        quality = 0  # Again — same as a wrong guess, just a gentler message
    else:
        print(f'\n✗ Not quite — the answer is: {expected}')
        quality = 0  # Again — wrong answers reset the streak automatically

    print(f"\n{entry['language'].upper()} definition:  {entry['definition_in_language']}")
    if entry.get("source_sentence"):
        print(f"\nFrom: \"{entry['source_sentence']}\"")
        if entry.get("source_title"):
            print(f"  — {entry['source_title']}")
    if entry.get("cultural_note"):
        print(f"\n🌿 {entry['cultural_note']}")

    entry["srs"] = apply_sm2(entry["srs"], quality, priority="priority" in entry.get("tags", []))
    return entry, quality == 0


def review_card_write_retry(entry):
    """'Write' mode retry drill — shown again because a previous attempt
    this session was missed. Same prompt, but no quality rating and no
    further SM-2 update — just genuine repeated practice, Quizlet-style,
    until it's answered correctly. Returns True if correct this time
    (drop from the retry queue), False if it should come back around
    again."""
    print("\n" + "=" * 50)
    print(f"  {entry['translation_en']}  (retry)")
    print("=" * 50)

    expected = display_word(entry)
    typed = input("Type the word again: ").strip()
    result = check_answer(typed, expected)

    if result in ("exact", "close"):
        print(f"\n✓ Got it! {expected}")
        return True
    elif typed == "":
        print(f"\nThe answer is: {expected}")
    else:
        print(f'\n✗ Not quite — the answer is: {expected}')
    return False


LANGUAGE_NAMES = {"fr": "French", "ru": "Russian", "zh": "Mandarin"}


def run_review():
    entries = load_vocab()
    cards = due_today(entries)

    if not cards:
        print("Nothing recommended right now. Nice work staying caught up!")
        return

    # Only ask which language when there's actually a choice to make — one
    # language due today (the common case so far) skips straight past this.
    languages = sorted(set(e["language"] for e in cards))
    if len(languages) > 1:
        print(f"{len(cards)} word(s) recommended for today, across {len(languages)} languages.\n")
        print("Which language do you want to review?")
        for i, lang in enumerate(languages, start=1):
            name = LANGUAGE_NAMES.get(lang, lang)
            count = sum(1 for e in cards if e["language"] == lang)
            print(f"  {i}) {name} ({count})")
        choice = input("> ").strip()
        try:
            chosen = languages[int(choice) - 1]
        except (ValueError, IndexError):
            chosen = languages[0]
        cards = [e for e in cards if e["language"] == chosen]

    print(f"\n{len(cards)} word(s) recommended for today.\n")
    print("How do you want to review today? (Enter for Write, the default)")
    print("  1) Recognize — see the word, recall the meaning yourself")
    print("  2) Write — see the meaning, type the word  [default]")
    mode = input("> ").strip()
    first_fn = review_card if mode == "1" else review_card_write
    retry_fn = review_card_retry if mode == "1" else review_card_write_retry

    # Queue of (entry, is_retry). A missed FIRST attempt gets its retry
    # inserted immediately next — so you retype it once right away while
    # the correct answer is still fresh, without re-touching its already-
    # locked-in SM-2 outcome. A missed RETRY (you saw it again and still
    # got it wrong) falls back to the end of the queue instead — a
    # breather on other words before it comes back around again, rather
    # than being stuck retyping the same word forever. `reviewed` only
    # counts genuine first attempts.
    #
    # `wrong_counts` tracks, per word id, how many times it's been missed
    # so far this session (first attempt + any failed retries). This is
    # the new difficulty signal, replacing manual self-rating: a word you
    # only flub once or twice before recovering is just normal; one that
    # takes real, repeated struggle gets auto-flagged priority once it's
    # finally answered correctly, so it naturally surfaces more often in
    # future sessions.
    queue = [(e, False) for e in cards]
    reviewed = 0
    wrong_counts = {}
    i = 0
    while i < len(queue):
        entry, is_retry = queue[i]
        i += 1
        if not is_retry:
            entry, missed = first_fn(entry)
            save_vocab(entries)  # save after every card, not just at the end
            reviewed += 1
            if missed:
                wrong_counts[entry["id"]] = 1
                queue.insert(i, (entry, True))
        else:
            got_it = retry_fn(entry)
            if not got_it:
                wrong_counts[entry["id"]] = wrong_counts.get(entry["id"], 1) + 1
                queue.append((entry, True))
            else:
                total_wrong = wrong_counts.pop(entry["id"], 0)
                if total_wrong >= PRIORITY_RETRY_THRESHOLD and "priority" not in entry.get("tags", []):
                    entry.setdefault("tags", []).append("priority")
                    save_vocab(entries)
                    print("  ⭐ That one took real effort — marked as priority.")

    print(f"\nDone! Reviewed {reviewed} card(s). See you next time.")


if __name__ == "__main__":
    run_review()
