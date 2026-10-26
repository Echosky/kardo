"use strict";
/* Kardo SQL Lab: exercise list, exercise screen with checker, free sandbox and a table browser.
   Loaded before app.js; uses its helpers (api, esc, topbar, bindNav, toast, store, ICON) at call time. */

const LAB_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5.5" rx="7.5" ry="2.8"/><path d="M4.5 5.5v6c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-6"/><path d="M4.5 11.5v6c0 1.5 3.4 2.8 7.5 2.8s7.5-1.3 7.5-2.8v-6"/></svg>';

const SQL_KEYS = ["SELECT", "FROM", "WHERE", "JOIN", "LEFT JOIN", "ON", "GROUP BY", "ORDER BY", "HAVING", "AS", "AND", "OR",
  "NOT", "IN", "IS NULL", "DISTINCT", "COUNT(*)", "SUM(", "AVG(", "MIN(", "MAX(", "ROUND(", "COALESCE(", "CASE WHEN", "THEN", "ELSE", "END",
  "WITH", "RECURSIVE", "UNION ALL", "OVER (", "PARTITION BY", "ROW_NUMBER()", "LAG(", "LEAD(", "DESC", "LIMIT", "*", "=", "<>", "(", ")", ",", "'", "||", ";"];

const SANDBOX_EXAMPLES = [
  ["Tables", "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') ORDER BY name;"],
  ["Peek at orders", "SELECT * FROM orders ORDER BY order_date DESC LIMIT 20;"],
  ["Revenue by month", "SELECT strftime('%Y-%m', o.order_date) AS month,\n       ROUND(SUM(oi.quantity * oi.unit_price * (1 - oi.discount)), 2) AS revenue\nFROM orders o\nJOIN order_items oi ON oi.order_id = o.order_id\nWHERE o.status IN ('completed', 'shipped')\nGROUP BY month\nORDER BY month;"],
  ["Date spine", "WITH RECURSIVE spine(day) AS (\n  SELECT '2025-12-01'\n  UNION ALL\n  SELECT date(day, '+1 day') FROM spine WHERE day < '2025-12-31'\n)\nSELECT * FROM spine;"],
  ["Org chart", "WITH RECURSIVE tree AS (\n  SELECT employee_id, full_name, 0 AS depth, full_name AS path\n  FROM employees WHERE manager_id IS NULL\n  UNION ALL\n  SELECT e.employee_id, e.full_name, t.depth + 1, t.path || ' > ' || e.full_name\n  FROM employees e JOIN tree t ON e.manager_id = t.employee_id\n)\nSELECT depth, path FROM tree ORDER BY path;"],
  ["Top 3 per category", "SELECT * FROM (\n  SELECT category_id, name, unit_price,\n         ROW_NUMBER() OVER (PARTITION BY category_id ORDER BY unit_price DESC) AS rn\n  FROM products\n) WHERE rn <= 3;"],
];

function labText(s) {
  // Prompt text: escape, then `code` spans and line breaks.
  return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\n/g, "<br>");
}

function labTable(r) {
  if (!r.columns.length) return `<div class="lab-note">${esc((r.notes || []).join(" · ") || "Done. No rows returned.")}</div>`;
  const cell = (v) => v === null ? '<td class="null">NULL</td>' : `<td class="${typeof v === "number" ? "num" : ""}">${esc(v)}</td>`;
  const meta = `${r.rows.length}${r.truncated ? "+" : ""} row${r.rows.length === 1 ? "" : "s"}${r.ms !== undefined && r.ms ? ` · ${r.ms} ms` : ""}${(r.notes || []).length ? " · " + esc(r.notes.join(" · ")) : ""}`;
  return `<div class="lab-meta">${meta}${r.truncated ? " (showing the first 500)" : ""}</div>
    <div class="lab-grid"><table><thead><tr>${r.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${r.rows.map((row) => `<tr>${row.map(cell).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function labEditor(host, { value, onChange, onRun }) {
  host.innerHTML = `<div class="lab-keys" role="toolbar" aria-label="Insert SQL">${SQL_KEYS.map((k) => `<button class="chip" data-k="${esc(k)}">${esc(k)}</button>`).join("")}</div>
    <textarea class="lab-sql" spellcheck="false" autocapitalize="off" autocomplete="off" autocorrect="off" wrap="off" placeholder="Write SQL here"></textarea>`;
  const ta = host.querySelector("textarea");
  ta.value = value || "";
  const grow = () => { ta.style.height = "auto"; ta.style.height = Math.max(150, Math.min(ta.scrollHeight + 4, window.innerHeight * 0.6)) + "px"; };
  const insert = (text) => {
    const s = ta.selectionStart ?? ta.value.length, e = ta.selectionEnd ?? s;
    const before = ta.value.slice(0, s), after = ta.value.slice(e);
    const word = /^[A-Za-z_*]/.test(text) && before && !/[\s(]$/.test(before) ? " " : "";
    const tail = /[A-Z)*]$/.test(text) && !text.endsWith("(") ? " " : "";
    const ins = word + text + tail;
    ta.value = before + ins + after;
    ta.selectionStart = ta.selectionEnd = s + ins.length;
    grow(); onChange && onChange(ta.value);
  };
  host.querySelectorAll("[data-k]").forEach((b) => {
    // pointerdown + preventDefault keeps the keyboard open on iPhone
    b.addEventListener("pointerdown", (e) => { e.preventDefault(); });
    b.addEventListener("click", (e) => { e.preventDefault(); insert(b.dataset.k); ta.focus(); });
  });
  ta.addEventListener("input", () => { grow(); onChange && onChange(ta.value); });
  ta.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); onRun && onRun(); }
    else if (e.key === "Tab") { e.preventDefault(); insert("  "); }
  });
  setTimeout(grow, 0);
  return { get value() { return ta.value; }, set value(v) { ta.value = v; grow(); onChange && onChange(v); }, insert, focus: () => ta.focus() };
}

