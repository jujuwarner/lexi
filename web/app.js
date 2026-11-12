// Lexi web UI — talks to api.py over the same-origin /api/* routes.
// No review logic lives here; this just renders cards and relays your
// answers/ratings to the backend, which is the only place SM-2 actually runs.

const LANGUAGE_NAMES = { fr: "French", ru: "Russian", zh: "Mandarin" };

let allDueCards = []; // everything due today, before any language filter
let cards = []; // the live session queue -- grows as missed cards get requeued
let index = 0;
let mode = null; // "write" | "recognize"
let reviewedCount = 0; // genuine first attempts only, not retries
let sessionLanguage = null; // which language the current session is for --
// lets the "keep going on backlog" option know what to fetch more of

// The progress display's denominator/numerator are deliberately NOT
// index/cards.length -- that pair grows every time something gets
// requeued, which reads as "more words got recommended" when really
// it's the same word coming back around. `totalRecommended` is captured
// once, at session start, and never changes; `pendingIds` starts as every
// recommended word's id and only loses one once it's genuinely done
// (missing it doesn't remove it -- see submitReviewFirstAttempt/
// advanceAfterRetry), so the displayed count only moves forward on real
// completions.
let totalRecommended = 0;
let pendingIds = new Set();

// How many times a word has been missed so far this session (first
// attempt + any failed retries), keyed by id. This is the difficulty
// signal now -- see resolveRetryAttempt() -- replacing manual Hard/Good
// /Easy self-rating, which went mostly unused in practice: you only ever
// rated a word AFTER getting it right, by which point it rarely felt
// "hard" even when it genuinely was. A word that takes real, repeated
// struggle gets auto-flagged priority once it's finally answered
// correctly, instead.
let wrongCounts = {};
const PRIORITY_RETRY_THRESHOLD = 3;

// Guards against a rapid double-submit (two Enter presses, or Enter then
// clicking Check, before the first request round-trips) firing the advance
// logic twice for the same card. Without this, a double-fire double-posts
// /api/review for that word and increments `index` by 2 -- silently
// skipping the next card in the queue and duplicating the retry copy.
// Set the instant a card starts being processed; cleared only once the
// next card is actually rendered.
let isProcessing = false;

const el = (id) => document.getElementById(id);

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

// Refreshes the "✓ Done for today" / backlog notes in the header so they
// track a session as it happens -- without this, they're frozen at
// whatever /api/status reported on page load and never budge while you
// review, even though every /api/review call is quietly moving them.
// Not awaited by callers -- it shouldn't hold up advancing to the next
// card just to update header text.
async function refreshHeaderNotes() {
  const status = await api("/api/status");
  renderCompletedNote(status.completed_languages);
  renderBacklogNote(status.backlog);
}

async function postReview(id, quality) {
  await api("/api/review", {
    method: "POST",
    body: JSON.stringify({ id, quality }),
  });
  refreshHeaderNotes();
}

function updateProgress() {
  if (!totalRecommended) return;
  const completed = totalRecommended - pendingIds.size;
  el("progress").textContent = `${completed} of ${totalRecommended} recommended`;
}

function showSection(id) {
  for (const s of ["language-picker", "mode-picker", "empty-state", "write-card", "recognize-card", "done-state"]) {
    el(s).classList.toggle("hidden", s !== id);
  }
}

function renderRevealHtml(data) {
  let html = `<p class="field-label">${(cards[index]?.language || "fr").toUpperCase()} definition</p><p>${data.definition_in_language}</p>`;
  if (data.source_sentence) {
    html += `<p class="field-label">From</p><blockquote>"${data.source_sentence}"${data.source_title ? ` — ${data.source_title}` : ""}</blockquote>`;
  }
  if (data.cultural_note) {
    html += `<div class="cultural-note">🌿 ${data.cultural_note}</div>`;
  }
  return html;
}

