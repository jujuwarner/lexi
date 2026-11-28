"""
chat.py — the "Ask Claude" panel's backend.

Runs Claude Code inside Lexi through the Claude Agent SDK, so Julia can
add words, fix leaky clues and ask about grammar without leaving a review
session. Each message is one SDK `query()`; passing the previous
`session_id` back as `resume` keeps the conversation going across messages
(and across page reloads, since the frontend remembers the id).

Scope is deliberately narrow. Claude can read the project, run python3
(for the duplicate and leak checks and for adding entries) and edit
vocab.json; every other tool call that would need approval is denied
("dontAsk" mode), since there's no one at a terminal to approve it. The
vocab workflow rules live in CLAUDE.md, which the SDK loads automatically
because the session's working directory is this folder.

Auth: the SDK drives the locally installed Claude Code, so it uses
whatever that's logged in with (or ANTHROPIC_API_KEY, if set).
"""

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

import images
import review

LEXI_DIR = Path(__file__).parent

PANEL_PROMPT = """\
You're talking with Julia through the chat panel built into Lexi, her \
vocabulary review app, usually in the middle of a review session or while \
she's reading a book in French or Russian. The panel is narrow, so keep \
replies short and conversational: a few sentences or a short list, no big \
headings, no tables.

Follow the vocab workflow in CLAUDE.md exactly when adding or editing \
cards: duplicate check, leak check, propose first and add only after she \
says yes (yes / да / oui / "add it" all count). You can edit vocab.json \
and, for Mandarin words, mandarin.json (see the Mandarin section of \
CLAUDE.md), nothing else. If she asks for something outside that (code changes, git commits), \
say it needs her terminal session with Claude Code instead.

Images: when she asks for a picture on a card, call search_commons with a \
good English (or Latin species) query. The panel shows her the candidates \
as numbered thumbnails, in the order returned, so just say in a sentence \
which ones look best to you and why, and let her pick. Don't describe \
every candidate. When she picks one ("use 2", or by clicking), call \
add_vocab_image with its exact file title and a credit written in the \
style of CLAUDE.md: describe what's shown without naming the word or its \
English meaning ("a man wearing this kind of coat"), plus artist or \
photographer, date if known, "via Wikimedia Commons" and the license. If \
nothing fits, try another query or say so.

Each message may start with a [Lexi context] block describing the card on \
her screen. If it says the answer isn't revealed yet, never write the \
card's word, its aspect forms or anything that gives them away: she may \
still be trying to recall it. Refer to it as "this card" instead."""

TOOL_LABELS = {
    "Read": "Reading",
    "Grep": "Searching",
    "Glob": "Looking through files",
    "Edit": "Editing",
    "Write": "Writing",
    "Bash": "Running",
    "mcp__lexi__search_commons": "Searching Wikimedia Commons",
    "mcp__lexi__add_vocab_image": "Adding the image",
}


def _image_tools(found: list):
    """The two image tools, built per request so search results can be
    handed to the panel (through `found`) as clickable thumbnails."""

    @tool(
        "search_commons",
        "Search Wikimedia Commons for images to put on a vocab card. Returns only images "
        "whose license allows reuse (public domain, CC0, CC BY, CC BY-SA). Julia sees the "
        "results as numbered thumbnails in the panel, in this order.",
        {"query": str},
    )
    async def search_commons(args):
        try:
            results = await asyncio.to_thread(images.search_commons, args["query"], 8)
        except Exception as exc:
            return {"content": [{"type": "text", "text": f"Search failed: {exc}"}], "is_error": True}
        found.append(results)
        if not results:
            return {"content": [{"type": "text", "text": "No reusable images found. Try another query."}]}
        lines = [
            f"{i}. {r['title']} | {r['license']} | artist: {r['artist'] or 'unknown'} | "
            f"{r['width']}x{r['height']} | {r['description']}"
            for i, r in enumerate(results, 1)
        ]
        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    @tool(
        "add_vocab_image",
        "Put a Wikimedia Commons image on a vocab card: re-checks the license, downloads and "
        "resizes it, sets image / image_credit / image_in_prompt on the card, and adds a README "
        "credit. The credit shows in the prompt, so it must not name the word or its English "
        "clue; the tool rejects one that does.",
        {"entry_id": int, "file_title": str, "credit": str},
    )
    async def add_vocab_image(args):
        try:
            result = await asyncio.to_thread(
                images.add_image, int(args["entry_id"]), args["file_title"], args["credit"]
            )
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "is_error": not result.get("ok")}

    return create_sdk_mcp_server(name="lexi", tools=[search_commons, add_vocab_image])