async function schemaSheet(onPick) {
  const { tables } = await api("lab/schema");
  const el = document.createElement("div");
  el.className = "sheet-backdrop";
  el.innerHTML = `<div class="sheet lab-schema" role="dialog" aria-label="Tables">
    <h3>Practice database: Shopwise</h3>
    <p class="muted" style="font-size:13px;margin:0 0 10px">Tap a table or column name to insert it into your query.</p>
    ${tables.map((t) => `<details><summary><b data-ins="${esc(t.name)}">${esc(t.name)}</b> <span class="muted">${t.rows} rows</span></summary>
      <ul>${t.columns.map((c) => `<li><button class="link" data-ins="${esc(c.name)}">${esc(c.name)}</button> <span class="muted">${esc(c.type.toLowerCase())}${c.pk ? " · primary key" : ""}${c.ref ? " → " + esc(c.ref) : ""}</span></li>`).join("")}</ul></details>`).join("")}
    <div class="spacer"></div><button class="btn primary" data-close>Close</button></div>`;
  document.body.appendChild(el);
  const close = () => el.remove();
  el.addEventListener("click", (e) => { if (e.target === el || e.target.hasAttribute("data-close")) close(); });
  el.querySelectorAll("[data-ins]").forEach((b) => b.addEventListener("click", (e) => {
    if (!onPick) return;
    e.preventDefault(); e.stopPropagation(); onPick(b.dataset.ins); toast(`Inserted ${b.dataset.ins}`);
  }));
}

function textSheet(title, html, actions = "") {
  const el = document.createElement("div");
  el.className = "sheet-backdrop";
  el.innerHTML = `<div class="sheet" role="dialog" aria-label="${esc(title)}"><h3>${esc(title)}</h3>${html}
    <div class="spacer"></div><div class="stack">${actions}<button class="btn primary" data-close>Close</button></div></div>`;
  document.body.appendChild(el);
  el.addEventListener("click", (e) => { if (e.target === el || e.target.hasAttribute("data-close")) el.remove(); });
  return el;
}

// ------------------------------------------------------------ lab home