// A plain "move on when you're ready" affordance for a first attempt
// that was already correct -- no rating to make, just pacing control so
// you can still read the definition/cultural note before advancing.
function renderContinueButton(container, onContinue) {
  container.innerHTML = "";
  const btn = document.createElement("button");
  btn.textContent = "Continue →";
  btn.className = "primary";
  btn.addEventListener("click", onContinue);
  container.appendChild(btn);
  container.classList.remove("hidden");
  // Focus it so Enter activates it directly, same as pressing Enter in
  // the write-input to submit -- no reaching for the mouse needed.
  setTimeout(() => btn.focus(), 0);
}

// Shared by both the Write-mode immediate retype and the later queued
// retry drill (either mode): updates the wrongCounts/priority difficulty
// signal for a word that was missed earlier this session, and reports
// back whether it should be requeued for another pass.
function resolveRetryAttempt(entry, gotIt) {
  if (gotIt) {
    const totalWrong = wrongCounts[entry.id] || 0;
    delete wrongCounts[entry.id];
    pendingIds.delete(entry.id);
    if (totalWrong >= PRIORITY_RETRY_THRESHOLD && !entry.priority) {
      api("/api/toggle_priority", {
        method: "POST",
        body: JSON.stringify({ id: entry.id }),
      }).catch(() => {}); // fire-and-forget -- doesn't block advancing
    }
    return false;
  }
  wrongCounts[entry.id] = (wrongCounts[entry.id] || 1) + 1;
  return true;
}

// Purely visual — unlike priority, era is never written back via the API
// from here; it's authored directly in vocab.json. Just shows/hides a
// colored chip for words tied to a specific bygone period (e.g. serfdom-era
// Russia), separate from "priority" which drives SM-2 scheduling.
function renderEraBadge(badgeId, entry) {
  const badge = el(badgeId);
  if (!entry.era) {
    badge.classList.add("hidden");
    return;
  }
  badge.textContent = entry.era.label;
  badge.style.backgroundColor = `${entry.era.color}22`; // low-opacity tint
  badge.style.color = entry.era.color;
  badge.classList.remove("hidden");
}

function renderPriorityButton(btnId, entry) {
  const btn = el(btnId);
  btn.textContent = entry.priority ? "★" : "☆";
  btn.classList.toggle("active", entry.priority);
  btn.title = entry.priority
    ? "Priority — reviewed more often. Click to unmark."
    : "Mark as priority (reviewed more often)";
}

async function togglePriority(btnId) {
  const entry = cards[index];
  const data = await api("/api/toggle_priority", {
    method: "POST",
    body: JSON.stringify({ id: entry.id }),
  });
  entry.priority = data.priority;
  renderPriorityButton(btnId, entry);
}

// A missed attempt already got its real SM-2 outcome locked in via
// /api/review (or, for a later retry-drill miss, was locked in back on the
// genuine first attempt) -- this just adds it back into the session's
// queue for further practice. Retry attempts never call /api/review again.
// Goes to the END of the queue -- used when a retry attempt is missed, so
// you get a breather on other words before it comes back around again,
// rather than being stuck retyping the same word forever.
function requeueForRetry(entry) {
  cards.push({ ...entry, _isRetry: true });
}

// A missed first attempt in Recognize mode (or a Write-mode "close" match
// self-rated as Again) gets its retry inserted immediately next -- so it
// comes back around right away while it's fresh, instead of only
// rejoining the queue somewhere down the line. Write mode's ordinary
// wrong/skip case doesn't go through this at all -- see
// handleImmediateRetypeSubmit below, which keeps you on the very same
// screen instead of flashing to what reads as a fresh card.
function requeueImmediately(entry) {
  cards.splice(index + 1, 0, { ...entry, _isRetry: true });
}

async function submitReviewFirstAttempt(entry, qualityKey) {
  if (isProcessing) return;
  isProcessing = true;
  await postReview(entry.id, qualityKey);
  reviewedCount += 1;
  if (qualityKey === "1") {
    wrongCounts[entry.id] = 1;
    requeueImmediately(entry);
  } else {
    pendingIds.delete(entry.id); // genuinely done -- not a miss
  }
  index += 1;
  renderCard();
}

