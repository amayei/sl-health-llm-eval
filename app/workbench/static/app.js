"use strict";
const TOKEN = document.querySelector('meta[name="wb-token"]').content;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 1) => (x == null ? "n/a" : (x * 100).toFixed(d) + "%");
const pts = (x) => (x == null ? "n/a" : (x * 100).toFixed(1) + " pts");
const MC = ["var(--m1)", "var(--m2)", "var(--m3)", "var(--m4)", "var(--m5)"];
const S = { state: null, view: "overview", sel: null, run: null, job: null, timer: null, cond: "en", ex: null, focusItem: null };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.body ? "POST" : "GET",
    headers: { "X-Workbench-Token": TOKEN, "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
async function download(path, name) {
  const res = await fetch(path, { headers: { "X-Workbench-Token": TOKEN } });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await res.blob());
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/* ---------- shared helpers ---------- */
function marker(i, x, y, r = 6) {
  const c = MC[i % 5], f = `fill="${c}" stroke="var(--panel)" stroke-width="1.5"`;
  switch (i % 5) {
    case 0: return `<circle cx="${x}" cy="${y}" r="${r}" ${f}/>`;
    case 1: return `<rect x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" ${f}/>`;
    case 2: return `<path d="M${x} ${y - r - 1} L${x + r + 1} ${y} L${x} ${y + r + 1} L${x - r - 1} ${y} Z" ${f}/>`;
    case 3: return `<path d="M${x} ${y - r - 1} L${x + r + 1} ${y + r} L${x - r - 1} ${y + r} Z" ${f}/>`;
    default: return `<path d="M${x - r} ${y - 2} h${r - 2} v${-(r - 2)} h4 v${r - 2} h${r - 2} v4 h${-(r - 2)} v${r - 2} h-4 v${-(r - 2)} h${-(r - 2)} z" ${f}/>`;
  }
}
const legend = (names) => `<div class="legend">${names.map((n, i) => `<span class="k"><svg width="16" height="16" viewBox="-8 -8 16 16">${marker(i, 0, 0, 5)}</svg>${esc(n)}</span>`).join("")}</div>`;

function setBanner(run) {
  const b = $("#banner");
  if (!run) { b.hidden = true; return; }
  const drafts = run.meta.item_status_counts?.draft || 0;
  if (run.meta.mock) { b.className = "banner mock"; b.hidden = false; b.textContent = "SIMULATED RESULTS: this run used a mock model that answers at random. Not real evaluation data."; }
  else if (drafts > 0) { b.className = "banner draft"; b.hidden = false; b.textContent = `PROVISIONAL: ${drafts} items in this run were not approved when it ran. Do not cite these figures as final.`; }
  else b.hidden = true;
}

function ranked(en) {
  const names = Object.keys(en).sort((a, b) => en[b].accuracy - en[a].accuracy);
  const top = en[names[0]];
  const tied = names.filter((n) => en[n].ci_high >= top.ci_low);
  return { names, top: names[0], tied };
}

/* ---------- charts ---------- */
function leaderboard(en) {
  const { names } = ranked(en), order = Object.keys(en);
  const W = 600, rowH = 46, pad = { l: 150, r: 60, t: 28, b: 34 }, H = pad.t + pad.b + names.length * rowH;
  const x = (v) => pad.l + v * (W - pad.l - pad.r);
  let g = "";
  for (let t = 0; t <= 1.0001; t += 0.25) g += `<line class="g" x1="${x(t)}" x2="${x(t)}" y1="${pad.t - 8}" y2="${H - pad.b}"/><text class="m" x="${x(t)}" y="${H - 12}" text-anchor="middle">${Math.round(t * 100)}%</text>`;
  g += `<line x1="${x(.25)}" x2="${x(.25)}" y1="${pad.t - 8}" y2="${H - pad.b}" stroke="var(--mute)" stroke-dasharray="5 4"/><text x="${x(.25) + 4}" y="${pad.t - 12}" class="m">chance</text>`;
  names.forEach((n, i) => {
    const m = en[n], y = pad.t + i * rowH + rowH / 2, idx = order.indexOf(n);
    g += `<text x="${pad.l - 14}" y="${y + 4}" text-anchor="end" font-weight="600">${i + 1}. ${esc(n)}</text>`;
    g += `<line x1="${x(m.ci_low)}" x2="${x(m.ci_high)}" y1="${y}" y2="${y}" stroke="${MC[idx % 5]}" stroke-width="5" stroke-linecap="round" opacity=".35"/>`;
    g += marker(idx, x(m.accuracy), y, 7);
    g += `<text x="${x(m.ci_high) + 10}" y="${y + 4}" font-weight="700">${pct(m.accuracy)}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc("Models ranked by accuracy with 95% intervals: " + names.map((n) => `${n} ${pct(en[n].accuracy)}, interval ${pct(en[n].ci_low)} to ${pct(en[n].ci_high)}`).join("; "))}">${g}</svg>
  <div class="legend"><span>Marker: mean item accuracy. Band: 95% bootstrap interval over items. Dashed line: chance (25%).</span></div>`;
}

function radar(en) {
  const names = Object.keys(en);
  const domains = [...new Set(names.flatMap((n) => Object.keys(en[n].domain_accuracy || {})))].sort();
  if (domains.length < 3) return "<p class='lead'>Radar needs at least three domains.</p>";
  const S0 = 420, cx = S0 / 2, cy = S0 / 2 + 6, R = 150, N = domains.length;
  const pt = (i, v) => [cx + R * v * Math.sin((2 * Math.PI * i) / N), cy - R * v * Math.cos((2 * Math.PI * i) / N)];
  let g = "";
  [0.25, 0.5, 0.75, 1].forEach((r) => { g += `<polygon points="${domains.map((_, i) => pt(i, r).join(",")).join(" ")}" fill="none" stroke="var(--line)"/>`; });
  g += `<text class="m" x="${cx + 4}" y="${cy - R * .25 - 3}" font-size="10">25%</text><text class="m" x="${cx + 4}" y="${cy - R - 3}" font-size="10">100%</text>`;
  domains.forEach((d, i) => {
    const [x, y] = pt(i, 1.12), a = x < cx - 8 ? "end" : x > cx + 8 ? "start" : "middle";
    g += `<line x1="${cx}" y1="${cy}" x2="${pt(i, 1)[0]}" y2="${pt(i, 1)[1]}" stroke="var(--line)"/><text x="${x}" y="${y + 4}" text-anchor="${a}" font-size="13">${esc(d.length > 28 ? d.slice(0, 27) + "…" : d)}</text>`;
  });
  names.forEach((n, k) => {
    const v = domains.map((d) => en[n].domain_accuracy?.[d]?.accuracy ?? 0);
    g += `<polygon points="${v.map((a, i) => pt(i, a).join(",")).join(" ")}" fill="${MC[k % 5]}" fill-opacity=".10" stroke="${MC[k % 5]}" stroke-width="2"/>`;
    v.forEach((a, i) => { const [x, y] = pt(i, a); g += marker(k, x, y, 3.5); });
  });
  return `<svg viewBox="0 0 ${S0 + 240} ${S0 + 20}" role="img" aria-label="Accuracy by domain, one polygon per model" style="width:100%;display:block;margin:auto"><g transform="translate(120,0)">${g}</g></svg>${legend(names)}`;
}

function heat(en) {
  const names = Object.keys(en);
  const domains = [...new Set(names.flatMap((n) => Object.keys(en[n].domain_accuracy || {})))].sort();
  const cell = (d) => {
    if (!d) return "<td>n/a</td>";
    const a = d.accuracy;
    return `<td style="background:color-mix(in srgb,var(--brand) ${Math.round(8 + 70 * a)}%,var(--panel))" title="${d.n_items} items">${pct(a, 0)}</td>`;
  };
  return `<table class="heat"><thead><tr><th>Domain</th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>` +
    domains.map((d) => `<tr><td>${esc(d)} <small class="lead">(${en[names[0]].domain_accuracy?.[d]?.n_items ?? "?"} items)</small></td>${names.map((n) => cell(en[n].domain_accuracy?.[d])).join("")}</tr>`).join("") + `</tbody></table>`;
}

/* ---------- load run ---------- */
async function loadRun() {
  const st = S.state;
  if (!st.runs.length) return null;
  S.sel = S.sel && st.runs.some((r) => `${r.source}/${r.id}` === S.sel) ? S.sel : `${st.runs[0].source}/${st.runs[0].id}`;
  const [source, id] = S.sel.split("/");
  if (!S.run || S.run.source !== source || S.run.id !== id) { S.run = await api(`/api/run/${source}/${encodeURIComponent(id)}`); S.ex = null; }
  setBanner(S.run);
  return S.run;
}
function runbar() {
  const st = S.state, bar = $("#runbar");
  if (!st.runs.length || ["run", "items", "help"].includes(S.view)) { bar.innerHTML = ""; return; }
  bar.innerHTML = `<label for="runsel" class="sr">Run</label><select id="runsel">${st.runs.map((r) => `<option value="${esc(r.source)}/${esc(r.id)}" ${`${r.source}/${r.id}` === S.sel ? "selected" : ""}>${esc(r.id)} (${r.source}${r.mock ? ", simulated" : ""})</option>`).join("")}</select>
  <button class="btn sec" id="exp">Export report (HTML)</button><button class="btn sec" id="expcsv">Export data (CSV)</button>`;
  $("#runsel").onchange = (e) => { S.sel = e.target.value; render(); };
  $("#exp").onclick = () => { const [s, i] = S.sel.split("/"); download(`/api/export/${s}/${encodeURIComponent(i)}.html`, `report-${i}.html`); };
  $("#expcsv").onclick = () => { const [s, i] = S.sel.split("/"); download(`/api/export/${s}/${encodeURIComponent(i)}.csv`, `results-${i}.csv`); };
}
const EMPTY = `<div class="eyebrow">Welcome</div><h1>Test an AI model on public health questions</h1><p class="lead">Three steps. No technical setup needed to try it.</p>
<div class="steps"><div class="step"><b class="n">1</b><h3>Start a trial run</h3><p>Open New evaluation and tick "Simulated run". It uses made-up answers so you can look around safely.</p></div>
<div class="step"><b class="n">2</b><h3>Read the results</h3><p>The Overview, Compare models and Domains pages explain each chart in plain words.</p></div>
<div class="step"><b class="n">3</b><h3>Run it for real</h3><p>Add an API key for a model such as ChatGPT, Claude or Gemini and run the same questions.</p></div></div>
<button class="btn" onclick="go('run')">Start a trial run</button>`;

/* ---------- provenance ---------- */
function provenance(run) {
  const m = run.meta, rets = run.summary.model_returned || {};
  const returned = Object.entries(rets).map(([k, v]) => `${esc(k)}: ${esc(Array.isArray(v) ? v.join(", ") : v)}`).join("; ");
  return `<section class="card prov" style="margin-top:16px" aria-label="Provenance and reproducibility"><h2>Provenance and reproducibility</h2>
  <dl><dt>Run</dt><dd>${esc(run.id)} (${esc(run.source)})</dd><dt>Started (UTC)</dt><dd>${esc(m.started_utc || "unknown")}</dd>
  <dt>Harness version</dt><dd>${esc(m.harness_version)}</dd><dt>Code commit</dt><dd>${esc((m.git_commit || "not recorded").slice(0, 12))}</dd>
  <dt>Item bank fingerprint</dt><dd>${esc((m.dataset_sha256 || "").slice(0, 16))} (SHA-256, first 16 characters)</dd>
  <dt>Repetitions and seed</dt><dd>${esc(m.args?.reps ?? "?")} repetitions, seed ${esc(m.args?.seed ?? "?")}</dd>
  <dt>Models requested</dt><dd>${esc((m.models || []).map((x) => x.model).join(", "))}</dd>${returned ? `<dt>Models returned by provider</dt><dd>${returned}</dd>` : ""}
  <dt>Item status</dt><dd>${esc(Object.entries(m.item_status_counts || {}).map(([k, v]) => `${v} ${k}`).join(", "))}</dd></dl>
  <p>Anyone with the repository, the same item bank and this seed can repeat the analysis. Hosted models change over time, so answers may differ on a new run.</p></section>`;
}

/* ---------- about ---------- */
async function viewAbout() {
  setBanner(null);
  const st = S.state;
  $("#main").innerHTML = `<h1>About and provenance</h1><p class="lead">What this application is, which versions are running, and where your data is kept.</p>
  <section class="card prov"><h2>This installation</h2><dl><dt>Application</dt><dd>SL-Health-LLM-Eval Evaluation Workbench ${esc(st.app_version)} (pilot)</dd><dt>Evaluation harness</dt><dd>${esc(st.harness_version)}</dd>
  <dt>Item bank</dt><dd>${esc(Object.entries(st.item_status).map(([k, v]) => `${v} ${k}`).join(", "))}; ${st.n_krio} Krio items</dd><dt>Your runs are stored in</dt><dd>${esc(st.workspace)}</dd></dl></section>
  <section class="card prov" style="margin-top:16px"><h2>Author and licence</h2><p>Created by Alhassan Mayei. Code, protocol and data: github.com/amayei/sl-health-llm-eval. Released under the repository licence. Pilot software provided as is, without warranty, not for clinical decisions.</p></section>
  <section class="card prov" style="margin-top:16px"><h2>Security and privacy</h2><p>The application listens on this computer only. API keys are kept in memory for the run and are never saved. Questions are sent only to the model provider you select.</p></section>`;
}

/* ---------- 01 overview ---------- */
function headline(run) {
  const en = run.summary.english, { names, top, tied } = ranked(en), m = en[top];
  const n = names.length;
  let s = `On ${m.n_items} items, ${esc(top)} had the highest accuracy at ${pct(m.accuracy)} (95% interval ${pct(m.ci_low)} to ${pct(m.ci_high)}).`;
  if (n > 1) s += tied.length > 1 ? ` The intervals of ${tied.length - 1} other model${tied.length > 2 ? "s" : ""} overlap with it, so this item bank cannot separate ${tied.length > 2 ? "them" : "it from " + esc(tied[1])}.` : ` Its interval does not overlap with any other model's.`;
  return s;
}
async function viewOverview() {
  const run = await loadRun();
  if (!run) { $("#main").innerHTML = EMPTY; setBanner(null); return; }
  const sm = run.summary, en = sm.english, { names } = ranked(en);
  const worst = Math.max(...names.map((n) => en[n].unparsed_rate || 0));
  const failed = names.reduce((a, n) => a + (en[n].failed_calls || 0), 0);
  const au = sm.audit || { consensus_against_key: [], never_correct: [] };
  $("#main").innerHTML = `
  <h1>Overview</h1><div class="eyebrow">Run ${esc(run.id)} · harness ${esc(run.meta.harness_version)} · ${esc((run.meta.started_utc || "").slice(0, 10))}</div>
  <div class="hero"><div class="eyebrow">Headline</div><div class="big">${headline(run)}</div>
    <p>Accuracy on multiple-choice public health questions is a screening signal. It does not show that a tool is safe or suitable for use in a health programme.</p></div>
  <div class="grid cols4">
    <div class="card kpi"><div class="l">Models</div><div class="v">${names.length}</div><div class="s">${esc(names.join(", "))}</div></div>
    <div class="card kpi"><div class="l">Items</div><div class="v">${en[names[0]].n_items}</div><div class="s">${esc(run.meta.args?.reps ?? "?")} repetitions, shuffled option order</div></div>
    <div class="card kpi"><div class="l">Unparseable replies</div><div class="v">${pct(worst)}</div><div class="s">Highest across models. Counted as wrong.</div></div>
    <div class="card kpi"><div class="l">Failed calls</div><div class="v">${failed}</div><div class="s">Errors excluded from accuracy, shown here</div></div>
  </div>
  <div class="grid" style="margin-top:16px;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr)">
    <div class="card"><h2>Ranking with uncertainty</h2>${leaderboard(en)}<details class="how"><summary>How to read this chart</summary><p>Each marker is a model's average score. The band around it shows the range the true score plausibly falls in, given only ${en[names[0]].n_items} questions. If two bands overlap, treat the models as equal.</p></details></div>
    <div class="card"><h2>Items to review</h2>
      <p class="lead">Items where most models agree against the key may have a key error or an ambiguous stem. A person decides.</p>
      ${au.consensus_against_key.length ? `<table><thead><tr><th>Item</th><th>Key</th><th>Models chose</th></tr></thead><tbody>${au.consensus_against_key.map((a) => `<tr><td><button class="link" data-item="${esc(a.id)}">${esc(a.id)}</button></td><td>${esc(a.key)}</td><td>${esc(a.consensus)} (${esc(a.models_agreeing)} of ${esc(a.models)})</td></tr>`).join("")}</tbody></table>` : "<p>No item flagged. With fewer than 3 models the audit cannot flag items.</p>"}
      <p>Never answered correctly by any model: ${au.never_correct.length ? au.never_correct.map((i) => `<button class="link" data-item="${esc(i)}">${esc(i)}</button>`).join(", ") : "none"}.</p></div>
  </div>`;
  $("#main").insertAdjacentHTML("beforeend", provenance(run));
  $$("[data-item]").forEach((b) => (b.onclick = () => { S.focusItem = b.dataset.item; go("explorer"); }));
}

/* ---------- 02 compare ---------- */
async function viewCompare() {
  const run = await loadRun();
  if (!run) { $("#main").innerHTML = EMPTY; return; }
  const sm = run.summary, en = sm.english, { names, tied } = ranked(en);
  const rows = names.map((n, i) => { const m = en[n]; return `<tr><td><strong>${i + 1}. ${esc(n)}</strong></td><td class="n">${pct(m.accuracy)}</td><td class="n">${pct(m.ci_low)} to ${pct(m.ci_high)}</td><td>${tied.includes(n) && i > 0 ? '<span class="tag warn">overlaps the top model</span>' : i === 0 ? '<span class="tag ok">highest</span>' : '<span class="tag">separated from top</span>'}</td><td class="n">${m.consistency == null ? "needs 2+ reps" : pct(m.consistency)}</td><td class="n">${pct(m.top_letter_share)}</td><td>${m.top_letter_share > 0.4 ? '<span class="tag warn">position bias likely</span>' : '<span class="tag">no strong bias</span>'}</td></tr>`; }).join("");
  const kk = Object.keys(sm.krio || {});
  const krio = kk.length ? `<div class="card" style="margin-top:16px"><h2>English and Krio</h2><table><thead><tr><th>Model</th><th class="n">Items</th><th class="n">English</th><th class="n">Krio</th><th class="n">Gap (EN minus KRI)</th><th>95% interval</th></tr></thead><tbody>${kk.map((n) => { const k = sm.krio[n]; return `<tr><td>${esc(n)}</td><td class="n">${k.n_items}</td><td class="n">${pct(k.en_accuracy)}</td><td class="n">${pct(k.kri_accuracy)}</td><td class="n">${pts(k.gap)}</td><td>${k.ci_low == null ? "<span class='tag warn'>not reported, too few items</span>" : `${pts(k.ci_low)} to ${pts(k.ci_high)}`}</td></tr>`; }).join("")}</tbody></table><div class="note">The Krio subset is small. The text was AI-drafted and then reviewed by one native speaker; there was no second reader or back-translation. Read gaps as indicative.</div></div>` : "";
  $("#main").innerHTML = `<div class="eyebrow">Compare models</div><h1>Who can be separated, and who cannot</h1>
  <p class="lead">Overlap of 95% intervals is a conservative screen, not a significance test. Models that overlap should be treated as indistinguishable on this item bank.</p>
  <div class="card"><h2>Ranking</h2>${leaderboard(en)}</div>
  <div class="card" style="margin-top:16px"><h2>Detail and robustness</h2><table><thead><tr><th>Model</th><th class="n">Accuracy</th><th class="n">95% interval</th><th>Versus top</th><th class="n">Order consistency</th><th class="n">Top letter share</th><th>Reading</th></tr></thead><tbody>${rows}</tbody></table>
  <div class="legend"><span>Order consistency: average share of repetitions that choose the same content when option order changes (1.0 = always). A top letter share near 25% suggests no position preference.</span></div></div>${krio}`;
}

/* ---------- 03 domains ---------- */
async function viewDomains() {
  const run = await loadRun();
  if (!run) { $("#main").innerHTML = EMPTY; return; }
  const en = run.summary.english;
  $("#main").innerHTML = `<div class="eyebrow">Domains</div><h1>Where models are strong or weak</h1>
  <p class="lead">Each domain holds about six items, so one item moves a cell by about 17 points. Use this to find areas to examine, not to rank models.</p>
  <div class="grid cols2"><div class="card"><h2>Radar</h2>${radar(en)}<details class="how"><summary>How to read this chart</summary><p>Each corner is a topic. The further a shape reaches toward the edge, the more questions that model answered correctly in that topic.</p></details></div><div class="card"><h2>Heatmap</h2>${heat(en)}<details class="how"><summary>How to read this table</summary><p>Darker blue means a higher share correct. Each topic has few questions, so a single question can change a cell a lot.</p></details></div></div>`;
}

/* ---------- 04 explorer ---------- */
async function viewExplorer() {
  const run = await loadRun();
  if (!run) { $("#main").innerHTML = EMPTY; return; }
  const [source, id] = S.sel.split("/");
  const hasKri = Object.keys(run.summary.krio || {}).length > 0;
  if (!hasKri) S.cond = "en";
  S.ex = await api(`/api/run/${source}/${encodeURIComponent(id)}/items?condition=${S.cond}`);
  const ex = S.ex, domains = [...new Set(ex.items.map((i) => i.domain))].sort();
  $("#main").innerHTML = `<div class="eyebrow">Item explorer</div><h1>Every item, every model</h1>
  <p class="lead">Open an item to see how each model answered across option orders. The key is shown in green. Bars show how many replies chose each option.</p>
  <div class="row noprint" style="margin-bottom:12px"><select id="xd" aria-label="Filter by domain" style="width:auto"><option value="">All domains</option>${domains.map((d) => `<option>${esc(d)}</option>`).join("")}</select>
  <select id="xf" aria-label="Sort or filter items" style="width:auto"><option value="all">All items</option><option value="hard">Hardest first</option><option value="split">Models disagree most</option><option value="allwrong">Nobody correct</option></select>
  ${hasKri ? `<select id="xc" aria-label="Language of items" style="width:auto"><option value="en">English</option><option value="kri" ${S.cond === "kri" ? "selected" : ""}>Krio</option></select>` : ""}
  <input id="xq" type="text" aria-label="Search item text" placeholder="Search item text" class="grow"><span class="lead" id="xn"></span></div><div id="xl"></div>`;
  const rate = (c) => c.correct / Math.max(c.calls, 1);
  const acc = (it) => { const v = Object.values(it.models).map(rate); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0; };
  const spread = (it) => { const v = Object.values(it.models).map(rate); return v.length ? Math.max(...v) - Math.min(...v) : 0; };
  const draw = () => {
    const d = $("#xd").value, f = $("#xf").value, q = $("#xq").value.toLowerCase();
    let list = ex.items.filter((i) => (!d || i.domain === d) && (!q || i.question.toLowerCase().includes(q) || i.id.toLowerCase().includes(q)));
    if (f === "hard") list = list.sort((a, b) => acc(a) - acc(b));
    if (f === "split") list = list.sort((a, b) => spread(b) - spread(a));
    if (f === "allwrong") list = list.filter((i) => Object.keys(i.models).length && acc(i) === 0);
    $("#xn").textContent = `${list.length} items`;
    $("#xl").innerHTML = list.map((it) => {
      const cells = ex.models.map((m, k) => {
        const c = it.models[m]; if (!c) return "";
        const tot = Math.max(c.calls, 1);
        const bar = c.picks.map((p, o) => `<span style="width:${(p / tot) * 100}%;background:${o === it.answer ? "var(--ok)" : "var(--bad)"};opacity:${o === it.answer ? 1 : 0.35 + 0.15 * o}" title="${"ABCD"[o]}: ${p}"></span>`).join("");
        return `<tr><td><svg width="14" height="14" viewBox="-8 -8 16 16">${marker(k, 0, 0, 5)}</svg> ${esc(m)}</td><td class="n">${c.correct}/${c.calls}</td><td><div class="pickbar">${bar}</div></td><td>${c.picks.map((p, o) => `${"ABCD"[o]}:${p}`).join(" ")}${c.unparsed ? ` unparsed:${c.unparsed}` : ""}</td></tr>`;
      }).join("");
      const a = acc(it);
      return `<details class="card" style="margin-bottom:10px" id="it-${esc(it.id)}" ${S.focusItem === it.id ? "open" : ""}><summary><strong>${esc(it.id)}</strong> <span class="tag">${esc(it.domain)}</span> <span class="tag ${a === 0 ? "bad" : a < .5 ? "warn" : "ok"}">${pct(a, 0)} correct overall</span> ${esc(it.question).slice(0, 110)}${it.question.length > 110 ? "…" : ""}</summary>
        <p style="margin-top:10px">${esc(it.question)}</p>${it.options.map((o, n) => `<div class="opt ${n === it.answer ? "key" : ""}">${"ABCD"[n]}. ${esc(o)}${n === it.answer ? " (key)" : ""}</div>`).join("")}
        <table style="margin-top:10px"><thead><tr><th>Model</th><th class="n">Correct</th><th>Choices by content option</th><th>Counts</th></tr></thead><tbody>${cells}</tbody></table></details>`;
    }).join("") || "<p>No items match.</p>";
    if (S.focusItem) { const el = $("#it-" + S.focusItem); if (el) el.scrollIntoView({ block: "center" }); S.focusItem = null; }
  };
  ["xd", "xf", "xq"].forEach((i) => ($("#" + i).oninput = draw));
  if ($("#xc")) $("#xc").onchange = (e) => { S.cond = e.target.value; render(); };
  draw();
}

/* ---------- 05 partner summary ---------- */
async function viewSummary() {
  const run = await loadRun();
  if (!run) { $("#main").innerHTML = EMPTY; return; }
  const sm = run.summary, en = sm.english, { names, tied } = ranked(en), meta = run.meta;
  const drafts = meta.item_status_counts?.draft || 0, au = sm.audit || { consensus_against_key: [], never_correct: [] };
  const caveats = [
    meta.mock ? "These results are SIMULATED from a mock model. They are not evaluation data." : null,
    drafts ? `${drafts} items had not been approved when this run was made. Results are provisional.` : "The items were approved by their author. No independent subject-matter reviewer has checked them.",
    `${en[names[0]].n_items} items give wide intervals. Models within a few points of each other cannot be ranked.`,
    Object.keys(sm.krio || {}).length ? "The Krio subset has 20 items, was AI-drafted and reviewed by one native speaker, with no second reader or back-translation." : null,
    "Multiple-choice knowledge does not test free-text advice, referral decisions, local protocol fit or harm.",
    au.consensus_against_key.length ? `${au.consensus_against_key.length} item(s) were flagged by the answer-key audit and need human review.` : null,
  ].filter(Boolean);
  const rows = names.map((n, i) => { const m = en[n]; return `<tr><td>${esc(n)}</td><td class="n">${pct(m.accuracy)}</td><td class="n">${pct(m.ci_low)} to ${pct(m.ci_high)}</td><td>${tied.includes(n) && i > 0 ? "overlaps top" : i === 0 ? "highest" : "below top"}</td></tr>`; }).join("");
  $("#main").innerHTML = `<div class="row between noprint"><div><div class="eyebrow">Partner summary</div><p class="lead">One page for meetings. Print it or save it as PDF from the print dialog.</p></div><button class="btn" id="pr">Print or save as PDF</button></div>
  <article class="paper"><div class="eyebrow">SL-Health-LLM-Eval · pilot evaluation summary</div><h1>Language model screening on public health questions</h1>
  <p class="lead">Run ${esc(run.id)} · ${esc((meta.started_utc || "").slice(0, 10))} · harness ${esc(meta.harness_version)} · prepared with the Evaluation Workbench</p>
  <h2>Headline</h2><p class="statement">${headline(run)}</p>
  <h2>Results</h2><table><thead><tr><th>Model</th><th class="n">Accuracy</th><th class="n">95% interval</th><th>Versus top</th></tr></thead><tbody>${rows}</tbody></table>
  <h2>What this shows</h2><ul><li>How often each model picks the keyed answer on original public health questions, with option order shuffled.</li><li>Whether answers follow content or position, and where domain performance is weak.</li></ul>
  <h2>What this does not show</h2><ul><li>Safety or suitability for any clinical or programme use.</li><li>Performance on free-text questions, patient-facing advice or local workflows.</li></ul>
  <h2>Caveats</h2><ul>${caveats.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
  <h2>Suggested next steps</h2><ol><li>Independent review of the item bank against national guidelines.</li><li>A second Krio reader and back-translation.</li><li>A free-text scenario protocol with clinician scoring.</li></ol>
  <p><small>Run ${esc(run.id)}, harness ${esc(meta.harness_version)}, item bank fingerprint ${esc((meta.dataset_sha256 || "").slice(0, 12))}, ${esc(meta.args?.reps ?? "?")} repetitions, seed ${esc(meta.args?.seed ?? "?")}.</small></p><p><small>Contact: Alhassan Mayei, alhassanmayei@gmail.com. Code, protocol and data: github.com/amayei/sl-health-llm-eval</small></p></article>`;
  $("#pr").onclick = () => window.print();
}

/* ---------- item bank ---------- */
async function viewItems() {
  setBanner(null);
  const { items, krio } = await api("/api/items");
  const kmap = Object.fromEntries(krio.map((k) => [k.id, k]));
  const domains = [...new Set(items.map((i) => i.domain))].sort();
  $("#main").innerHTML = `<div class="eyebrow">Item bank</div><h1>${items.length} items</h1><p class="lead">The key is highlighted for reviewers. Status shows whether the item passed the review gate.</p>
   <div class="row noprint"><select id="fdom" aria-label="Filter by domain" style="width:auto"><option value="">All domains</option>${domains.map((d) => `<option>${esc(d)}</option>`).join("")}</select>
   <select id="flang" aria-label="Language of items" style="width:auto"><option value="en">English</option><option value="kri">Krio (${krio.length})</option></select>
   <input id="fq" type="text" aria-label="Search item text" placeholder="Search text" class="grow"><span id="icount" class="lead"></span></div><div id="ilist" style="margin-top:12px"></div>`;
  const draw = () => {
    const d = $("#fdom").value, q = $("#fq").value.toLowerCase(), lang = $("#flang").value;
    const list = items.filter((i) => (!d || i.domain === d) && (lang === "en" || kmap[i.id]) && (!q || (lang === "kri" ? kmap[i.id].question : i.question).toLowerCase().includes(q)));
    $("#ilist").innerHTML = list.map((i) => {
      const src = lang === "kri" ? kmap[i.id] : i;
      return `<div class="card" style="margin-bottom:10px"><div class="row"><strong>${esc(i.id)}</strong><span class="tag">${esc(i.domain)}</span><span class="tag ${i.status === "reviewed" ? "ok" : "warn"}">${i.status === "reviewed" ? "approved" : "draft"}</span>${i.krio_subset ? '<span class="tag">Krio subset</span>' : ""}</div>
      <p>${esc(src.question)}</p>${src.options.map((o, n) => `<div class="opt ${n === i.answer ? "key" : ""}">${"ABCD"[n]}. ${esc(o)}${n === i.answer ? " (key)" : ""}</div>`).join("")}
      <small class="lead">Source anchor: ${esc(i.source_anchor)}${i.reviewed_by ? ` · approved by ${esc(i.reviewed_by)}, ${esc(i.reviewed_on || "")}` : ""}</small></div>`;
    }).join("") || "<p>No items match.</p>";
    $("#icount").textContent = `${list.length} shown`;
  };
  ["fdom", "flang", "fq"].forEach((i) => ($("#" + i).oninput = draw));
  draw();
}

/* ---------- new evaluation ---------- */
function viewRun() {
  setBanner(null);
  const st = S.state, drafts = st.item_status.draft || 0;
  const banks = st.banks.map((b) => `<option value="${esc(b.name)}">${esc(b.label)}, ${b.n_items} items</option>`).join("");
  const models = st.models.map((m, i) => `<div class="card" style="margin-bottom:10px;padding:12px 14px"><label class="chk" style="margin:0"><input type="checkbox" class="msel" data-i="${i}"><span><strong>${esc(m.label)}</strong> <small class="lead">${esc(m.provider)} / ${esc(m.model)}</small></span></label>
     <input type="password" class="mkey" data-i="${i}" placeholder="API key (${esc(m.key_name)}), kept in memory only" autocomplete="off"></div>`).join("");
  $("#main").innerHTML = `<div class="eyebrow">New evaluation</div><h1>Run the protocol</h1><p class="lead">The same questions are asked of every model, with the answer options shuffled, so results can be compared fairly.</p>
  <div class="crumbs"><span class="on">1 Choose questions</span><span class="on">2 Choose models</span><span>3 Start and watch progress</span></div>
  <div class="grid cols2"><div class="card"><h2>1. Questions</h2><select id="bank" aria-label="Item bank">${banks}</select>
    <label class="chk"><input type="checkbox" id="mock"><span>Simulated run (random answers, no API key, for exploring the interface only)</span></label>
    ${drafts ? `<label class="chk"><input type="checkbox" id="drafts"><span>Provisional run: allow unapproved items (${drafts} draft). Results will be labelled provisional.</span></label>` : ""}
    <label for="rid">Run name</label><input id="rid" type="text" placeholder="for example pilot-1">
    <label for="reps">Repetitions (1 to 10)</label><input id="reps" type="number" min="1" max="10" value="3">
    <h2 style="margin-top:20px">Import your own item bank</h2>
    <p class="lead">CSV columns: id, domain, question, option_a, option_b, option_c, option_d, answer (A to D). Imports are drafts unless you confirm review.</p>
    <input id="bname" type="text" placeholder="Bank name"><textarea id="btext" rows="4" placeholder="Paste CSV here"></textarea>
    <label class="chk"><input type="checkbox" id="brev"><span>These items were reviewed and the key was checked by a qualified person</span></label>
    <button class="btn sec" id="bimp">Import</button><div id="bmsg"></div></div>
  <div class="card"><h2>2. Models</h2>${models}
    <details style="margin-top:8px"><summary>Add a model on any OpenAI-compatible endpoint (local or hosted)</summary>
      <label for="cl">Label</label><input id="cl" type="text" placeholder="local-model"><label for="cm">Model id</label><input id="cm" type="text">
      <label for="cu">Base URL</label><input id="cu" type="text" placeholder="http://127.0.0.1:11434/v1"><label for="ck">API key (optional)</label><input id="ck" type="password" autocomplete="off">
      <label class="chk"><input type="checkbox" id="cuse"><span>Include this model</span></label></details></div></div>
  <div class="row" style="margin-top:16px"><button class="btn" id="go">Start evaluation</button><button class="btn sec" id="stop" hidden>Stop</button></div>
  <div id="rmsg"></div><div id="prog" style="margin-top:10px"></div><pre class="log" id="log" aria-live="polite" aria-label="Run log" hidden></pre>`;
  $("#bimp").onclick = async () => {
    try {
      const r = await api("/api/itembanks", { body: { name: $("#bname").value.trim(), text: $("#btext").value, format: "csv", confirm_reviewed: $("#brev").checked } });
      $("#bmsg").innerHTML = r.ok ? `<div class="note ok">Imported ${r.n_items} items.${r.warnings.length ? " Warnings: " + esc(r.warnings.join("; ")) : ""}</div>` : `<div class="note bad">${r.problems.map(esc).join("<br>")}</div>`;
      if (r.ok) { S.state = await api("/api/state"); $("#bank").innerHTML = S.state.banks.map((b) => `<option value="${esc(b.name)}">${esc(b.label)}, ${b.n_items} items</option>`).join(""); }
    } catch (e) { $("#bmsg").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
  };
  $("#go").onclick = startJob;
  $("#stop").onclick = () => S.job && api(`/api/jobs/${S.job}/stop`, { body: {} });
}
async function startJob() {
  const picked = [];
  $$(".msel:checked").forEach((c) => picked.push({ label: S.state.models[+c.dataset.i].label, api_key: $(`.mkey[data-i="${c.dataset.i}"]`).value }));
  if ($("#cuse").checked) picked.push({ custom: true, label: $("#cl").value.trim(), model: $("#cm").value.trim(), base_url: $("#cu").value.trim(), api_key: $("#ck").value, max_tokens: 16 });
  if ($("#mock").checked && !picked.length) picked.push({ label: S.state.models[0].label });
  const body = { models: picked, bank: $("#bank").value, mock: $("#mock").checked, allow_drafts: !!$("#drafts")?.checked, reps: +$("#reps").value, run_id: $("#rid").value.trim() || undefined };
  try {
    const r = await api("/api/jobs", { body });
    $$(".mkey,#ck").forEach((i) => (i.value = ""));
    S.job = r.job_id; S.running = true;
    $("#rmsg").innerHTML = ""; $("#go").disabled = true; $("#stop").hidden = false; $("#log").hidden = false;
    poll();
  } catch (e) { $("#rmsg").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
}
async function poll() {
  const j = await api(`/api/jobs/${S.job}`);
  $("#log").textContent = j.log.join("\n");
  const done = Object.values(j.progress).reduce((t, v) => t + v.calls, 0), total = (j.expected || 0) * (j.n_models || 1), p = total ? Math.min(100, Math.round((done / total) * 100)) : 0;
  $("#prog").innerHTML = `${total ? `<div class="progress" role="progressbar" aria-valuenow="${p}" aria-valuemin="0" aria-valuemax="100"><div style="width:${p}%"></div></div><div><strong>${p}%</strong> done (${done} of ${total} answers)</div>` : ""}` + Object.entries(j.progress).map(([k, v]) => `<div>${esc(k)}: ${v.calls} answers, ${v.failures} failed</div>`).join("");
  S.running = j.status === "running";
  if (j.status === "running") { S.timer = setTimeout(poll, 1000); return; }
  $("#go").disabled = false; $("#stop").hidden = true;
  if (j.status === "done") {
    S.state = await api("/api/state"); S.sel = `local/${j.run_id}`; S.run = null;
    $("#rmsg").innerHTML = `<div class="note ok">Finished. <button class="link" id="open">Open overview</button></div>`;
    $("#open").onclick = () => go("overview");
  } else $("#rmsg").innerHTML = `<div class="note bad">${j.status === "stopped" ? "Stopped." : "Failed: " + esc(j.error)}</div>`;
}

/* ---------- guide ---------- */
function viewHelp() {
  setBanner(null);
  $("#main").innerHTML = `<div class="help"><div class="eyebrow">Guide</div><h1>How to read this application</h1>
  <h2>What it does</h2><p>It measures how accurately language models answer public health multiple-choice questions, in English and in a Krio subset, and reports uncertainty and known failure modes. It supports a pilot pre-deployment evaluation. It does not certify any tool for clinical or programme use.</p>
  <h2>Screens</h2><ul><li><strong>Overview</strong>: headline, ranking and items needing review.</li><li><strong>Compare models</strong>: who can and cannot be separated, robustness and the English and Krio gap.</li><li><strong>Domains</strong>: radar and heatmap.</li><li><strong>Item explorer</strong>: every item with each model's choices.</li><li><strong>Partner summary</strong>: a printable one-page brief.</li></ul>
  <h2>Reading the numbers</h2><ul>
  <li><strong>Accuracy</strong> is the mean over items of the share of correct answers across repetitions. The interval resamples items 10,000 times (seeded), so it reflects item sampling, not model randomness.</li>
  <li><strong>Overlap</strong> of intervals is a conservative screen. Overlapping models should not be ranked.</li>
  <li><strong>Order consistency</strong> and <strong>top letter share</strong> show whether a model follows content or position.</li>
  <li><strong>Gap</strong> is English minus Krio accuracy on the same items, reported only with at least 15 paired items.</li>
  <li><strong>Key audit</strong> lists items where models agree against the key. A person decides.</li></ul>
  <h2>Status labels</h2><ul><li><strong>SIMULATED</strong>: mock model, random answers.</li><li><strong>PROVISIONAL</strong>: some items were unapproved when the run was made.</li></ul>
  <h2>Privacy</h2><p>The app listens on this computer only. API keys you type are used for the run and not written to disk. Questions go to the model provider you choose. Do not import items containing patient information. Use a local OpenAI-compatible endpoint to keep everything on this computer.</p>
  <h2>Limits</h2><ul><li>Multiple-choice knowledge is a weak proxy for safe deployment.</li><li>48 items give wide intervals.</li><li>Krio items are few and were reviewed by one reader.</li><li>Items are author-approved, with no independent review.</li></ul></div>`;
}

/* ---------- shell ---------- */
async function render() {
  clearTimeout(S.timer);
  $$("#nav button").forEach((b) => { const on = b.dataset.view === S.view; b.classList.toggle("on", on); if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  try {
    runbar();
    const titles = { overview: "Overview", compare: "Compare models", domains: "Domains", explorer: "Item explorer", summary: "Partner summary", items: "Item bank", run: "New evaluation", help: "Guide", about: "About" };
    document.title = `${titles[S.view]} | SL-Health-LLM-Eval Workbench`;
    const v = { about: viewAbout, overview: viewOverview, compare: viewCompare, domains: viewDomains, explorer: viewExplorer, summary: viewSummary, items: viewItems, run: viewRun, help: viewHelp }[S.view];
    await v();
  } catch (e) { $("#main").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
}
function go(v) { S.view = v; render(); $("#main").focus(); window.scrollTo(0, 0); }
window.go = go;
$$("#nav button").forEach((b) => (b.onclick = () => go(b.dataset.view)));
$("#about-link").onclick = () => go("about");
window.addEventListener("beforeunload", (e) => { if (S.running) { e.preventDefault(); e.returnValue = ""; } });
function setTheme(t) { document.documentElement.setAttribute("data-theme", t); try { localStorage.setItem("slwb-theme", t); } catch (e) {} $$("[data-theme-set]").forEach((b) => b.classList.toggle("on", b.dataset.themeSet === t)); }
$$("[data-theme-set]").forEach((b) => (b.onclick = () => setTheme(b.dataset.themeSet)));
setTheme(document.documentElement.getAttribute("data-theme"));
api("/api/state").then((s) => { S.state = s; render(); }).catch((e) => ($("#main").textContent = e.message));
