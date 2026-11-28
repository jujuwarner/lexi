// Mandarin character practice (see mandarin.py). Each prompt is one edge of
// a word's triangle: characters, sound and meaning. Loaded after app.js and
// uses its helpers (el, api, showSection). app.js opens it through
// window.lexiZh from the Mandarin page's Characters tile.

(() => {
  const $ = (id) => document.getElementById(id);

  // What each edge shows, what it asks for, and the label above the prompt.
  const EDGES = {
    "hanzi>meaning": { show: "hanzi", ask: "What does it mean?" },
    "sound>meaning": { show: "sound", ask: "What does it mean?" },
    "hanzi>pinyin": { show: "hanzi", ask: "Type the pinyin" },
    "meaning>pinyin": { show: "meaning", ask: "Type the pinyin" },
    "meaning>hanzi": { show: "meaning", ask: "Type the characters" },
    "sound>hanzi": { show: "sound", ask: "Type the characters" },
  };
  const PLACEHOLDERS = {
    pinyin: "nǐ hǎo or ni3 hao3…",
    hanzi: "Use the Pinyin keyboard to type characters…",
  };

  let queue = [];
  let i = 0;
  let total = 0;
  let done = new Set(); // "word_id|edge" once answered correctly
  let reviewed = 0;
  let busy = false;

  const keyOf = (p) => `${p.word_id}|${p.edge}`;

  // ---- audio: the Mac's built-in Mandarin voices, via the browser ------
  let voice = null;
  function pickVoice() {
    const voices = speechSynthesis.getVoices().filter((v) => /^zh[-_]CN/i.test(v.lang));
    voice =
      voices.find((v) => /premium|enhanced/i.test(v.name)) ||
      voices.find((v) => /tingting/i.test(v.name)) ||
      voices[0] ||
      null;
  }
  const canSpeak = "speechSynthesis" in window;
  if (canSpeak) {
    pickVoice();
    speechSynthesis.addEventListener("voiceschanged", pickVoice);
  }
  function speak(text) {
    if (!canSpeak) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "zh-CN";
    if (voice) u.voice = voice;
    u.rate = 0.8; // a little slower than conversational, to hear the tones
    speechSynthesis.speak(u);
  }

  function soundButton(text, label) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "zh-sound-btn";
    btn.textContent = label;
    btn.setAttribute("aria-label", "Play the word again");
    btn.addEventListener("click", () => speak(text));
    return btn;
  }

  // ---- screens ---------------------------------------------------------
  function updateProgress() {
    el("progress").textContent = total ? `${done.size} of ${total} Mandarin prompts` : "";
  }

  function render() {
    busy = false;
    updateProgress();
    if (i >= queue.length) return finish();
    const p = queue[i];
    const info = EDGES[p.edge];
    showSection("zh-card");

    const badge = $("zh-badge");
    badge.textContent = p._retry ? "Retry" : p.is_new ? "New word" : "";
    badge.classList.toggle("hidden", !(p._retry || p.is_new));

    $("zh-ask").textContent = info.ask;
    const box = $("zh-prompt");
    box.replaceChildren();
    if (info.show === "hanzi") {
      const h = document.createElement("p");
      h.className = "zh-hanzi";
      h.lang = "zh-CN";
      h.textContent = p.hanzi;
      box.appendChild(h);
    } else if (info.show === "meaning") {
      const m = document.createElement("p");
      m.className = "prompt";
      m.textContent = p.meaning;
      box.appendChild(m);
    } else {
      box.appendChild(soundButton(p.hanzi, "🔊 Play"));
      if (!canSpeak) {
        const warn = document.createElement("p");
        warn.className = "zh-note";
        warn.textContent = "This browser can't play audio. Try Safari or Chrome.";
        box.appendChild(warn);
      }
      setTimeout(() => speak(p.hanzi), 150);
    }

    for (const id of ["zh-result", "zh-reveal", "zh-actions"]) $(id).classList.add("hidden");
    const typed = p.answer !== "meaning";
    $("zh-form").classList.toggle("hidden", !typed);
    $("zh-reveal-btn").classList.toggle("hidden", typed);
    if (typed) {
      const input = $("zh-input");
      input.value = "";
      input.disabled = false;
      input.placeholder = PLACEHOLDERS[p.answer];
      input.lang = p.answer === "hanzi" ? "zh-CN" : "en";
      setTimeout(() => input.focus(), 0);
    } else {
      setTimeout(() => $("zh-reveal-btn").focus(), 0);
    }
  }

  // The whole triangle, shown after every answer.
  function showReveal(p) {
    const box = $("zh-reveal");
    box.replaceChildren();
    const h = document.createElement("p");
    h.className = "zh-hanzi zh-hanzi-small";
    h.lang = "zh-CN";
    h.textContent = p.hanzi;
    const py = document.createElement("p");
    py.className = "zh-pinyin";
    py.textContent = p.pinyin + " ";
    py.appendChild(soundButton(p.hanzi, "🔊"));
    const m = document.createElement("p");
    m.className = "zh-meaning";
    m.textContent = p.meaning;
    box.append(h, py, m);
    if (p.note) {
      const n = document.createElement("div");
      n.className = "cultural-note";
      n.textContent = p.note;
      box.appendChild(n);
    }
    box.classList.remove("hidden");
    speak(p.hanzi);
  }

  function showResult(kind, text) {
    const r = $("zh-result");
    r.className = `result ${kind}`;
    r.textContent = text;
  }

  // Records a first attempt (retries don't touch the schedule), then either
  // marks the prompt done or sends it to the back of the queue to try again.
  async function grade(p, correct) {
    if (!p._retry) {
      reviewed++;
      try {
        await api("/api/zh/review", {
          method: "POST",
          body: JSON.stringify({ word_id: p.word_id, edge: p.edge, correct }),
        });
      } catch (e) {
        showResult("wrong", "Couldn't save that answer. Is Lexi still running?");
        $("zh-result").classList.remove("hidden");
        return false;
      }
    }
    if (correct) done.add(keyOf(p));
    else queue.push({ ...p, _retry: true });
    updateProgress();
    return true;
  }

  function continueButton() {
    const actions = $("zh-actions");
    const btn = document.createElement("button");
    btn.className = "primary";
    btn.textContent = "Continue";
    btn.addEventListener("click", () => { i++; render(); });
    actions.replaceChildren(btn);
    actions.classList.remove("hidden");
    setTimeout(() => btn.focus(), 0);
  }

  // Chinese input methods use Enter to confirm a character choice. Ignore a
  // submit that lands right as composition ends, so picking 好 doesn't also
  // send the answer.
  let compositionEndedAt = 0;
  $("zh-input").addEventListener("compositionend", () => { compositionEndedAt = Date.now(); });

  $("zh-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy || Date.now() - compositionEndedAt < 80) return;
    const p = queue[i];
    const typed = $("zh-input").value;
    if (!typed.trim()) return;
    busy = true;
    let result;
    try {
      ({ result } = await api("/api/zh/check", {
        method: "POST",
        body: JSON.stringify({ word_id: p.word_id, edge: p.edge, typed }),
      }));
    } catch (err) {
      busy = false;
      showResult("wrong", "Couldn't check that. Is Lexi still running?");
      $("zh-result").classList.remove("hidden");
      return;
    }
    $("zh-input").disabled = true;
    const correct = result === "exact";
    showResult(
      correct ? "exact" : result === "tones" ? "close" : "wrong",
      correct ? "✓ Correct" : result === "tones" ? `Right syllables, check the tones: ${p.pinyin}` : `Not quite. It's ${p.answer === "hanzi" ? p.hanzi : p.pinyin}`,
    );
    $("zh-result").classList.remove("hidden");
    showReveal(p);
    if (await grade(p, correct)) continueButton();
  });

  $("zh-reveal-btn").addEventListener("click", () => {
    if (busy) return;
    const p = queue[i];
    $("zh-reveal-btn").classList.add("hidden");
    showReveal(p);
    const actions = $("zh-actions");
    const yes = document.createElement("button");
    yes.textContent = "Got it";
    const no = document.createElement("button");
    no.textContent = "Not quite";
    const answer = async (correct) => {
      if (busy) return;
      busy = true;
      if (await grade(p, correct)) { i++; render(); } else busy = false;
    };
    yes.addEventListener("click", () => answer(true));
    no.addEventListener("click", () => answer(false));
    actions.replaceChildren(yes, no);
    actions.classList.remove("hidden");
    setTimeout(() => yes.focus(), 0);
  });

  function finish() {
    el("done-message").textContent = `Done! ${reviewed} Mandarin prompt${reviewed === 1 ? "" : "s"} today. 加油！`;
    el("keep-going-btn").classList.add("hidden");
    showSection("done-state");
  }

  // ---- entry points for app.js ---------------------------------------
  async function summary() {
    try {
      const s = await api("/api/zh/status");
      if (!s.words) return "No words yet";
      if (s.due) return `${s.due} prompt${s.due === 1 ? "" : "s"} due today`;
      if (s.done_today) return "Done for today";
      return "All caught up";
    } catch (e) {
      return "";
    }
  }

  async function start() {
    const [s, prompts] = await Promise.all([api("/api/zh/status"), api("/api/zh/due")]);
    if (!prompts.length) {
      el("empty-state-message").textContent = !s.words
        ? "No Mandarin words yet. Tell Claude a word from Duolingo (here in the chat or in the terminal) and it will add a card."
        : s.done_today
          ? "You're all done with Mandarin for today. 加油！"
          : "No Mandarin prompts due right now.";
      el("progress").textContent = "";
      showSection("empty-state");
      return;
    }
    queue = prompts;
    i = 0;
    total = prompts.length;
    done = new Set();
    reviewed = 0;
    render();
  }

  window.lexiZh = { summary, start };
})();