function advanceAfterRetry(gotIt, entry) {
  if (isProcessing) return;
  isProcessing = true;
  if (resolveRetryAttempt(entry, gotIt)) requeueForRetry(entry);
  index += 1;
  renderCard();
}

function renderCard() {
  isProcessing = false; // the next card is about to render -- unblock it
  updateProgress();

  if (index >= cards.length) {
    el("done-message").textContent = `Done! Reviewed ${reviewedCount} card(s). See you next time.`;
    showSection("done-state");
    offerKeepGoing();
    return;
  }

  if (mode === "write") renderWriteCard();
  else renderRecognizeCard();
}

const WRITE_INPUT_PLACEHOLDER = "Type the word (le/la/l' if it's a noun)…";
const RETYPE_PLACEHOLDER = "Type it once more to help it stick…";

// Set while a missed Write-mode first attempt is waiting on its immediate
// retype (see handleImmediateRetypeSubmit) -- the very next submit on this
// same screen is that retype, not a fresh answer to a new card.
let pendingRetypeEntry = null;

function renderWriteCard() {
  showSection("write-card");
  const entry = cards[index];
  pendingRetypeEntry = null;

  renderPriorityButton("write-priority-btn", entry);
  renderEraBadge("write-era-badge", entry);
  el("write-prompt").textContent = entry.translation_en;
  el("write-retry-badge").classList.toggle("hidden", !entry._isRetry);
  el("write-input").placeholder = WRITE_INPUT_PLACEHOLDER;
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

  if (pendingRetypeEntry) {
    if (isProcessing) return;
    isProcessing = true;
    await handleImmediateRetypeSubmit(typed);
    return;
  }
  // An empty submission ("I don't know, just show me") is a valid way to
  // give up on a card rather than getting stuck -- checked normally, an
  // empty string never matches, so it resolves as "wrong" on its own.

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
  } else if (typed === "") {
    resultBox.textContent = `No worries — the answer is: ${data.expected}`;
  } else {
    resultBox.textContent = `✗ Not quite — the answer is: ${data.expected}`;
  }
  resultBox.classList.remove("hidden");

  const revealBox = el("write-reveal");
  revealBox.innerHTML = renderRevealHtml(data);
  revealBox.classList.remove("hidden");

  if (entry._isRetry) {
    // Retry drill: no further SM-2 update -- the real outcome was already
    // locked in on the genuine first attempt. A correct retry drops it;
    // a missed retry gets the same same-screen immediate retype as a
    // missed first attempt, instead of just showing the answer and
    // jumping to a different card.
    const gotIt = data.result === "exact" || data.result === "close";
    if (gotIt) {
      setTimeout(() => advanceAfterRetry(true, entry), 900);
    } else {
      setTimeout(() => {
        pendingRetypeEntry = entry;
        el("write-input").placeholder = RETYPE_PLACEHOLDER;
        el("write-input").value = "";
        el("write-form").classList.remove("hidden");
        setTimeout(() => el("write-input").focus(), 0);
      }, 900);
    }
    return;
  }

  if (data.result === "exact" || data.result === "close") {
    // A clean match is automatically Easy, a close match (accent/article
    // slip) is automatically Good -- no self-rating. Just a plain
    // "Continue" button so you can still read the definition/cultural
    // note at your own pace before moving on.
    const quality = data.result === "exact" ? "4" : "3";
    renderContinueButton(el("write-quality"), () => submitReviewFirstAttempt(entry, quality));
  } else {
    // Missed -- lock in the real "Again" outcome now (this doesn't move
    // to a new card), then have them retype it right here on the same
    // screen, answer and definition still visible, instead of flashing
    // through what would read as a brand new card for the same word.
    if (isProcessing) return;
    isProcessing = true;
    await postReview(entry.id, "1");
    reviewedCount += 1;
    wrongCounts[entry.id] = 1;
    pendingRetypeEntry = entry;
    isProcessing = false; // the retype input is live now -- unblock for it
    el("write-input").placeholder = RETYPE_PLACEHOLDER;
    el("write-input").value = "";
    el("write-form").classList.remove("hidden");
    setTimeout(() => el("write-input").focus(), 0);
  }
}

