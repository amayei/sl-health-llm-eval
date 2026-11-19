"use strict";
const TOKEN = document.querySelector('meta[name="wb-token"]').content;
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 1) => (x == null ? "n/a" : (x * 100).toFixed(d) + "%");
const COLORS = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)"];
const S = { state: null, view: "dashboard", sel: null, run: null, job: null, timer: null, lang: "en" };

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
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function setBanner(run) {
  const b = $("#banner");
  if (!run) { b.hidden = true; return; }
  const drafts = run.meta.item_status_counts?.draft || 0;
  if (run.meta.mock) {
    b.className = "banner mock"; b.hidden = false;
    b.textContent = "SIMULATED RESULTS: this run used a mock model that answers at random. Not real evaluation data.";
  } else if (drafts > 0) {
    b.className = "banner draft"; b.hidden = false;
    b.textContent = `PROVISIONAL: ${drafts} of the items in this run are not yet approved by a reviewer. Do not cite these figures as final.`;
  } else b.hidden = true;
}

/* ---------- charts ---------- */
function accuracyChart(models) {
  const names = Object.keys(models);
  const W = 640, rowH = 38, pad = { l: 150, r: 24, t: 14, b: 30 }, H = pad.t + pad.b + names.length * rowH;
  const x = (v) => pad.l + v * (W - pad.l - pad.r);
  let g = "";
  for (let t = 0; t <= 1.0001; t += 0.25) g += `<line class="grid" x1="${x(t)}" x2="${x(t)}" y1="${pad.t}" y2="${H - pad.b}"/><text class="m" x="${x(t)}" y="${H - 10}" text-anchor="middle">${Math.round(t * 100)}%</text>`;
  g += `<line x1="${x(0.25)}" x2="${x(0.25)}" y1="${pad.t}" y2="${H - pad.b}" stroke="var(--mute)" stroke-dasharray="4 3"/>`;
  names.forEach((n, i) => {
    const m = models[n], y = pad.t + i * rowH + rowH / 2, c = COLORS[i % 4];
    g += `<text x="${pad.l - 10}" y="${y + 4}" text-anchor="end">${esc(n)}</text>`;
    g += `<rect x="${x(0)}" y="${y - 9}" width="${x(m.accuracy) - x(0)}" height="18" rx="3" fill="${c}" opacity=".85"/>`;
    if (m.ci_low != null) g += `<line x1="${x(m.ci_low)}" x2="${x(m.ci_high)}" y1="${y}" y2="${y}" stroke="var(--ink)" stroke-width="2"/><line x1="${x(m.ci_low)}" x2="${x(m.ci_low)}" y1="${y - 6}" y2="${y + 6}" stroke="var(--ink)" stroke-width="2"/><line x1="${x(m.ci_high)}" x2="${x(m.ci_high)}" y1="${y - 6}" y2="${y + 6}" stroke="var(--ink)" stroke-width="2"/>`;
    g += `<text x="${Math.min(x(m.ci_high ?? m.accuracy) + 8, W - 40)}" y="${y - 12}" font-weight="600">${pct(m.accuracy)}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Accuracy by model with 95% bootstrap intervals; dashed line marks chance at 25%" style="width:100%;height:auto">${g}</svg>
  <div class="legend"><span>Bar: mean item accuracy. Whisker: 95% bootstrap interval over items. Dashed line: chance (25%).</span></div>`;
}

function heat(models) {
  const names = Object.keys(models);
  const domains = [...new Set(names.flatMap((n) => Object.keys(models[n].domain_accuracy || {})))].sort();
  if (!domains.length) return "<p class='lead'>No domain data.</p>";
  const cell = (d) => {
    if (!d) return "<td>n/a</td>";
    const a = d.accuracy, alpha = 0.12 + 0.6 * a;
    return `<td style="background:color-mix(in srgb,var(--brand) ${Math.round(alpha * 100)}%,transparent)" title="${d.n_items} items">${pct(a, 0)}</td>`;
  };
  return `<table class="heat"><thead><tr><th>Domain</th>${names.map((n) => `<th>${esc(n)}</th>`).join("")}</tr></thead><tbody>` +
    domains.map((d) => `<tr><td>${esc(d)}</td>${names.map((n) => cell(models[n].domain_accuracy?.[d])).join("")}</tr>`).join("") +
    `</tbody></table><div class="legend"><span>Cells show accuracy per domain. Domains hold few items, so differences of one or two items are not meaningful.</span></div>`;
}

/* ---------- dashboard ---------- */
async function viewDashboard() {
  const st = S.state;
  const main = $("#main");
  if (!st.runs.length) {
    main.innerHTML = `<h1>Dashboard</h1><div class="card"><p>No runs yet. Start one under <strong>New evaluation</strong>. A simulated run needs no API key and lets you explore the interface.</p></div>`;
    setBanner(null); return;
  }
  const sel = S.sel || `${st.runs[0].source}/${st.runs[0].id}`;
  S.sel = sel;
  const [source, id] = sel.split("/");
  S.run = await api(`/api/run/${source}/${encodeURIComponent(id)}`);
  const run = S.run, sm = run.summary, en = sm.english, names = Object.keys(en);
  setBanner(run);
  const best = names.reduce((a, b) => (en[a].accuracy >= en[b].accuracy ? a : b));
  const nItems = en[best].n_items;
  const unparsed = Math.max(...names.map((n) => en[n].unparsed_rate || 0));
  const cons = names.map((n) => en[n].consistency).filter((v) => v != null);
  const opts = st.runs.map((r) => `<option value="${esc(r.source)}/${esc(r.id)}" ${`${r.source}/${r.id}` === sel ? "selected" : ""}>${esc(r.id)} (${r.source}${r.mock ? ", simulated" : ""})</option>`).join("");
  let krio = "";
  const kk = Object.keys(sm.krio || {});
  if (kk.length) {
    krio = `<div class="card"><h2>English and Krio</h2><table><thead><tr><th>Model</th><th class="n">Items</th><th class="n">English</th><th class="n">Krio</th><th class="n">Gap (EN minus KRI)</th><th>95% interval</th></tr></thead><tbody>` +
      kk.map((n) => { const k = sm.krio[n]; return `<tr><td>${esc(n)}</td><td class="n">${k.n_items}</td><td class="n">${pct(k.en_accuracy)}</td><td class="n">${pct(k.kri_accuracy)}</td><td class="n">${k.gap == null ? "n/a" : (k.gap * 100).toFixed(1) + " pts"}</td><td>${k.ci_low == null ? "<span class='tag warn'>not reported, too few items</span>" : `${(k.ci_low * 100).toFixed(1)} to ${(k.ci_high * 100).toFixed(1)} pts`}</td></tr>`; }).join("") +
      `</tbody></table><div class="note">The Krio subset is small. Treat gaps as indicative. The Krio text was AI-drafted and then reviewed by one native speaker; no second reader or back-translation has been done.</div></div>`;
  }
  const au = sm.audit || { consensus_against_key: [], never_correct: [] };
  const audit = `<div class="card"><h2>Answer-key audit</h2>
    <p class="lead">Items where most models agree on an answer that differs from the key are candidates for a key error or an ambiguous question. They are reviewed by a person, not corrected automatically.</p>
    ${au.consensus_against_key.length ? `<table><thead><tr><th>Item</th><th>Key</th><th>Model consensus</th><th>Agreeing</th></tr></thead><tbody>${au.consensus_against_key.map((a) => `<tr><td>${esc(a.id)}</td><td>${esc(a.key)}</td><td>${esc(a.consensus)}</td><td>${esc(a.models_agreeing)} of ${esc(a.models)}</td></tr>`).join("")}</tbody></table>` : "<p>No item flagged. With fewer than 3 models the audit cannot flag items.</p>"}
    <p>Never answered correctly by any model: ${au.never_correct.length ? au.never_correct.map(esc).join(", ") : "none"}.</p></div>`;
  main.innerHTML = `
  <div class="row" style="justify-content:space-between"><div><h1>Dashboard</h1><p class="lead">Run <strong>${esc(run.id)}</strong>, harness ${esc(run.meta.harness_version)}, started ${esc(run.meta.started_utc || "")}</p></div>
    <div class="row noprint"><select id="runsel" aria-label="Select run" style="width:auto">${opts}</select>
    <button class="btn sec" id="exp">Export HTML report</button><button class="btn sec" id="prn">Print</button></div></div>
  <div class="grid cols4">
    <div class="card kpi"><div class="l">Models evaluated</div><div class="v">${names.length}</div><div class="s">${esc(names.join(", "))}</div></div>
    <div class="card kpi"><div class="l">Items per condition</div><div class="v">${nItems}</div><div class="s">${esc(run.meta.args?.reps ?? "?")} repetitions with shuffled option order</div></div>
    <div class="card kpi"><div class="l">Highest accuracy</div><div class="v">${pct(en[best].accuracy)}</div><div class="s">${esc(best)}, 95% interval ${pct(en[best].ci_low)} to ${pct(en[best].ci_high)}</div></div>
    <div class="card kpi"><div class="l">Unparseable replies (max)</div><div class="v">${pct(unparsed)}</div><div class="s">Replies without a valid letter count as wrong</div></div>
  </div>
  <div class="grid cols2" style="margin-top:14px">
    <div class="card"><h2>Accuracy with 95% intervals</h2>${accuracyChart(en)}</div>
    <div class="card"><h2>Accuracy by domain</h2>${heat(en)}</div>
  </div>
  <div class="card" style="margin-top:14px"><h2>Robustness checks</h2><table><thead><tr><th>Model</th><th class="n">Order consistency</th><th class="n">Most-chosen letter share</th><th class="n">Failed calls</th><th>Reading</th></tr></thead><tbody>` +
    names.map((n) => { const m = en[n]; const flag = m.top_letter_share > 0.4 ? "<span class='tag warn'>position bias likely</span>" : "<span class='tag'>no strong bias</span>"; return `<tr><td>${esc(n)}</td><td class="n">${m.consistency == null ? "needs 2+ repetitions" : pct(m.consistency)}</td><td class="n">${pct(m.top_letter_share)}</td><td class="n">${m.failed_calls}</td><td>${flag}</td></tr>`; }).join("") +
    `</tbody></table><div class="legend"><span>Order consistency: share of items where the model picks the same content when option order changes. A letter share near 25% suggests no position preference.</span></div></div>
  <div style="margin-top:14px" class="grid">${krio}${audit}</div>`;
  $("#runsel").onchange = (e) => { S.sel = e.target.value; render(); };
  $("#exp").onclick = () => download(`/api/export/${source}/${encodeURIComponent(id)}.html`, `report-${id}.html`);
  $("#prn").onclick = () => window.print();
}

/* ---------- items ---------- */
async function viewItems() {
  setBanner(null);
  const { items, krio } = await api("/api/items");
  const kmap = Object.fromEntries(krio.map((k) => [k.id, k]));
  const domains = [...new Set(items.map((i) => i.domain))].sort();
  const main = $("#main");
  const draw = () => {
    const d = $("#fdom")?.value || "", q = ($("#fq")?.value || "").toLowerCase(), lang = $("#flang")?.value || "en";
    const list = items.filter((i) => (!d || i.domain === d) && (lang === "en" || kmap[i.id]) && (!q || (lang === "kri" ? kmap[i.id].question : i.question).toLowerCase().includes(q)));
    $("#ilist").innerHTML = list.map((i) => {
      const src = lang === "kri" ? kmap[i.id] : i;
      return `<div class="card" style="margin-bottom:10px"><div class="row"><strong>${esc(i.id)}</strong><span class="tag">${esc(i.domain)}</span><span class="tag ${i.status === "reviewed" ? "" : "warn"}">${esc(i.status)}</span>${i.krio_subset ? '<span class="tag">Krio subset</span>' : ""}</div>
      <p>${esc(src.question)}</p>${src.options.map((o, n) => `<div class="opt ${n === i.answer ? "key" : ""}">${"ABCD"[n]}. ${esc(o)}${n === i.answer ? " (key)" : ""}</div>`).join("")}
      <small class="lead">Source anchor: ${esc(i.source_anchor)}</small></div>`;
    }).join("") || "<p>No items match.</p>";
    $("#icount").textContent = `${list.length} items`;
  };
  main.innerHTML = `<h1>Item bank</h1><p class="lead">The key is shown so reviewers can check it. Items stay "draft" until a reviewer approves them.</p>
   <div class="row noprint"><select id="fdom" style="width:auto"><option value="">All domains</option>${domains.map((d) => `<option>${esc(d)}</option>`).join("")}</select>
   <select id="flang" style="width:auto"><option value="en">English</option><option value="kri">Krio (${krio.length})</option></select>
   <input id="fq" type="text" placeholder="Search text" class="grow"><span id="icount" class="lead"></span></div><div id="ilist" style="margin-top:12px"></div>`;
  ["fdom", "flang", "fq"].forEach((id) => ($("#" + id).oninput = draw));
  draw();
}

/* ---------- run ---------- */
function viewRun() {
  setBanner(null);
  const st = S.state, drafts = st.item_status.draft || 0;
  const banks = st.banks.map((b) => `<option value="${esc(b.name)}">${esc(b.label)}, ${b.n_items} items</option>`).join("");
  const models = st.models.map((m, i) => `<div class="card" style="margin-bottom:8px"><label class="chk"><input type="checkbox" class="msel" data-i="${i}"><span><strong>${esc(m.label)}</strong> <small class="lead">${esc(m.provider)} / ${esc(m.model)}</small></span></label>
     <input type="password" class="mkey" data-i="${i}" placeholder="API key (${esc(m.key_name)}), kept in memory only" autocomplete="off"></div>`).join("");
  $("#main").innerHTML = `<h1>New evaluation</h1><p class="lead">Runs the same protocol as the published benchmark: zero-shot, temperature 0, three shuffled option orders by default.</p>
  <div class="grid cols2"><div class="card"><h2>1. Item bank</h2><select id="bank">${banks}</select>
    <label class="chk"><input type="checkbox" id="mock"><span>Simulated run (random answers, no API key, for exploring the interface only)</span></label>
    ${drafts ? `<label class="chk"><input type="checkbox" id="drafts"><span>Provisional run: allow unapproved items (${drafts} draft). Results will be labelled provisional.</span></label>` : ""}
    <label for="rid">Run name</label><input id="rid" type="text" placeholder="for example pilot-1">
    <label for="reps">Repetitions (1 to 10)</label><input id="reps" type="number" min="1" max="10" value="3">
    <h2 style="margin-top:18px">Import your own item bank</h2>
    <p class="lead">CSV columns: id, domain, question, option_a, option_b, option_c, option_d, answer (A to D). Imported items are drafts unless you confirm they were reviewed.</p>
    <input id="bname" type="text" placeholder="Bank name"><textarea id="btext" rows="4" placeholder="Paste CSV here"></textarea>
    <label class="chk"><input type="checkbox" id="brev"><span>These items were reviewed and the answer key was checked by a qualified person</span></label>
    <button class="btn sec" id="bimp">Import</button><div id="bmsg"></div></div>
  <div class="card"><h2>2. Models</h2>${models}
    <details style="margin-top:8px"><summary>Add a model on any OpenAI-compatible endpoint (local or hosted)</summary>
      <label for="cl">Label</label><input id="cl" type="text" placeholder="local-model"><label for="cm">Model id</label><input id="cm" type="text">
      <label for="cu">Base URL</label><input id="cu" type="text" placeholder="http://127.0.0.1:11434/v1"><label for="ck">API key (optional)</label><input id="ck" type="password" autocomplete="off">
      <label class="chk"><input type="checkbox" id="cuse"><span>Include this model</span></label></details></div></div>
  <div class="row" style="margin-top:14px"><button class="btn" id="go">Start evaluation</button><button class="btn sec" id="stop" hidden>Stop</button></div>
  <div id="rmsg"></div><div id="prog" style="margin-top:10px"></div><pre class="log" id="log" hidden></pre>`;
  $("#bimp").onclick = async () => {
    try {
      const r = await api("/api/itembanks", { body: { name: $("#bname").value.trim(), text: $("#btext").value, format: "csv", confirm_reviewed: $("#brev").checked } });
      $("#bmsg").innerHTML = r.ok ? `<div class="note">Imported ${r.n_items} items.${r.warnings.length ? " Warnings: " + esc(r.warnings.join("; ")) : ""}</div>` : `<div class="note bad">${r.problems.map(esc).join("<br>")}</div>`;
      if (r.ok) { S.state = await api("/api/state"); $("#bank").innerHTML = S.state.banks.map((b) => `<option value="${esc(b.name)}">${esc(b.label)}, ${b.n_items} items</option>`).join(""); }
    } catch (e) { $("#bmsg").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
  };
  $("#go").onclick = startJob;
  $("#stop").onclick = () => S.job && api(`/api/jobs/${S.job}/stop`, { body: {} });
}

async function startJob() {
  const picked = [];
  document.querySelectorAll(".msel:checked").forEach((c) => picked.push({ label: S.state.models[+c.dataset.i].label, api_key: document.querySelector(`.mkey[data-i="${c.dataset.i}"]`).value }));
  if ($("#cuse").checked) picked.push({ custom: true, label: $("#cl").value.trim(), model: $("#cm").value.trim(), base_url: $("#cu").value.trim(), api_key: $("#ck").value, max_tokens: 16 });
  const body = { models: picked, bank: $("#bank").value, mock: $("#mock").checked, allow_drafts: !!$("#drafts")?.checked, reps: +$("#reps").value, run_id: $("#rid").value.trim() || undefined };
  if (body.mock && !picked.length) picked.push({ label: S.state.models[0].label });
  try {
    const r = await api("/api/jobs", { body });
    document.querySelectorAll(".mkey,#ck").forEach((i) => (i.value = ""));
    S.job = r.job_id; S.jobRun = r.run_id;
    $("#rmsg").innerHTML = ""; $("#go").disabled = true; $("#stop").hidden = false; $("#log").hidden = false;
    poll();
  } catch (e) { $("#rmsg").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
}

async function poll() {
  const j = await api(`/api/jobs/${S.job}`);
  $("#log").textContent = j.log.join("\n");
  $("#prog").innerHTML = Object.entries(j.progress).map(([k, v]) => `<div>${esc(k)}: ${v.calls} calls, ${v.failures} failed</div>`).join("");
  if (j.status === "running") { S.timer = setTimeout(poll, 1000); return; }
  $("#go").disabled = false; $("#stop").hidden = true;
  if (j.status === "done") {
    S.state = await api("/api/state"); S.sel = `local/${j.run_id}`;
    $("#rmsg").innerHTML = `<div class="note">Finished. <a href="#" id="open">Open dashboard</a></div>`;
    $("#open").onclick = (e) => { e.preventDefault(); go("dashboard"); };
  } else $("#rmsg").innerHTML = `<div class="note bad">${j.status === "stopped" ? "Stopped." : "Failed: " + esc(j.error)}</div>`;
}

/* ---------- help ---------- */
function viewHelp() {
  setBanner(null);
  $("#main").innerHTML = `<div class="help"><h1>Guide</h1>
  <h2>What this tool does</h2><p>It measures how accurately language models answer public health multiple-choice questions, in English and in a Krio subset, and reports uncertainty and known failure modes. It supports a pilot pre-deployment evaluation. It does not certify any tool for clinical or programme use.</p>
  <h2>How to read the dashboard</h2><ul>
  <li><strong>Accuracy</strong> is the mean over items of the share of correct answers across repetitions. The interval comes from resampling items 10,000 times (seeded), so it reflects item sampling, not model randomness.</li>
  <li><strong>Order consistency</strong> and <strong>letter share</strong> show whether the model follows content or position.</li>
  <li><strong>Domain cells</strong> are based on few items. Do not rank models on one domain.</li>
  <li><strong>Gap</strong> is English accuracy minus Krio accuracy on the same items. It is reported only when at least 15 paired items exist.</li>
  <li><strong>Key audit</strong> lists items where models agree against the key. A person decides whether the key or the question is at fault.</li></ul>
  <h2>Status labels</h2><ul><li><strong>SIMULATED</strong>: mock model, random answers.</li><li><strong>PROVISIONAL</strong>: some items are unapproved drafts.</li></ul>
  <h2>Privacy</h2><p>The app listens on this computer only. API keys you type are used for the run and are not written to disk. Questions are sent to the model provider you choose, so do not import items that contain patient information. Use a local OpenAI-compatible endpoint to keep everything on this computer.</p>
  <h2>Limits</h2><ul><li>Multiple-choice knowledge is a weak proxy for safe deployment. It does not test free-text answers, referral advice, local protocol fit or harm.</li><li>48 items give wide intervals. Models within a few points of each other cannot be separated.</li><li>Krio items are few and were reviewed by one reader.</li></ul></div>`;
}

/* ---------- shell ---------- */
async function render() {
  clearTimeout(S.timer);
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.view === S.view));
  try {
    if (S.view === "dashboard") await viewDashboard();
    else if (S.view === "items") await viewItems();
    else if (S.view === "run") viewRun();
    else viewHelp();
  } catch (e) { $("#main").innerHTML = `<div class="note bad">${esc(e.message)}</div>`; }
}
function go(v) { S.view = v; render(); $("#main").focus(); }
document.querySelectorAll("#nav button").forEach((b) => (b.onclick = () => go(b.dataset.view)));
api("/api/state").then((s) => { S.state = s; render(); }).catch((e) => ($("#main").textContent = e.message));
