// The Ask Claude panel: a chat with Claude Code running inside Lexi (see
// chat.py). Loaded after app.js, so it can read the review state there
// (cards, index, mode) to tell Claude which card is on screen.

(() => {
  const $ = (id) => document.getElementById(id);
  const STORE_KEY = "lexi-chat-v1";
  const MAX_SAVED = 60; // messages kept in this browser between visits

  let state = { sessionId: null, messages: [] };
  try {
    const saved = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
    if (saved && Array.isArray(saved.messages)) state = saved;
  } catch (e) {}
  const persist = () => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify({ ...state, messages: state.messages.slice(-MAX_SAVED) }));
    } catch (e) {}
  };

  let busy = false;

  // ---- what's on screen ----------------------------------------------
  function currentCardContext() {
    const writeVisible = !$("write-card").classList.contains("hidden");
    const recognizeVisible = !$("recognize-card").classList.contains("hidden");
    if (!(writeVisible || recognizeVisible) || typeof cards === "undefined" || !cards[index]) return {};
    const revealId = writeVisible ? "write-reveal" : "recognize-reveal";
    return {
      card_id: cards[index].id,
      mode: writeVisible ? "write" : "recognize",
      answer_shown: !$(revealId).classList.contains("hidden"),
    };
  }

  // After Claude edits vocab.json, pull the fresh copy of the card on
  // screen so a fixed clue shows right away.
  async function refreshCurrentCard() {
    const ctx = currentCardContext();
    if (!ctx.card_id) return;
    let fresh;
    try {
      const res = await fetch(`/api/entry/${ctx.card_id}`);
      if (!res.ok) return;
      fresh = await res.json();
    } catch (e) {
      return;
    }
    for (const list of [cards, allDueCards]) {
      for (const c of list || []) if (c.id === fresh.id) Object.assign(c, fresh);
    }
    if (ctx.mode === "write" && !ctx.answer_shown) {
      $("write-prompt").textContent = fresh.translation_en;
      if (fresh.definition_in_prompt && fresh.definition_in_language) {
        $("write-prompt-definition").textContent = fresh.definition_in_language;
      }
      if (fresh.image_in_prompt && fresh.image) {
        const img = $("write-prompt-image");
        img.src = `${fresh.image}?v=${Date.now()}`; // bust the cache if the file was replaced
        img.alt = fresh.translation_en || "";
        img.classList.remove("hidden");
        const credit = $("write-prompt-image-credit");
        credit.textContent = fresh.image_credit || "";
        credit.classList.toggle("hidden", !fresh.image_credit);
      }
    }
  }

  // ---- rendering --------------------------------------------------------
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // Just enough Markdown for chat replies: bold, italics, code, bullets.
  function renderMarkdown(text) {
    const lines = esc(text).split("\n");
    let html = "";
    let inList = false;
    for (const raw of lines) {
      const bullet = raw.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)$/);
      const line = (bullet ? bullet[1] : raw)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>");
      if (bullet) {
        if (!inList) { html += "<ul>"; inList = true; }
        html += `<li>${line}</li>`;
        continue;
      }
      if (inList) { html += "</ul>"; inList = false; }
      html += line.trim() ? `<p>${line}</p>` : "";
    }
    if (inList) html += "</ul>";
    return html;
  }

  // Image search results as numbered thumbnails; clicking one asks Claude
  // to put that image on the card.
  function imageGrid(results) {
    const grid = document.createElement("div");
    grid.className = "chat-images";
    if (!results.length) return grid;
    results.forEach((r, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "chat-image";
      btn.title = `${r.title.replace(/^File:/, "")}\n${r.license}${r.artist ? " · " + r.artist : ""}`;
      const img = document.createElement("img");
      img.src = r.thumb;
      img.alt = r.description || r.title;
      img.loading = "lazy";
      const num = document.createElement("span");
      num.className = "chat-image-num";
      num.textContent = String(i + 1);
      const lic = document.createElement("span");
      lic.className = "chat-image-license";
      lic.textContent = r.license;
      btn.append(img, num, lic);
      btn.addEventListener("click", () => send(`Use image ${i + 1}: ${r.title}`));
      grid.appendChild(btn);
    });
    return grid;
  }

  function messageEl(msg) {
    const div = document.createElement("div");
    div.className = `chat-msg ${msg.role}`;
    if (msg.role === "assistant") {
      div.innerHTML = renderMarkdown(msg.text || "");
      for (const t of msg.tools || []) {
        const tool = document.createElement("p");
        tool.className = "chat-tool";
        tool.textContent = t;
        div.prepend(tool);
      }
      for (const results of msg.images || []) div.appendChild(imageGrid(results));
      if (msg.error) {
        const err = document.createElement("p");
        err.className = "chat-error";
        err.textContent = msg.error;
        div.appendChild(err);
      }
    } else {
      div.textContent = msg.text;
    }
    return div;
  }

  function renderAll() {
    const log = $("chat-log");
    log.replaceChildren();
    if (!state.messages.length) {
      const empty = document.createElement("div");
      empty.className = "chat-empty";
      empty.innerHTML =
        "<p><strong>Ask about a word, or about the card on screen.</strong></p>" +
        "<p>Try “what does начинка mean?”, “add it” or “this clue is leaky”. " +
        "Claude can add and fix cards, and find pictures for them (“add an image to this card”). It won't give away a card's answer before you've seen it.</p>";
      log.appendChild(empty);
      return;
    }
    state.messages.forEach((m) => log.appendChild(messageEl(m)));
    log.scrollTop = log.scrollHeight;
  }

  // ---- sending ----------------------------------------------------------
  async function send(text) {
    if (busy || !text.trim()) return;
    busy = true;
    $("chat-send").disabled = true;
    $("chat-status").textContent = "Claude is thinking…";

    state.messages.push({ role: "user", text });
    const reply = { role: "assistant", text: "", tools: [] };
    state.messages.push(reply);
    renderAll();
    const log = $("chat-log");
    let replyEl = log.lastElementChild;
    const redraw = () => {
      const next = messageEl(reply);
      replyEl.replaceWith(next);
      replyEl = next;
      log.scrollTop = log.scrollHeight;
    };

    let edited = false;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: state.sessionId, ...currentCardContext() }),
      });
      if (!res.ok || !res.body) throw new Error(`The server answered ${res.status}.`);
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          const ev = JSON.parse(line);
          if (ev.type === "text") {
            reply.text += ev.text;
            $("chat-status").textContent = "";
          } else if (ev.type === "tool") {
            reply.tools.push(ev.label);
            $("chat-status").textContent = ev.label + "…";
          } else if (ev.type === "images") {
            (reply.images = reply.images || []).push(ev.results);
          } else if (ev.type === "error") {
            reply.error = ev.message;
          } else if (ev.type === "done") {
            state.sessionId = ev.session_id || state.sessionId;
            edited = ev.edited;
          }
          redraw();
        }
      }
    } catch (e) {
      reply.error = `Couldn't reach Claude. Is Lexi still running? (${e.message})`;
      redraw();
    }
    if (!reply.text && !reply.error) reply.error = "No reply came back. Try again.";
    redraw();
    persist();
    busy = false;
    $("chat-send").disabled = false;
    $("chat-status").textContent = edited ? "Lexi's cards were updated." : "";
    if (edited) refreshCurrentCard();
    $("chat-input").focus();
  }

  // ---- panel wiring -----------------------------------------------------
  function setOpen(open) {
    $("chat-panel").classList.toggle("hidden", !open);
    $("chat-toggle").setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("chat-open", open);
    try { localStorage.setItem("lexi-chat-open", open ? "1" : "0"); } catch (e) {}
    if (open) {
      renderAll();
      $("chat-input").focus();
    }
  }

  $("chat-toggle").addEventListener("click", () => setOpen($("chat-panel").classList.contains("hidden")));
  $("chat-close").addEventListener("click", () => setOpen(false));
  $("chat-new").addEventListener("click", () => {
    if (busy) return;
    state = { sessionId: null, messages: [] };
    persist();
    renderAll();
    $("chat-status").textContent = "Started a new conversation.";
    $("chat-input").focus();
  });
  $("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = $("chat-input");
    const text = input.value;
    input.value = "";
    input.style.height = "";
    send(text);
  });
  $("chat-input").addEventListener("keydown", (e) => {
    // Enter sends; Shift+Enter makes a new line. Keys typed here shouldn't
    // reach the review screen's own shortcuts.
    e.stopPropagation();
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      $("chat-form").requestSubmit();
    }
  });
  $("chat-input").addEventListener("input", (e) => {
    e.target.style.height = "";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  });

  let startOpen = false;
  try { startOpen = localStorage.getItem("lexi-chat-open") === "1"; } catch (e) {}
  setOpen(startOpen);
})();