async function handleImmediateRetypeSubmit(typed) {
  const entry = pendingRetypeEntry;
  pendingRetypeEntry = null;
  el("write-form").classList.add("hidden");

  const data = await api("/api/check", {
    method: "POST",
    body: JSON.stringify({ id: entry.id, typed }),
  });
  const gotIt = data.result === "exact" || data.result === "close";

  const resultBox = el("write-result");
  resultBox.className = `result ${gotIt ? "exact" : "wrong"}`;
  resultBox.textContent = gotIt
    ? `✓ Nice, that's it! ${data.expected}`
    : typed === ""
    ? `The answer is: ${data.expected}`
    : `✗ Not quite — the answer is: ${data.expected}`;
  resultBox.classList.remove("hidden");

  // This retype was just reinforcement -- typed while the answer was
  // still right there on screen, which isn't the same as actually
  // recalling it. Always send it back around for a later, blank retry
  // drill (no answer visible) before it's considered learned, regardless
  // of how the copy-typing went -- a correct copy here does NOT clear the
  // difficulty signal or count as done; only a genuine blank-prompt retry
  // success (in advanceAfterRetry) does that. A wrong copy still counts
  // toward the difficulty signal, same as any other miss.
  if (!gotIt) wrongCounts[entry.id] = (wrongCounts[entry.id] || 1) + 1;
  requeueForRetry(entry);
  index += 1;
  setTimeout(renderCard, 900);
}

function renderRecognizeCard() {
  showSection("recognize-card");
  const entry = cards[index];

  renderPriorityButton("recognize-priority-btn", entry);
  renderEraBadge("recognize-era-badge", entry);
  el("recognize-prompt-label").textContent = LANGUAGE_NAMES[entry.language] || entry.language;
  el("recognize-word").textContent = entry.display_word;
  el("recognize-retry-badge").classList.toggle("hidden", !entry._isRetry);
  el("recognize-reveal").classList.add("hidden");
  el("recognize-quality").classList.add("hidden");
  el("recognize-reveal-btn").classList.remove("hidden");
  setTimeout(() => el("recognize-reveal-btn").focus(), 0);
}

function handleRecognizeReveal() {
  if (isProcessing) return; // guard against a double-click stacking duplicate reveals
  const entry = cards[index];
  el("recognize-reveal-btn").classList.add("hidden");

  const revealBox = el("recognize-reveal");
  let html = `<p class="field-label">English</p><p>${entry.translation_en}</p>`;
  html += renderRevealHtml(entry);
  revealBox.innerHTML = html;
  revealBox.classList.remove("hidden");

  // Simple got-it-or-not self-report -- no 1-4 scale, here or on a retry.
  // Recognize mode has no typed answer to auto-check, so this binary
  // self-report is as close to automatic as it can get; a first-attempt
  // "got it" is scored Easy automatically (no further rating to make),
  // and a miss feeds the same wrongCounts/priority difficulty signal as
  // everywhere else.
  const box = el("recognize-quality");
  box.innerHTML = "";
  const yesBtn = document.createElement("button");
  yesBtn.textContent = "Got it";
  const noBtn = document.createElement("button");
  noBtn.textContent = "Not quite";
  if (entry._isRetry) {
    yesBtn.addEventListener("click", () => advanceAfterRetry(true, entry));
    noBtn.addEventListener("click", () => advanceAfterRetry(false, entry));
  } else {
    yesBtn.addEventListener("click", () => submitReviewFirstAttempt(entry, "4"));
    noBtn.addEventListener("click", () => submitReviewFirstAttempt(entry, "1"));
  }
  box.appendChild(yesBtn);
  box.appendChild(noBtn);
  box.classList.remove("hidden");
  setTimeout(() => yesBtn.focus(), 0); // Enter defaults to "Got it"
}

