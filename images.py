"""
images.py — find and add vocab-card images from Wikimedia Commons.

Used by the Ask Claude panel (chat.py) as two narrow tools, so Claude can
add an image without general download or shell access:

- search_commons(query): candidates whose license allows reuse (public
  domain, CC0, CC BY, CC BY-SA), with thumbnails for Julia to choose from.
- add_image(entry_id, file_title, credit): re-checks the license,
  downloads the file, resizes it with sips, saves it under
  web/assets/vocab/, sets the card's image fields and adds a README credit.

Credits show in the Write-mode prompt (image_in_prompt), so add_image
rejects one that names the card's word or its English clue.
"""

import html
import json
import re
import subprocess
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import review

LEXI_DIR = Path(__file__).parent
ASSET_DIR = LEXI_DIR / "web" / "assets" / "vocab"
README = LEXI_DIR / "README.md"
API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "lexi-vocab-tool/1.0"  # generic on purpose: no personal details

# Licenses that allow reuse with attribution at most. Anything NC/ND or
# unlabeled is skipped.
_OK_LICENSE = re.compile(r"^(public domain|pd\b|cc0|cc[ -]by(-sa)?\b)", re.I)
_BAD_LICENSE = re.compile(r"\b(nc|nd)\b", re.I)


def _get(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _plain(s: str) -> str:
    """Strip HTML from Commons metadata fields."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def _license_ok(name: str) -> bool:
    return bool(name) and bool(_OK_LICENSE.search(name)) and not _BAD_LICENSE.search(name)


def _describe(page: dict) -> dict | None:
    info = (page.get("imageinfo") or [{}])[0]
    meta = info.get("extmetadata") or {}
    lic = _plain(meta.get("LicenseShortName", {}).get("value", ""))
    if not _license_ok(lic):
        return None
    return {
        "title": page["title"],
        "thumb": info.get("thumburl") or info.get("url"),
        "url": info.get("url"),
        "page": info.get("descriptionurl"),
        "license": lic,
        "artist": _plain(meta.get("Artist", {}).get("value", ""))[:120],
        "description": _plain(meta.get("ImageDescription", {}).get("value", ""))[:200],
        "date": _plain(meta.get("DateTimeOriginal", {}).get("value", ""))[:40],
        "width": info.get("width"),
        "height": info.get("height"),
    }


def search_commons(query: str, limit: int = 8) -> list[dict]:
    """Bitmap images on Commons matching `query`, reusable licenses only."""
    data = _get({
        "action": "query",
        "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6,
        "gsrlimit": min(limit * 3, 40),  # extra, since some get filtered out
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size",
        "iiurlwidth": 320,
    })
    pages = sorted((data.get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        d = _describe(p)
        if d:
            out.append(d)
        if len(out) >= limit:
            break
    return out


# ---- adding an image ------------------------------------------------------

_RU = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p",
                "r", "s", "t", "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya"]))


def _slug(word: str) -> str:
    w = re.sub(r"^(le|la|les|l['’])\s*", "", word.lower().strip())
    w = "".join(_RU.get(c, c) for c in w)
    w = "".join(c for c in unicodedata.normalize("NFKD", w) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", w).strip("-") or "image"


_CLUE_STOPWORDS = {
    "with", "from", "that", "this", "kind", "used", "type", "sort", "something", "someone", "into", "over",
    "long", "short", "small", "large", "little", "very", "made", "worn", "being", "having", "often",
}


def _leaks(credit: str, entry: dict) -> list[str]:
    """Words from the card's answer or English clue that appear in the credit."""
    c = credit.lower()
    found = []
    forms = [entry["word"]] + list((entry.get("aspect_pair") or {}).values())
    for form in forms:
        for tok in re.findall(r"\w+", form.lower()):
            if len(tok) >= 4 and tok[:5] in c:
                found.append(tok)
    clue = re.sub(r"\(.*?\)|\[.*?\]", "", entry.get("translation_en", "")).lower()
    for tok in re.findall(r"[a-z]+", clue):
        if len(tok) >= 4 and tok not in _CLUE_STOPWORDS \
                and re.search(rf"\b{tok}", c):
            found.append(tok)
    return sorted(set(found))


def _add_readme_credit(entry: dict, info: dict, credit: str) -> None:
    """Append a bullet after the last one in README's "Vocab-card images"
    list (before the closing paragraph)."""
    lines = README.read_text(encoding="utf-8").split("\n")
    try:
        start = next(i for i, l in enumerate(lines) if l.startswith("### Vocab-card images"))
    except StopIteration:
        return
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("#")), len(lines))
    bullets = [i for i in range(start, end) if lines[i].startswith("- **")]
    if not bullets:
        return
    at = bullets[-1] + 1
    while at < end and lines[at].startswith("  "):  # the last bullet's continuation lines
        at += 1
    bullet = (
        f"- **{entry['word']}** (id {entry['id']}) — {credit.rstrip('.')}. "
        f"Source: [{info['title']}]({info['page']}). Added from the Ask Claude panel. "
        f"`image_in_prompt: true`."
    )
    lines.insert(at, bullet)
    README.write_text("\n".join(lines), encoding="utf-8")


def add_image(entry_id: int, file_title: str, credit: str) -> dict:
    """Download a Commons image onto a card. Returns {"ok": ...} with
    details, or {"ok": False, "error": ...} explaining what to fix."""
    entries = review.load_vocab()
    entry = next((e for e in entries if e["id"] == entry_id), None)
    if entry is None:
        return {"ok": False, "error": f"No card with id {entry_id}."}

    leaks = _leaks(credit, entry)
    if leaks:
        return {"ok": False, "error": "The credit shows in the prompt, so it can't contain the answer or the English "
                                      f"clue. Rewrite it without: {', '.join(leaks)}."}

    title = file_title if file_title.startswith("File:") else "File:" + file_title
    data = _get({"action": "query", "titles": title, "prop": "imageinfo",
                 "iiprop": "url|extmetadata|size", "iiurlwidth": 1000})
    page = next(iter((data.get("query") or {}).get("pages", {}).values()), {})
    if "missing" in page or not page.get("imageinfo"):
        return {"ok": False, "error": f"Couldn't find {title} on Wikimedia Commons."}
    info = _describe(page)
    if info is None:
        return {"ok": False, "error": f"{title} isn't public domain or CC BY / CC BY-SA, so it can't be used."}
    if info["license"].lower() not in credit.lower():
        credit = f"{credit.rstrip('. ')}. {info['license']}."

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{_slug(entry['word'])}_{entry['id']}.jpg"
    dest = ASSET_DIR / name
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "download"
        req = urllib.request.Request(info["thumb"] or info["url"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as r:
            raw.write_bytes(r.read())
        result = subprocess.run(
            ["sips", "-s", "format", "jpeg", "-Z", "500", str(raw), "--out", str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0 or not dest.exists():
            return {"ok": False, "error": f"Couldn't convert the image: {result.stderr.strip()[:200]}"}

    replaced = bool(entry.get("image"))
    entry["image"] = f"assets/vocab/{name}"
    entry["image_credit"] = credit
    entry["image_in_prompt"] = True
    review.save_vocab(entries)
    _add_readme_credit(entry, info, credit)
    return {"ok": True, "image": entry["image"], "credit": credit, "license": info["license"],
            "replaced_existing_image": replaced}