async function labView(sub, params) {
  if (sub === "ex") return labExerciseView(location.hash.split("/")[3]);
  if (sub === "sandbox") return labSandboxView();
  const o = await api("lab");
  const open = new Set(store.get("lab.open", []));
  const next = o.tracks.flatMap((t) => t.exercises).find((x) => !x.solved);
  const pct = o.total ? Math.round(100 * o.solved / o.total) : 0;
  $app.innerHTML = `<div class="screen">
    ${topbar({ title: "SQL Lab", back: "/" })}
    <div class="overview">
      <h2>${o.solved} of ${o.total} exercises solved</h2>
      <div class="lab-progress"><span style="width:${pct}%"></span></div>
      <div class="stack" style="margin-top:14px">
        ${next ? `<button class="btn primary" data-nav="/lab/ex/${next.id}">${o.solved ? "Continue" : "Start"}: ${esc(next.title)}</button>` : `<div class="lab-ok">Every exercise solved. Try them again from memory, or explore in the sandbox.</div>`}
        <div class="lab-two"><button class="btn" data-nav="/lab/sandbox">Sandbox</button><button class="btn" id="tables">Tables</button></div>
      </div>
      <p class="muted" style="font-size:13px;margin:12px 0 0">Each query runs on a fresh copy of the practice database (SQLite ${esc(o.sqlite)}), so you can insert, update or drop anything.</p>
    </div>
    ${o.tracks.map((t) => {
      const done = t.exercises.filter((x) => x.solved).length;
      return `<details class="lab-track" data-track="${esc(t.name)}" ${open.has(t.name) ? "open" : ""}>
        <summary><span>${esc(t.name.replace(/^\d+ /, ""))}</span><span class="muted">${done}/${t.exercises.length}</span></summary>
        <div class="list">${t.exercises.map((x) => `<button class="row" data-nav="/lab/ex/${x.id}">
          <span class="lab-mark ${x.solved ? "ok" : x.tried ? "tried" : ""}">${x.solved ? "✓" : x.tried ? "•" : ""}</span>
          <span class="name">${esc(x.title)}</span></button>`).join("")}</div></details>`;
    }).join("")}
    <div class="spacer"></div>
    <button class="btn danger" id="reset">Reset lab progress</button>
  </div>`;
  bindNav($app);
  $app.querySelectorAll(".lab-track").forEach((d) => d.addEventListener("toggle", () => {
    d.open ? open.add(d.dataset.track) : open.delete(d.dataset.track);
    store.set("lab.open", [...open]);
  }));
  $app.querySelector("#tables").onclick = () => schemaSheet(null);
  $app.querySelector("#reset").onclick = async () => {
    if (!confirm("Clear every solved mark and saved answer in the SQL Lab?")) return;
    await api("lab/reset", { body: {} });
    Object.keys(localStorage).filter((k) => k.startsWith("kardo.lab.draft.")).forEach((k) => localStorage.removeItem(k));
    labView();
  };
}

// ------------------------------------------------------------ exercise