function startSession(chosenMode) {
  mode = chosenMode;
  sessionLanguage = cards[0]?.language || sessionLanguage;
  index = 0;
  reviewedCount = 0;
  totalRecommended = cards.length;
  pendingIds = new Set(cards.map((c) => c.id));
  wrongCounts = {};
  renderCard();
}

// Checks whether there's still backlog left for the language that was
// just finished, and if so, shows the "keep going" button so you can
// pull another chunk right now instead of waiting for tomorrow. Fetches
// fresh status rather than reusing the one from page load, since a whole
// session's worth of reviewing just happened and the numbers have moved.
async function offerKeepGoing() {
  const btn = el("keep-going-btn");
  btn.classList.add("hidden"); // hide any stale state while we check
  if (!sessionLanguage) return;

  const status = await api("/api/status");
  const info = status.backlog[sessionLanguage];
  if (!info) return; // nothing left beyond today's normal cap

  const name = LANGUAGE_NAMES[sessionLanguage] || sessionLanguage;
  el("keep-going-count").textContent =
    `${info.due} more ${name} card(s) due · ~${info.days} day${info.days === 1 ? "" : "s"} to clear`;
  btn.classList.remove("hidden");
}

async function keepGoingOnBacklog() {
  if (!sessionLanguage) return;
  const more = await api(`/api/backlog?language=${encodeURIComponent(sessionLanguage)}`);
  if (more.length === 0) return; // backlog moved under us; nothing to add
  allDueCards = allDueCards.concat(more);
  cards = more;
  startSession(mode); // same mode as the session that just finished
}

// Set by chooseLanguage() -- distinguishes a normal active-today session
// from a deliberate backlog continuation, purely for showModePicker()'s
// wording ("recommended for today" doesn't fit a backlog you chose to
// keep going on well past today's normal cap).
let sessionKind = "active";

function showModePicker() {
  // When there was an actual language choice, chooseLanguage() already
  // narrowed `cards` down to one language before this runs -- so a single
  // language present here just means that was the only (or only
  // remaining) one due, and the picker screen got skipped. Either way,
  // say which language it is instead of leaving that unstated.
  const languages = [...new Set(cards.map((c) => c.language))];
  const languageLabel = languages.length === 1 ? `${LANGUAGE_NAMES[languages[0]] || languages[0]} ` : "";
  const verb = sessionKind === "backlog" ? "from the backlog" : "recommended for today";
  el("progress").textContent = `${cards.length} ${languageLabel}word${cards.length === 1 ? "" : "s"} ${verb}`;
  showSection("mode-picker");
}

// `kind` distinguishes a normal active-today pick from deliberately
// continuing on a language whose cap is already spent for today -- the
// latter fetches straight from the uncapped backlog instead of filtering
// today's (already-exhausted) due list.
async function chooseLanguage(lang, kind = "active") {
  sessionKind = kind;
  if (kind === "backlog") {
    cards = await api(`/api/backlog?language=${encodeURIComponent(lang)}`);
  } else {
    cards = allDueCards.filter((c) => c.language === lang);
  }
  showModePicker();
}

// Renders the "✓ Done for today: French" note in the header -- this sits
// outside the toggled <section>s (see showSection()) specifically so it
// stays visible no matter which screen is showing, including the common
// case where only one language is still active and the language-picker
// screen gets skipped entirely.
function renderCompletedNote(completedLanguages) {
  const note = el("completed-note");
  if (completedLanguages.length === 0) {
    note.classList.add("hidden");
    note.textContent = "";
    return;
  }
  const names = completedLanguages.map((lang) => LANGUAGE_NAMES[lang] || lang);
  note.textContent = `✓ Done for today: ${names.join(", ")}`;
  note.classList.remove("hidden");
}

