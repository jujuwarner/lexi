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

import json
from pathlib import Path
from typing import AsyncIterator, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    ToolUseBlock,
    query,
)

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
only. If she asks for something outside that (code changes, images, git \
commits), say it needs her terminal session with Claude Code instead.

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
}


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
    {"type": "done", "session_id": ..., "edited": bool}
    {"type": "error", "message": ...}
    """
    options = ClaudeAgentOptions(
        cwd=str(LEXI_DIR),
        setting_sources=["project"],  # loads CLAUDE.md; not ~/.claude settings
        system_prompt={"type": "preset", "preset": "claude_code", "append": PANEL_PROMPT},
        allowed_tools=["Read", "Glob", "Grep", "Edit(/vocab.json)", "Bash(python3 *)"],
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
                    if isinstance(block, ToolUseBlock):
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
