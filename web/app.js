// Lexi web UI — talks to api.py over the same-origin /api/* routes.
// No review logic lives here; this just renders cards and relays your
// answers/ratings to the backend, which is the only place SM-2 actually runs.

const QUALITY_LABELS = { "1": "Again", "2": "Hard", "3": "Good", "4": "Easy" };

let cards = [];
let index = 0;
let mode = null; // "write" | "recognize"

const el = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

function updateProgress() {
  if (!cards.length) return;
  el("progress").textContent = `${Math.min(index + 1, cards.length)} of ${cards.length} recommended`;
}

function showSection(id) {
  for (const s of ["mode-picker", "empty-state", "write-card", "recognize-card", "done-state"]) {
    el(s).classList.toggle("hidden", s !== id);
  }
}

function renderRevealHtml(data) {
  let html = `<p class="field-label">${(cards[index]?.language || "fr").toUpperCase()} definition</p><p>${data.definition_in_language}</p>`;
  if (data.source_sentence) {
    html += `<p class="field-label">From</p><blockquote>"${data.source_sentence}"${data.source_title ? ` — ${data.source_title}` : ""}</blockquote>`;
  }
  if (data.cultural_note) {
    html += `<div class="cultural-note">📌 ${data.cultural_note}</div>`;
  }
  return html;
}

function renderQualityButtons(container, allowedKeys, onPick) {
  container.innerHTML = "";
  for (const key of allowedKeys) {
    const btn = document.createElement("button");
    btn.textContent = QUALITY_LABELS[key];
    btn.dataset.quality = key;
    btn.addEventListener("click", () => onPick(key));
    container.appendChild(btn);
  }
  container.classList.remove("hidden");
}

async function submitReview(id, qualityKey) {
  await api("/api/review", {
    method: "POST",
    body: JSON.stringify({ id, quality: qualityKey }),
  });
  index += 1;
  renderCard();
}

function renderCard() {
  updateProgress();

  if (index >= cards.length) {
    el("done-message").textContent = `Done! Reviewed ${cards.length} card(s). See you next time.`;
    showSection("done-state");
    return;
  }

  if (mode === "write") renderWriteCard();
  else renderRecognizeCard();
}

function renderWriteCard() {
  showSection("write-card");
  const entry = cards[index];

  el("write-prompt").textContent = entry.translation_en;
  el("write-input").value = "";
  el("write-result").classList.add("hidden");
  el("write-reveal").classList.add("hidden");
  el("write-quality").classList.add("hidden");
  el("write-form").classList.remove("hidden");
  setTimeout(() => el("write-input").focus(), 0);
}

async function handleWriteSubmit(e) {
  e.preventDefault();
  const typed = el("write-input").value.trim();
  if (!typed) return;

  const entry = cards[index];
  const data = await api("/api/check", {
    method: "POST",
    body: JSON.stringify({ id: entry.id, typed }),
  });

  el("write-form").classList.add("hidden");

  const resultBox = el("write-result");
  resultBox.className = `result ${data.result}`;
  if (data.result === "exact") {
    resultBox.textContent = `✓ Correct! ${data.expected}`;
  } else if (data.result === "close") {
    resultBox.textContent = `~ Close — you wrote "${typed}", correct is "${data.expected}"`;
  } else {
    resultBox.textContent = `✗ Not quite — the answer is: ${data.expected}`;
  }
  resultBox.classList.remove("hidden");

  const revealBox = el("write-reveal");
  revealBox.innerHTML = renderRevealHtml(data);
  revealBox.classList.remove("hidden");

  const qualityBox = el("write-quality");
  if (data.allowed_qualities.length > 0) {
    renderQualityButtons(qualityBox, data.allowed_qualities, (key) =>
      submitReview(entry.id, key)
    );
  } else {
    // Wrong answer — auto-rates as "Again", just needs a way to move on.
    qualityBox.innerHTML = "";
    const btn = document.createElement("button");
    btn.className = "primary";
    btn.textContent = "Continue";
    btn.addEventListener("click", () => submitReview(entry.id, "1"));
    qualityBox.appendChild(btn);
    qualityBox.classList.remove("hidden");
  }
}

function renderRecognizeCard() {
  showSection("recognize-card");
  const entry = cards[index];

  el("recognize-word").textContent = entry.display_word;
  el("recognize-reveal").classList.add("hidden");
  el("recognize-quality").classList.add("hidden");
  el("recognize-reveal-btn").classList.remove("hidden");
}

function handleRecognizeReveal() {
  const entry = cards[index];
  el("recognize-reveal-btn").classList.add("hidden");

  const revealBox = el("recognize-reveal");
  let html = `<p class="field-label">English</p><p>${entry.translation_en}</p>`;
  html += renderRevealHtml(entry);
  revealBox.innerHTML = html;
  revealBox.classList.remove("hidden");

  renderQualityButtons(el("recognize-quality"), ["1", "2", "3", "4"], (key) =>
    submitReview(entry.id, key)
  );
}

function startSession(chosenMode) {
  mode = chosenMode;
  index = 0;
  renderCard();
}

async function init() {
  cards = await api("/api/due");

  if (cards.length === 0) {
    showSection("empty-state");
    el("progress").textContent = "";
    return;
  }

  el("mode-write").addEventListener("click", () => startSession("write"));
  el("mode-recognize").addEventListener("click", () => startSession("recognize"));
  el("write-form").addEventListener("submit", handleWriteSubmit);
  el("recognize-reveal-btn").addEventListener("click", handleRecognizeReveal);

  el("progress").textContent = `${cards.length} word${cards.length === 1 ? "" : "s"} recommended for today`;
  showSection("mode-picker");
}

init();
