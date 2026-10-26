"use strict";
/* Kardo web app: deck list, study, practice, browse, stats and settings. The SQL Lab lives in lab.js. */

const $app = document.getElementById("app");
const store = {
  get(k, d) { try { const v = localStorage.getItem("kardo." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("kardo." + k, JSON.stringify(v)); } catch { /* private mode */ } },
};

// ------------------------------------------------------------ helpers

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const leaf = (name) => name.split("::").pop();
const qs = (o) => { const p = new URLSearchParams(); for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== "") p.set(k, v); const s = p.toString(); return s ? "?" + s : ""; };

// Call the JSON API. Objects are sent as JSON; the viewer's UTC offset rides along so the
// server knows when "today" starts for them. Throws an Error with the server's message.
async function api(path, opts = {}) {
  const headers = { "X-TZ-Offset": String(-new Date().getTimezoneOffset()), ...(opts.headers || {}) };
  let body = opts.body;
  if (body && !(body instanceof Blob) && !(body instanceof ArrayBuffer) && typeof body !== "string") {
    body = JSON.stringify(body); headers["Content-Type"] = "application/json";
  }
  let res;
  try {
    res = await fetch("/api/" + path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new Error("Can't reach the server. Check that Tailscale is connected.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

let toastTimer;
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

const ICON = {
  back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  chevron: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>',
  undo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 010 11H11"/></svg>',
  stats: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><path d="M5 20V11M12 20V4M19 20v-6"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4-4"/></svg>',
  gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/></svg>',
};

function isDark() {
  const t = store.get("theme", "auto");
  return t === "dark" || (t === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
}
function applyTheme() {
  const t = store.get("theme", "auto");
  if (t === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
}
applyTheme();

const BASE_CARD_CSS = `
:host { display: block; }
.kardo-root { min-height: 100%; }
.card { font-family: -apple-system, system-ui, sans-serif; font-size: 20px; line-height: 1.45; padding: 18px 16px 28px;
  color: #16181d; background: transparent; text-align: center; word-wrap: break-word; overflow-wrap: anywhere; }
.night_mode .card { color: #eceef2; }
.card img { max-width: 100%; height: auto; }
.card table { border-collapse: collapse; max-width: 100%; }
.card td, .card th { border: 1px solid rgba(128,128,128,.4); padding: 4px 6px; }
.card hr#answer { border: 0; border-top: 1px solid rgba(128,128,128,.35); margin: 16px 0; }
.cloze { font-weight: 700; color: #2f6fe4; }
.night_mode .cloze { color: #6d9cf3; }
audio { width: 100%; margin: 6px 0; }
`;

// Cards are drawn inside a shadow root so a deck's own CSS (from its Anki note type) styles
// the card without leaking into the app, and the app's CSS can't break the card.
// Anki's .nightMode / .night_mode classes are set in dark mode so deck styles can adapt.
function renderCard(host, html, css, extraClass = "") {
  const root = host.shadowRoot || host.attachShadow({ mode: "open" });
  const dark = isDark();
  root.innerHTML = `<style>${BASE_CARD_CSS}\n${css || ""}</style>` +
    `<div class="kardo-root ${dark ? "nightMode night_mode" : ""}"><div class="card ${dark ? "nightMode night_mode" : ""} ${extraClass}">${html}</div></div>`;
  return root;
}

function topbar({ title, back, actions = "" }) {
  return `<div class="topbar">
    ${back ? `<button class="icon-btn" data-nav="${esc(back)}" aria-label="Back">${ICON.back}</button>` : ""}
    ${title ? (back ? `<div class="title">${esc(title)}</div>` : `<h1>${esc(title)}</h1>`) : ""}
    ${actions}
  </div>`;
}

function bindNav(scope) {
  scope.querySelectorAll("[data-nav]").forEach((el) => el.addEventListener("click", (e) => {
    e.stopPropagation(); location.hash = el.dataset.nav;
  }));
}

function countSpan(n, cls) { return `<span class="${n ? cls : "zero"}">${n}</span>`; }

// ------------------------------------------------------------ router

// Hash routes: #/, #/deck/<id>, #/study/<id>, #/practice/<id>, #/browse, #/stats, #/settings, #/lab/...
// A view may set `cleanup` to remove its listeners/timers when the user navigates away.
let cleanup = null;
function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  document.querySelectorAll(".sheet-backdrop").forEach((el) => el.remove());
  const h = location.hash.replace(/^#/, "") || "/";
  const [path, query] = h.split("?");
  const params = Object.fromEntries(new URLSearchParams(query || ""));
  const parts = path.split("/").filter(Boolean);
  window.scrollTo(0, 0);
  const views = { "": homeView, deck: deckView, study: studyView, practice: practiceView, browse: browseView, stats: statsView, settings: settingsView, lab: labView };
  const view = views[parts[0] || ""] || homeView;
  Promise.resolve(view(parts[1], params)).catch((e) => {
    $app.innerHTML = `<div class="screen">${topbar({ title: "Kardo", back: "/" })}<div class="empty"><h2>Something went wrong</h2><p>${esc(e.message)}</p><button class="btn primary" onclick="location.reload()">Try again</button></div></div>`;
    bindNav($app);
  });
}
window.addEventListener("hashchange", route);

// ------------------------------------------------------------ home: deck tree

async function homeView() {
  const { decks } = await api("decks");
  const collapsed = new Set(store.get("collapsed", []));
  const names = new Set(decks.map((d) => d.name));
  const hasKids = (n) => decks.some((d) => d.name.startsWith(n + "::"));
  const hidden = (n) => { const p = n.split("::"); for (let i = 1; i < p.length; i++) { if (collapsed.has(p.slice(0, i).join("::"))) return true; } return false; };

  const rows = decks.filter((d) => !hidden(d.name)).map((d) => {
    const depth = d.name.split("::").length - 1;
    const kids = hasKids(d.name);
    return `<div class="row" data-deck="${d.id}" style="padding-left:${12 + depth * 18}px">
      ${kids ? `<button class="twisty ${collapsed.has(d.name) ? "" : "open"}" data-toggle="${esc(d.name)}" aria-label="Expand">${ICON.chevron}</button>` : `<span class="twisty"></span>`}
      <span class="name">${esc(leaf(d.name))}</span>
      <span class="counts">${countSpan(d.new, "c-new")}${countSpan(d.learn, "c-learn")}${countSpan(d.review, "c-review")}</span>
    </div>`;
  }).join("");

  $app.innerHTML = `<div class="screen">
    ${topbar({ title: "Kardo", actions: `
      <button class="icon-btn" data-nav="/lab" aria-label="SQL Lab">${LAB_ICON}</button>
      <button class="icon-btn" data-nav="/browse" aria-label="Browse cards">${ICON.search}</button>
      <button class="icon-btn" data-nav="/stats" aria-label="Statistics">${ICON.stats}</button>
      <button class="icon-btn" data-nav="/settings" aria-label="Settings">${ICON.gear}</button>` })}
    ${decks.length ? `<div class="list">${rows}</div>
      <div class="legend"><span class="c-new">New</span><span class="c-learn">Learning</span><span class="c-review">Due</span></div>`
      : `<div class="empty"><h2>No decks yet</h2><p>Import an .apkg or CSV file to get started.</p><button class="btn primary" data-nav="/settings">Import a deck</button></div>`}
    <div class="list" style="margin-top:16px"><button class="row home-lab" data-nav="/lab">${LAB_ICON}<span class="name"><b>SQL Lab</b><span>Write and run real queries, with answers checked</span></span></button></div>
  </div>`;
  bindNav($app);
  $app.querySelectorAll("[data-toggle]").forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation();
    const n = b.dataset.toggle;
    collapsed.has(n) ? collapsed.delete(n) : collapsed.add(n);
    store.set("collapsed", [...collapsed].filter((x) => names.has(x)));
    homeView();
  }));
  $app.querySelectorAll("[data-deck]").forEach((r) => r.addEventListener("click", () => { location.hash = `/deck/${r.dataset.deck}`; }));
}

// ------------------------------------------------------------ deck overview

async function deckView(id) {
  const [{ decks }, { tags }] = await Promise.all([api("decks"), api("tags")]);
  const d = decks.find((x) => String(x.id) === String(id));
  if (!d) { location.hash = "/"; return; }
  const tag = store.get("tag." + id, "");
  const shown = await api("next" + qs({ deck: id, tag }));
  const c = shown.counts;
  const any = c.new + c.learn + c.review > 0 || shown.card;
  $app.innerHTML = `<div class="screen">
    ${topbar({ title: d.name.includes("::") ? d.name.split("::").slice(0, -1).join(" › ") : "Decks", back: "/" })}
    <div class="overview">
      <h2>${esc(leaf(d.name))}</h2>
      <div class="big-counts">
        <div><b class="c-new">${c.new}</b><span>New</span></div>
        <div><b class="c-learn">${c.learn}</b><span>Learning</span></div>
        <div><b class="c-review">${c.review}</b><span>Due</span></div>
      </div>
      <div class="stack">
        <button class="btn primary" id="study" ${any ? "" : "disabled"}>${any ? "Study now" : "All done for today"}</button>
      </div>
      <p class="muted" style="font-size:14px;margin:12px 0 0">${d.total} cards · ${c.new_done} new and ${c.review_done} reviews done today</p>
    </div>
    <div class="section-title">Only cards with tag</div>
    <select class="input" id="tag"><option value="">Any tag</option>${tags.map((t) => `<option value="${esc(t.tag)}" ${t.tag === tag ? "selected" : ""}>${esc(t.tag)} (${t.count})</option>`).join("")}</select>
    <div class="section-title">Practice without changing your schedule</div>
    <div class="stack">
      <button class="btn" data-practice="20">Quiz me on 20 random cards</button>
      <button class="btn" data-practice="50">Quiz me on 50 random cards</button>
      <button class="btn" data-practice="50" data-only="struggling">Cards I've forgotten before</button>
    </div>
    <div class="spacer"></div>
    <button class="btn danger" id="del">Delete this deck</button>
  </div>`;
  bindNav($app);
  $app.querySelector("#study").onclick = () => { location.hash = `/study/${id}${qs({ tag })}`; };
  $app.querySelector("#tag").onchange = (e) => { store.set("tag." + id, e.target.value); deckView(id); };
  $app.querySelectorAll("[data-practice]").forEach((b) => b.onclick = () => {
    location.hash = `/practice/${id}${qs({ tag, n: b.dataset.practice, only: b.dataset.only })}`;
  });
  $app.querySelector("#del").onclick = async () => {
    if (!confirm(`Delete "${d.name}" and all its subdecks, cards and review history? This can't be undone.`)) return;
    await api(`decks/${id}`, { method: "DELETE" });
    toast("Deck deleted"); location.hash = "/";
  };
}

// ------------------------------------------------------------ study (spaced repetition)

async function studyView(id, params) {
  const tag = params.tag || "";
  let state = await api("next" + qs({ deck: id, tag }));
  let flipped = false, shownAt = Date.now(), busy = false, waitTimer = null;
  const backTo = `/deck/${id}`;

  $app.innerHTML = `<div class="screen study">
    <div class="topbar">
      <button class="icon-btn" data-nav="${backTo}" aria-label="Close">${ICON.close}</button>
      <div class="study-counts" id="counts"></div>
      <button class="icon-btn" id="undo" aria-label="Undo last answer">${ICON.undo}</button>
    </div>
    <div class="deck-path" id="path"></div>
    <div class="card-wrap" id="wrap"><div class="card-host" id="host"></div></div>
    <div class="answer-bar" id="bar"></div>
  </div>`;
  bindNav($app);
  const $counts = $app.querySelector("#counts"), $host = $app.querySelector("#host"), $bar = $app.querySelector("#bar"),
    $wrap = $app.querySelector("#wrap"), $path = $app.querySelector("#path");

  function draw() {
    clearTimeout(waitTimer);
    const c = state.counts, card = state.card;
    const act = card ? (card.state === "new" ? "new" : card.state === "review" ? "review" : "learn") : "";
    $counts.innerHTML = `<span class="c-new ${act === "new" ? "active" : ""}">${c.new}</span>
      <span class="c-learn ${act === "learn" ? "active" : ""}">${c.learn}</span>
      <span class="c-review ${act === "review" ? "active" : ""}">${c.review}</span>`;
    if (!card) {
      $path.textContent = "";
      $wrap.style.display = "none";
      const nxt = state.next_learning_due;
      const mins = nxt ? Math.max(1, Math.ceil((nxt * 1000 - Date.now()) / 60000)) : 0;
      $bar.style.position = "static";
      $bar.innerHTML = `<div class="done-box"><div class="emoji">🎉</div><h2>Done for now</h2>
        <p>${nxt && mins < 24 * 60 ? `A learning card comes back in about ${mins} minute${mins === 1 ? "" : "s"}. Keep this open and it will appear.` : "You've finished everything due today. Come back tomorrow."}</p>
        <div class="stack"><button class="btn primary" data-nav="${backTo}">Back to deck</button>
        <button class="btn" data-nav="/practice/${id}${qs({ tag, n: 20 })}">Practice 20 more cards</button></div></div>`;
      bindNav($bar);
      if (nxt && mins < 60) waitTimer = setTimeout(refresh, Math.max(5000, nxt * 1000 - Date.now() + 1000));
      return;
    }
    $wrap.style.display = "";
    $bar.style.position = "";
    $path.textContent = card.deck.split("::").join(" › ");
    renderCard($host, flipped ? card.back : card.front, card.css);
    if (!flipped) {
      $wrap.scrollTop = 0;
      $bar.innerHTML = `<button class="btn primary" id="show" style="min-height:64px">Show answer</button>`;
      $bar.querySelector("#show").onclick = flip;
    } else {
      const ans = $host.shadowRoot.getElementById("answer");
      if (ans && $wrap.scrollHeight > $wrap.clientHeight) $wrap.scrollTop = Math.max(0, ans.offsetTop - 40);
      const iv = card.intervals;
      $bar.innerHTML = `<div class="grades">
        <button class="grade g1" data-r="1">Again<small>${iv[1]}</small></button>
        <button class="grade g2" data-r="2">Hard<small>${iv[2]}</small></button>
        <button class="grade g3" data-r="3">Good<small>${iv[3]}</small></button>
        <button class="grade g4" data-r="4">Easy<small>${iv[4]}</small></button></div>`;
      $bar.querySelectorAll("[data-r]").forEach((b) => b.onclick = () => answer(+b.dataset.r));
    }
  }

  function flip() { if (state.card && !flipped) { flipped = true; draw(); } }

  async function answer(r) {
    if (busy || !state.card || !flipped) return;
    busy = true;
    try {
      state = await api("answer", { body: { card_id: state.card.id, rating: r, elapsed_ms: Date.now() - shownAt, deck: id, tag } });
      flipped = false; shownAt = Date.now(); draw();
    } catch (e) { toast(e.message); } finally { busy = false; }
  }

  async function refresh() {
    try { state = await api("next" + qs({ deck: id, tag })); flipped = false; shownAt = Date.now(); draw(); } catch (e) { toast(e.message); }
  }

  $app.querySelector("#undo").onclick = async () => {
    if (busy) return; busy = true;
    try { state = await api("undo", { body: { deck: id, tag } }); flipped = false; shownAt = Date.now(); draw(); toast("Undone"); }
    catch (e) { toast(e.message); } finally { busy = false; }
  };
  $wrap.addEventListener("click", (e) => { if (!e.composedPath().some((el) => el.tagName === "A" || el.tagName === "AUDIO")) flip(); });

  const onKey = (e) => {
    if (e.target.tagName === "INPUT") return;
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); flipped ? answer(3) : flip(); }
    else if (["1", "2", "3", "4"].includes(e.key)) answer(+e.key);
    else if (e.key === "z" && (e.metaKey || e.ctrlKey)) $app.querySelector("#undo").click();
  };
  const onVisible = () => { if (document.visibilityState === "visible" && !flipped) refresh(); };
  document.addEventListener("keydown", onKey);
  document.addEventListener("visibilitychange", onVisible);
  cleanup = () => { clearTimeout(waitTimer); document.removeEventListener("keydown", onKey); document.removeEventListener("visibilitychange", onVisible); };
  draw();
}

// ------------------------------------------------------------ practice (quiz, no scheduling)

async function practiceView(id, params) {
  const { cards } = await api("practice" + qs({ deck: id, tag: params.tag, limit: params.n || 20, only: params.only }));
  const backTo = `/deck/${id}`;
  if (!cards.length) {
    $app.innerHTML = `<div class="screen">${topbar({ title: "Practice", back: backTo })}<div class="empty"><h2>No cards to practice</h2><p>${params.only === "struggling" ? "You haven't forgotten any cards in this deck yet." : "This deck has no active cards."}</p></div></div>`;
    bindNav($app); return;
  }
  let queue = cards.map((c) => ({ ...c, misses: 0 }));
  const total = queue.length;
  let done = 0, firstTry = 0, flipped = false;
  const missedIds = new Set();

  $app.innerHTML = `<div class="screen study">
    <div class="topbar"><button class="icon-btn" data-nav="${backTo}" aria-label="Close">${ICON.close}</button>
      <div class="study-counts" id="prog"></div><span style="width:44px"></span></div>
    <div class="deck-path" id="path"></div>
    <div class="card-wrap" id="wrap"><div class="card-host" id="host"></div></div>
    <div class="answer-bar" id="bar"></div></div>`;
  bindNav($app);
  const $host = $app.querySelector("#host"), $bar = $app.querySelector("#bar"), $wrap = $app.querySelector("#wrap"),
    $prog = $app.querySelector("#prog"), $path = $app.querySelector("#path");

  function draw() {
    $prog.innerHTML = `<span>${done} / ${total}</span>`;
    const card = queue[0];
    if (!card) {
      $wrap.style.display = "none"; $path.textContent = "";
      const pct = Math.round(100 * firstTry / total);
      $bar.style.position = "static";
      $bar.innerHTML = `<div class="done-box"><div class="emoji">${pct >= 80 ? "🏆" : pct >= 68 ? "✅" : "📚"}</div>
        <h2>${pct}% right first time</h2><p>${firstTry} of ${total} cards.${/salesforce/i.test(cards[0].deck) ? " The exam pass mark is 68%." : ""}${missedIds.size ? ` You missed ${missedIds.size}.` : ""}</p>
        <div class="stack"><button class="btn primary" id="again">New random set</button>
        <button class="btn" data-nav="${backTo}">Back to deck</button></div></div>`;
      bindNav($bar);
      $bar.querySelector("#again").onclick = () => practiceView(id, params);
      return;
    }
    $wrap.style.display = ""; $bar.style.position = "";
    $path.textContent = card.deck.split("::").join(" › ") + (card.misses ? " · retry" : "");
    renderCard($host, flipped ? card.back : card.front, card.css);
    if (!flipped) {
      $wrap.scrollTop = 0;
      $bar.innerHTML = `<button class="btn primary" id="show" style="min-height:64px">Show answer</button>`;
      $bar.querySelector("#show").onclick = flip;
    } else {
      const ans = $host.shadowRoot.getElementById("answer");
      if (ans && $wrap.scrollHeight > $wrap.clientHeight) $wrap.scrollTop = Math.max(0, ans.offsetTop - 40);
      $bar.innerHTML = `<div class="grades two"><button class="grade g1" data-ok="0">Missed it</button><button class="grade g3" data-ok="1">Got it</button></div>`;
      $bar.querySelectorAll("[data-ok]").forEach((b) => b.onclick = () => mark(b.dataset.ok === "1"));
    }
  }
  function flip() { if (queue[0] && !flipped) { flipped = true; draw(); } }
  function mark(ok) {
    const card = queue.shift();
    if (ok) { done++; if (!card.misses) firstTry++; }
    else { card.misses++; missedIds.add(card.id); queue.splice(Math.min(queue.length, 3 + Math.floor(Math.random() * 3)), 0, card); }
    flipped = false; draw();
  }
  $wrap.addEventListener("click", flip);
  const onKey = (e) => {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); flipped ? mark(true) : flip(); }
    else if (flipped && e.key === "1") mark(false);
    else if (flipped && (e.key === "2" || e.key === "3")) mark(true);
  };
  document.addEventListener("keydown", onKey);
  cleanup = () => document.removeEventListener("keydown", onKey);
  draw();
}