// Renders a quiet note about any language whose backlog is big enough to
// take more than one day to clear at the daily cap -- same "outside the
// toggled sections" placement as renderCompletedNote(), for the same
// reason: it should stay visible regardless of which screen is showing.
function renderBacklogNote(backlog) {
  const note = el("backlog-note");
  const langs = Object.keys(backlog);
  if (langs.length === 0) {
    note.classList.add("hidden");
    note.textContent = "";
    return;
  }
  const parts = langs.map((lang) => {
    const { due, days } = backlog[lang];
    const name = LANGUAGE_NAMES[lang] || lang;
    return `${name} — ${due} in backlog (~${days} day${days === 1 ? "" : "s"})`;
  });
  note.textContent = parts.join(" · ");
  note.classList.remove("hidden");
}

// Renders the language-picker buttons for a mix of normal active-today
// options and "continue backlog" options (languages already done for
// today that still have more backlog waiting) -- the two are visually
// distinguished, but both lead into chooseLanguage() the same way.
function renderLanguageOptions(options) {
  const container = el("language-buttons");
  container.innerHTML = "";
  for (const opt of options) {
    const name = LANGUAGE_NAMES[opt.lang] || opt.lang;
    const btn = document.createElement("button");
    btn.className = "primary";
    const label = opt.kind === "backlog" ? `Continue ${name} backlog` : name;
    const sub =
      opt.kind === "backlog"
        ? `${opt.count} card${opt.count === 1 ? "" : "s"} in backlog`
        : `${opt.count} word${opt.count === 1 ? "" : "s"}`;
    btn.innerHTML = `${label}<br /><span>${sub}</span>`;
    btn.addEventListener("click", () => chooseLanguage(opt.lang, opt.kind));
    container.appendChild(btn);
  }
}

async function init() {
  el("restart-btn").addEventListener("click", () => location.reload());
  el("keep-going-btn").addEventListener("click", keepGoingOnBacklog);

  const [due, status] = await Promise.all([api("/api/due"), api("/api/status")]);
  allDueCards = due;
  cards = allDueCards;
  const completedLanguages = status.completed_languages;
  renderCompletedNote(completedLanguages);
  renderBacklogNote(status.backlog);

  el("mode-write").addEventListener("click", () => startSession("write"));
  el("mode-recognize").addEventListener("click", () => startSession("recognize"));
  el("write-form").addEventListener("submit", handleWriteSubmit);
  el("recognize-reveal-btn").addEventListener("click", handleRecognizeReveal);
  el("write-priority-btn").addEventListener("click", () => togglePriority("write-priority-btn"));
  el("recognize-priority-btn").addEventListener("click", () => togglePriority("recognize-priority-btn"));

  // What you could start right now: any language with an active batch
  // still due today, plus any language that's done for today but still
  // has backlog you could deliberately keep going on -- e.g. you've hit
  // French's cap for the day, but want to come back this evening and do
  // another chunk rather than wait for tomorrow.
  const activeLangs = [...new Set(cards.map((c) => c.language))];
  const continuableBacklogLangs = completedLanguages.filter((lang) => lang in status.backlog);

  const options = [
    ...activeLangs.map((lang) => ({
      lang,
      kind: "active",
      count: cards.filter((c) => c.language === lang).length,
    })),
    ...continuableBacklogLangs.map((lang) => ({
      lang,
      kind: "backlog",
      count: status.backlog[lang].due,
    })),
  ];

  if (options.length === 0) {
    // Nothing active and nothing continuable, but tell apart "you
    // finished everything that was due" from "there was never anything
    // due in the first place" -- only the former actually happened today.
    el("empty-state-message").textContent =
      completedLanguages.length > 0
        ? "You're all done for today. Nice work! 🎉"
        : "Nothing recommended right now. Nice work staying caught up!";
    showSection("empty-state");
    el("progress").textContent = "";
    return;
  }

  // Only ask which language/option when there's actually a choice to
  // make -- a single option (the common case) skips straight past this.
  if (options.length > 1) {
    renderLanguageOptions(options);
    el("progress").textContent = `${options.length} option${options.length === 1 ? "" : "s"} available right now`;
    showSection("language-picker");
    return;
  }

  await chooseLanguage(options[0].lang, options[0].kind); // calls showModePicker() itself
}

init();