def _card_context(card_id: Optional[int], mode: Optional[str], answer_shown: bool) -> str:
    """A short description of the card on screen, read fresh from
    vocab.json so it reflects any edit made earlier in the chat."""
    if card_id is None:
        return ""
    entry = next((e for e in review.load_vocab() if e["id"] == card_id), None)
    if entry is None:
        return ""
    lang = {"fr": "French", "ru": "Russian", "zh": "Mandarin"}.get(entry["language"], entry["language"])
    lines = [
        "[Lexi context]",
        f"Card on screen: id {entry['id']} ({lang}), {mode or 'review'} mode.",
        f"Answer revealed: {'yes' if answer_shown else 'NO, do not reveal the word'}.",
        f"Word: {review.display_word(entry)}",
        f"English clue: {entry.get('translation_en', '')}",
        f"Definition: {entry.get('definition_in_language', '')}",
    ]
    if entry.get("cultural_note"):
        lines.append(f"Note: {entry['cultural_note']}")
    lines.append("[/Lexi context]")
    return "\n".join(lines) + "\n\n"


def _tool_summary(block: ToolUseBlock) -> str:
    inp = block.input or {}
    label = TOOL_LABELS.get(block.name, block.name)
    if block.name == "Bash":
        detail = inp.get("description") or "a command"
        return f"{label}: {detail}"
    path = inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
    if path:
        return f"{label} {Path(str(path)).name}"
    return label


def _event(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False) + "\n"


async def stream_chat(
    message: str,
    session_id: Optional[str] = None,
    card_id: Optional[int] = None,
    mode: Optional[str] = None,
    answer_shown: bool = False,
) -> AsyncIterator[str]:
    """Yields newline-delimited JSON events for the frontend:
    {"type": "text", "text": ...}   a chunk of Claude's reply
    {"type": "tool", "label": ...}  Claude is using a tool
    {"type": "images", "results": [...]}  image search results to pick from
    {"type": "done", "session_id": ..., "edited": bool}
    {"type": "error", "message": ...}
    """
    found: list = []  # image search results, forwarded to the panel
    options = ClaudeAgentOptions(
        cwd=str(LEXI_DIR),
        setting_sources=["project"],  # loads CLAUDE.md; not ~/.claude settings
        system_prompt={"type": "preset", "preset": "claude_code", "append": PANEL_PROMPT},
        mcp_servers={"lexi": _image_tools(found)},
        allowed_tools=[
            "Read", "Glob", "Grep", "Edit(/vocab.json)", "Edit(/mandarin.json)", "Bash(python3 *)",
            "mcp__lexi__search_commons", "mcp__lexi__add_vocab_image",
        ],
        disallowed_tools=["WebSearch", "WebFetch", "Agent", "Task"],
        permission_mode="dontAsk",
        include_partial_messages=True,
        resume=session_id or None,
    )
    prompt = _card_context(card_id, mode, answer_shown) + message

    vocab_path = LEXI_DIR / "vocab.json"
    mtime_before = vocab_path.stat().st_mtime
    wrote_text = False
    try:
        async for msg in query(prompt=prompt, options=options):
            while found:
                yield _event(type="images", results=found.pop(0))
            if isinstance(msg, StreamEvent):
                ev = msg.event
                if ev.get("type") == "content_block_start" and ev.get("content_block", {}).get("type") == "text":
                    if wrote_text:
                        yield _event(type="text", text="\n\n")
                elif ev.get("type") == "content_block_delta":
                    delta = ev.get("delta", {})
                    if delta.get("type") == "text_delta" and delta.get("text"):
                        wrote_text = True
                        yield _event(type="text", text=delta["text"])
            elif isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, ToolUseBlock) and block.name != "ToolSearch":
                        yield _event(type="tool", label=_tool_summary(block))
            elif isinstance(msg, ResultMessage):
                if msg.is_error:
                    detail = msg.result or msg.subtype
                    yield _event(type="error", message=f"Claude stopped early ({detail}).")
                # Compare timestamps rather than guessing from tool calls:
                # a python3 script may only read the file.
                edited = vocab_path.stat().st_mtime != mtime_before
                yield _event(type="done", session_id=msg.session_id, edited=edited)
    except Exception as exc:  # surface any SDK/CLI failure in the panel
        yield _event(type="error", message=f"Couldn't reach Claude: {exc}")