// ------------------------------------------------------------ browse

async function browseView(_, params) {
  const { decks } = await api("decks");
  let q = params.q || "", st = params.state || "", deck = params.deck || "", offset = 0, items = [], total = 0;
  const filters = [["", "All"], ["due", "Due"], ["new", "New"], ["learning", "Learning"], ["review", "Review"], ["struggling", "Forgotten 2+ times"], ["suspended", "Suspended"]];
  $app.innerHTML = `<div class="screen">
    ${topbar({ title: "Browse cards", back: "/" })}
    <div class="search">
      <input class="input" id="q" type="search" placeholder="Search card text" value="${esc(q)}" autocomplete="off">
      <select class="input" id="deck"><option value="">All decks</option>${decks.map((d) => `<option value="${d.id}" ${String(d.id) === deck ? "selected" : ""}>${esc(d.name.split("::").join(" › "))}</option>`).join("")}</select>
      <div class="filters">${filters.map(([k, l]) => `<button class="chip ${k === st ? "on" : ""}" data-st="${k}">${l}</button>`).join("")}</div>
      <div class="muted" id="total" style="font-size:13px"></div>
    </div>
    <div class="list" id="list"></div>
    <div class="spacer"></div>
    <button class="btn" id="more" style="display:none">Load more</button>
  </div>`;
  bindNav($app);
  const $list = $app.querySelector("#list"), $more = $app.querySelector("#more"), $total = $app.querySelector("#total");

  async function load(reset) {
    if (reset) { offset = 0; items = []; }
    const r = await api("cards" + qs({ q, state: st, deck, offset, limit: 60 }));
    total = r.total; items = items.concat(r.items); offset = items.length;
    $total.textContent = `${total} card${total === 1 ? "" : "s"}`;
    $list.style.display = items.length ? "" : "none";
    $list.innerHTML = items.map((c) => `<button class="row card-row" data-card="${c.id}">
      <div class="t">${c.suspended ? '<span class="badge">suspended</span>' : ""}${esc(c.text)}</div>
      <div class="m">${esc(leaf(c.deck))} · ${esc(c.due)}${c.state === "review" ? ` · every ${c.ivl}d` : ""}${c.lapses ? ` · forgotten ${c.lapses}×` : ""}</div></button>`).join("");
    $more.style.display = items.length < total ? "" : "none";
    $list.querySelectorAll("[data-card]").forEach((b) => b.onclick = () => cardSheet(+b.dataset.card, () => load(true)));
  }
  let t;
  $app.querySelector("#q").addEventListener("input", (e) => { q = e.target.value; clearTimeout(t); t = setTimeout(() => load(true), 250); });
  $app.querySelector("#deck").onchange = (e) => { deck = e.target.value; load(true); };
  $app.querySelectorAll("[data-st]").forEach((b) => b.onclick = () => {
    st = b.dataset.st; $app.querySelectorAll("[data-st]").forEach((x) => x.classList.toggle("on", x === b)); load(true);
  });
  $more.onclick = () => load(false);
  await load(true);
}