async function labExerciseView(id) {
  const ex = await api(`lab/ex/${encodeURIComponent(id)}`);
  const draftKey = "lab.draft." + ex.id;
  let showHint = false;
  $app.innerHTML = `<div class="screen lab">
    ${topbar({ title: `${ex.track.replace(/^\d+ /, "")} · ${ex.number}/${ex.count}`, back: "/lab", actions: `
      <button class="icon-btn" id="tables" aria-label="Tables">${LAB_ICON}</button>` })}
    <div class="panel lab-prompt">
      <h2>${ex.solved ? '<span class="lab-mark ok">✓</span> ' : ""}${esc(ex.title)}</h2>
      <div>${labText(ex.prompt)}</div>
      ${ex.setup ? `<details class="lab-setup"><summary>Runs first for this exercise</summary><pre>${esc(ex.setup)}</pre></details>` : ""}
      <div class="lab-expect">Expected: ${ex.expected_columns.length} column${ex.expected_columns.length === 1 ? "" : "s"} (${esc(ex.expected_columns.join(", "))}), ${ex.expected_rows} row${ex.expected_rows === 1 ? "" : "s"}${ex.ordered ? ", in a specific order" : ", any order"}${ex.has_check ? ". Checked with a query run after yours" : ""}.</div>
      <div id="hint" class="lab-hint" hidden>${labText(ex.hint || "No hint for this one. Look at the expected columns, and try the Tables button.")}</div>
    </div>
    <div id="editor" class="lab-editor"></div>
    <div class="lab-actions">
      <button class="btn primary" id="run">Run and check</button>
      <button class="btn" id="explain">Explain</button>
    </div>
    <div id="verdict"></div>
    <div id="out"></div>
    <div class="lab-more">
      <button class="chip" id="hintBtn">Hint</button>
      <button class="chip" id="expBtn">Expected result</button>
      <button class="chip" id="solBtn">Solution</button>
      <button class="chip" id="clearBtn">Clear</button>
    </div>
    <div class="lab-nav">
      <button class="btn" ${ex.prev ? `data-nav="/lab/ex/${ex.prev}"` : "disabled"}>Previous</button>
      <button class="btn" ${ex.next ? `data-nav="/lab/ex/${ex.next}"` : "disabled"}>Next</button>
    </div>
  </div>`;
  bindNav($app);
  const ed = labEditor($app.querySelector("#editor"), {
    value: store.get(draftKey, null) ?? ex.last_sql ?? "",
    onChange: (v) => store.set(draftKey, v),
    onRun: () => run(false),
  });
  const $out = $app.querySelector("#out"), $verdict = $app.querySelector("#verdict");
  const $run = $app.querySelector("#run"), $explain = $app.querySelector("#explain");

  async function run(explain) {
    if (!ed.value.trim()) return toast("Write a query first");
    $run.disabled = $explain.disabled = true;
    $verdict.innerHTML = ""; $out.innerHTML = '<div class="lab-note">Running…</div>';
    try {
      const r = await api("lab/run", { body: { sql: ed.value, ex: ex.id, explain } });
      if (r.verdict) {
        const ok = r.verdict.ok;
        $verdict.innerHTML = `<div class="lab-verdict ${ok ? "ok" : "bad"}">${esc(r.verdict.message)}${ok && ex.next ? ' <button class="btn primary" id="go">Next exercise</button>' : ""}</div>`;
        const go = $verdict.querySelector("#go");
        if (go) go.onclick = () => { location.hash = `/lab/ex/${ex.next}`; };
        if (ok && !ex.solved) { ex.solved = true; $app.querySelector(".lab-prompt h2").innerHTML = `<span class="lab-mark ok">✓</span> ${esc(ex.title)}`; }
      }
      $out.innerHTML = labTable(r);
    } catch (e) {
      $out.innerHTML = `<div class="lab-error">${esc(e.message)}</div>`;
    } finally {
      $run.disabled = $explain.disabled = false;
      $verdict.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }
  $run.onclick = () => run(false);
  $explain.onclick = () => run(true);
  $app.querySelector("#tables").onclick = () => schemaSheet((name) => ed.insert(name));
  $app.querySelector("#hintBtn").onclick = () => { showHint = !showHint; $app.querySelector("#hint").hidden = !showHint; };
  $app.querySelector("#clearBtn").onclick = () => { if (!ed.value || confirm("Clear the editor?")) { ed.value = ""; ed.focus(); } };
  $app.querySelector("#expBtn").onclick = async () => {
    try { const r = await api(`lab/ex/${ex.id}/expected`); textSheet("Expected result", labTable(r)); } catch (e) { toast(e.message); }
  };
  $app.querySelector("#solBtn").onclick = async () => {
    if (!ex.solved && !confirm("Show the model answer? Try the hint and the expected result first.")) return;
    try {
      const { solution } = await api(`lab/ex/${ex.id}/solution`);
      const el = textSheet("One possible answer", `<pre class="lab-solution">${esc(solution)}</pre><p class="muted" style="font-size:13px">Other queries that return the same rows are just as correct.</p>`,
        '<button class="btn" id="use">Copy into the editor</button>');
      el.querySelector("#use").onclick = () => { ed.value = solution; el.remove(); };
    } catch (e) { toast(e.message); }
  };
}

// ------------------------------------------------------------ sandbox

async function labSandboxView() {
  $app.innerHTML = `<div class="screen lab">
    ${topbar({ title: "SQL sandbox", back: "/lab", actions: `<button class="icon-btn" id="tables" aria-label="Tables">${LAB_ICON}</button>` })}
    <div class="lab-examples filters">${SANDBOX_EXAMPLES.map(([n], i) => `<button class="chip" data-ex="${i}">${esc(n)}</button>`).join("")}</div>
    <div id="editor" class="lab-editor"></div>
    <div class="lab-actions"><button class="btn primary" id="run">Run</button><button class="btn" id="explain">Explain</button></div>
    <div id="out"></div>
    <p class="muted" style="font-size:13px">Every run starts from a fresh copy of the practice data. Separate statements with semicolons; the last result set is shown. Cmd/Ctrl+Enter runs on a keyboard.</p>
  </div>`;
  bindNav($app);
  const ed = labEditor($app.querySelector("#editor"), {
    value: store.get("lab.draft.sandbox", SANDBOX_EXAMPLES[1][1]),
    onChange: (v) => store.set("lab.draft.sandbox", v),
    onRun: () => run(false),
  });
  const $out = $app.querySelector("#out"), $run = $app.querySelector("#run"), $explain = $app.querySelector("#explain");
  async function run(explain) {
    if (!ed.value.trim()) return toast("Write a query first");
    $run.disabled = $explain.disabled = true;
    $out.innerHTML = '<div class="lab-note">Running…</div>';
    try { $out.innerHTML = labTable(await api("lab/run", { body: { sql: ed.value, explain } })); }
    catch (e) { $out.innerHTML = `<div class="lab-error">${esc(e.message)}</div>`; }
    finally { $run.disabled = $explain.disabled = false; }
  }
  $run.onclick = () => run(false);
  $explain.onclick = () => run(true);
  $app.querySelector("#tables").onclick = () => schemaSheet((name) => ed.insert(name));
  $app.querySelectorAll("[data-ex]").forEach((b) => b.onclick = () => {
    if (ed.value.trim() && ed.value !== SANDBOX_EXAMPLES.find(([, q]) => q === ed.value)?.[1] && !confirm("Replace what's in the editor?")) return;
    ed.value = SANDBOX_EXAMPLES[+b.dataset.ex][1];
  });
}