async function cardSheet(id, onChange) {
  const from = location.hash;
  const card = await api(`cards/${id}`);
  if (location.hash !== from) return;
  const el = document.createElement("div");
  el.className = "sheet-backdrop";
  el.innerHTML = `<div class="sheet" role="dialog" aria-label="Card">
    <h3>${esc(card.deck.split("::").join(" › "))}</h3>
    <div class="preview"><div id="ph"></div></div>
    <p class="muted" style="font-size:13px">Tags: ${card.tags.length ? card.tags.map(esc).join(", ") : "none"}</p>
    <div class="stack">
      <button class="btn" data-a="suspend">Suspend (hide from study)</button>
      <button class="btn" data-a="unsuspend">Unsuspend</button>
      <button class="btn" data-a="forget">Reset to new</button>
      <button class="btn primary" data-a="close">Close</button>
    </div></div>`;
  document.body.appendChild(el);
  renderCard(el.querySelector("#ph"), card.back, card.css);
  const close = () => el.remove();
  el.addEventListener("click", (e) => { if (e.target === el) close(); });
  el.querySelectorAll("[data-a]").forEach((b) => b.onclick = async () => {
    const a = b.dataset.a;
    if (a === "close") return close();
    if (a === "forget" && !confirm("Reset this card's progress so it shows up as new again?")) return;
    try { await api(`cards/${id}`, { body: { action: a } }); toast({ suspend: "Suspended", unsuspend: "Unsuspended", forget: "Reset to new" }[a]); close(); onChange && onChange(); }
    catch (e) { toast(e.message); }
  });
}

// ------------------------------------------------------------ stats

async function statsView(_, params) {
  const { decks } = await api("decks");
  const deck = params.deck || "";
  const s = await api("stats" + qs({ deck }));
  const bars = (arr, labels) => {
    const max = Math.max(1, ...arr);
    return `<div class="bars">${arr.map((v, i) => `<div class="bar"><em>${v || ""}</em><i style="height:${(v / max) * 100}%"></i><u>${labels[i]}</u></div>`).join("")}</div>`;
  };
  const fLabels = s.forecast.map((_, i) => (i === 0 ? "T" : i % 2 === 0 ? `+${i}` : ""));
  const hLabels = s.history.map((_, i) => (i === 13 ? "T" : (13 - i) % 2 === 0 ? `-${13 - i}` : ""));
  // With a deck picked, show its subdecks (or itself when it has none); otherwise every deck.
  const picked = decks.find((x) => String(x.id) === deck);
  let rows = picked ? s.decks.filter((d) => d.name.startsWith(picked.name + "::")) : s.decks;
  if (picked && !rows.length) rows = s.decks.filter((d) => d.id === picked.id);
  rows = rows.filter((d) => d.total);
  const colors = { new: "var(--new)", learning: "var(--learn)", young: "#7fc8a0", mature: "var(--review)" };
  $app.innerHTML = `<div class="screen">
    ${topbar({ title: "Statistics", back: "/" })}
    <select class="input" id="deck"><option value="">All decks</option>${decks.map((d) => `<option value="${d.id}" ${String(d.id) === deck ? "selected" : ""}>${esc(d.name.split("::").join(" › "))}</option>`).join("")}</select>
    <div class="spacer"></div>
    <div class="tiles">
      <div class="tile"><b>${s.today.reviews}</b><span>Answers today${s.today.reviews ? ` · ${Math.round(100 * s.today.correct / s.today.reviews)}% right` : ""}</span></div>
      <div class="tile"><b>${s.today.minutes}</b><span>Minutes today</span></div>
      <div class="tile"><b>${s.retention_30d === null ? "–" : s.retention_30d + "%"}</b><span>Review recall, 30 days</span></div>
      <div class="tile"><b>${s.streak}</b><span>Day streak</span></div>
    </div>
    <div class="section-title">Due in the next 14 days</div>
    <div class="panel">${bars(s.forecast, fLabels)}</div>
    <div class="section-title">Answers in the last 14 days</div>
    <div class="panel">${bars(s.history, hLabels)}</div>
    <div class="section-title">Progress by deck</div>
    <div class="key">${Object.entries(colors).map(([k, c]) => `<span><i style="background:${c}"></i>${k === "young" ? "Young (<21d)" : k === "mature" ? "Mature (21d+)" : k[0].toUpperCase() + k.slice(1)}</span>`).join("")}</div>
    <div class="list">${rows.map((d) => {
      const seen = d.total - d.new;
      return `<div class="deck-stat"><div class="top"><span>${esc(leaf(d.name))}</span><span>${seen}/${d.total} seen</span></div>
        <div class="stack-bar">${["mature", "young", "learning", "new"].map((k) => `<span style="width:${(100 * d[k]) / d.total}%;background:${colors[k]}"></span>`).join("")}</div></div>`;
    }).join("") || '<div class="empty">No cards yet</div>'}</div>
    ${s.struggling ? `<div class="spacer"></div><button class="btn" data-nav="/browse?state=struggling${deck ? "&deck=" + deck : ""}">${s.struggling} card${s.struggling === 1 ? "" : "s"} forgotten 3+ times</button>` : ""}
  </div>`;
  bindNav($app);
  $app.querySelector("#deck").onchange = (e) => { location.hash = "/stats" + qs({ deck: e.target.value }); };
}

// ------------------------------------------------------------ settings & import

async function settingsView() {
  const s = await api("settings");
  const secure = window.isSecureContext;
  $app.innerHTML = `<div class="screen">
    ${topbar({ title: "Settings", back: "/" })}
    <div class="section-title">Import decks</div>
    <div class="panel">
      <div class="field"><label for="file">Anki .apkg or CSV / TXT files</label>
        <input class="input" id="file" type="file" accept=".apkg,.csv,.txt,.tsv" multiple></div>
      <button class="btn primary" id="import">Import</button>
      <p class="help">Re-importing a deck you already have updates the card text and keeps your progress.</p>
    </div>

    <div class="section-title">Daily limits</div>
    <div class="panel">
      <div class="field"><label for="new_per_day">New cards per day</label><input class="input" id="new_per_day" type="number" inputmode="numeric" min="0" value="${s.new_per_day}"></div>
      <div class="field"><label for="max_reviews">Maximum reviews per day</label><input class="input" id="max_reviews" type="number" inputmode="numeric" min="0" value="${s.max_reviews}"></div>
      <div class="field"><label for="new_order">Order of new cards</label>
        <select class="input" id="new_order">
          <option value="interleave" ${s.new_order === "interleave" ? "selected" : ""}>Mix subdecks (one from each in turn)</option>
          <option value="sequential" ${s.new_order === "sequential" ? "selected" : ""}>In deck order</option>
          <option value="random" ${s.new_order === "random" ? "selected" : ""}>Random</option>
        </select></div>
      <div class="field"><label for="rollover_hour">New day starts at (hour)</label><input class="input" id="rollover_hour" type="number" inputmode="numeric" min="0" max="23" value="${s.rollover_hour}"></div>
    </div>

    <div class="section-title">Scheduling</div>
    <div class="panel">
      <div class="field"><label for="learn_steps">Learning steps (minutes)</label><input class="input" id="learn_steps" value="${esc(s.learn_steps)}"><small>Each new card is shown again after these gaps before it graduates.</small></div>
      <div class="field"><label for="relearn_steps">Relearning steps (minutes)</label><input class="input" id="relearn_steps" value="${esc(s.relearn_steps)}"></div>
      <div class="field"><label for="graduating_ivl">Graduating interval (days)</label><input class="input" id="graduating_ivl" type="number" inputmode="numeric" min="1" value="${s.graduating_ivl}"></div>
      <div class="field"><label for="easy_ivl">Easy interval (days)</label><input class="input" id="easy_ivl" type="number" inputmode="numeric" min="1" value="${s.easy_ivl}"></div>
      <div class="field"><label for="max_ivl">Maximum interval (days)</label><input class="input" id="max_ivl" type="number" inputmode="numeric" min="1" value="${s.max_ivl}"><small>Exam in a few weeks? Setting this to around 7 keeps every card in rotation.</small></div>
      <button class="btn primary" id="save">Save settings</button>
    </div>

    <div class="section-title">Appearance</div>
    <div class="panel">
      <select class="input" id="theme">
        ${["auto", "light", "dark"].map((t) => `<option value="${t}" ${store.get("theme", "auto") === t ? "selected" : ""}>${t === "auto" ? "Match iPhone" : t[0].toUpperCase() + t.slice(1)}</option>`).join("")}
      </select>
    </div>

    <div class="section-title">Backup</div>
    <div class="panel"><a class="btn" style="display:grid;place-items:center;text-decoration:none" href="/api/backup" download>Download a backup of all progress</a></div>

    <div class="section-title">Put Kardo on your Home Screen</div>
    <div class="panel help"><ol>
      <li>Open this page in Safari.</li><li>Tap the Share button, then <b>Add to Home Screen</b>.</li><li>Open Kardo from the new icon. It runs full screen like an app.</li>
    </ol>${secure ? "" : "<p>You're on plain http. That works fine; switch to the https Tailscale address if you want the app to open instantly when the connection is slow.</p>"}</div>
    <div class="spacer"></div>
  </div>`;
  bindNav($app);

  $app.querySelector("#import").onclick = async () => {
    const files = [...$app.querySelector("#file").files];
    if (!files.length) return toast("Choose a file first");
    const btn = $app.querySelector("#import");
    btn.disabled = true;
    try {
      for (const f of files) {
        btn.textContent = `Importing ${f.name}…`;
        const r = await api("import" + qs({ filename: f.name }), { method: "POST", body: f, headers: { "Content-Type": "application/octet-stream" } });
        toast(`${f.name}: ${r.added} added, ${r.updated} updated${r.skipped ? `, ${r.skipped} skipped` : ""}`);
      }
      setTimeout(() => { location.hash = "/"; }, 1200);
    } catch (e) { toast(e.message); } finally { btn.disabled = false; btn.textContent = "Import"; }
  };
  $app.querySelector("#save").onclick = async () => {
    const body = {};
    ["new_per_day", "max_reviews", "rollover_hour", "graduating_ivl", "easy_ivl", "max_ivl"].forEach((k) => { body[k] = Number($app.querySelector("#" + k).value); });
    ["learn_steps", "relearn_steps", "new_order"].forEach((k) => { body[k] = $app.querySelector("#" + k).value; });
    try { await api("settings", { body }); toast("Saved"); } catch (e) { toast(e.message); }
  };
  ["new_per_day", "max_reviews", "new_order", "rollover_hour"].forEach((k) => $app.querySelector("#" + k).addEventListener("change", () => $app.querySelector("#save").click()));
  $app.querySelector("#theme").onchange = (e) => { store.set("theme", e.target.value); applyTheme(); };
}

// ------------------------------------------------------------ boot

if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { if (store.get("theme", "auto") === "auto") route(); });
route();
