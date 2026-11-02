// AdaptiveSched dashboard. Presentation only: every number comes from the API, which serves the
// files the experiment runner wrote. No scheduling or metric logic lives here.
"use strict";

const SLOTS = { fifo: 1, sjf: 2, adaptive: 3, easy_backfill: 4, srtf: 5, adaptive_multifactor: 6,
                amf_preemptive: 7, amf_fixed: 8 };  // same fixed order as analysis/style.py
const METRICS = [
  ["average_waiting_time", "Average waiting time", "lower"],
  ["average_turnaround_time", "Average turnaround time", "lower"],
  ["makespan", "Makespan", "lower"],
  ["cpu_utilization", "CPU utilization (%)", "higher"],
  ["bounded_slowdown", "Bounded slowdown (tau = 10)", "lower"],
  ["max_waiting_time", "Max waiting time", "lower"],
  ["fairness_index", "Fairness (Jain over slowdowns)", "higher"],
  ["throughput", "Throughput (jobs / time unit)", "higher"],
];
const TABLE_METRICS = [...METRICS.map(m => m[0]), "completed_jobs", "total_preemptions"];
const PAGE = 50;

const state = { policies: [], workloads: null, exps: [], exp: null, group: "", runId: "", run: null,
                job: null, sort: ["job_id", 1], page: 0, poll: null };

// ---- helpers -------------------------------------------------------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = v => v == null ? "" : typeof v === "number" && !Number.isInteger(v) ? v.toFixed(3) : String(v);
const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const color = s => css(SLOTS[s] ? `--s${SLOTS[s]}` : "--other");
const swatch = s => `<span class="swatch" style="background:${color(s)}"></span>`;
const badge = st => `<span class="badge ${esc(st)}">${esc(st)}</span>`;

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || `${r.status} ${r.statusText}`);
  return body;
}

function flash(msg, ok = false) {
  const f = $("#flash");
  f.textContent = msg; f.className = ok ? "flash ok" : "flash"; f.hidden = !msg;
  if (msg) window.scrollTo({ top: 0, behavior: "smooth" });
}

function table(cols, rows, { rowAttrs = () => "", sortable = false } = {}) {
  const head = cols.map(([k, label, num]) =>
    `<th class="${num ? "num" : ""} ${sortable ? "sort" : ""}" data-k="${esc(k)}">${esc(label)}${
      sortable && state.sort[0] === k ? (state.sort[1] > 0 ? " &#9650;" : " &#9660;") : ""}</th>`).join("");
  const body = rows.map(r => `<tr ${rowAttrs(r)}>${cols.map(([k, , num, render]) =>
    `<td class="${num ? "num" : ""}">${render ? render(r) : esc(fmt(r[k]))}</td>`).join("")}</tr>`).join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body || `<tr><td colspan="${cols.length}" class="muted">nothing yet</td></tr>`}</tbody></table>`;
}

// ---- routing ---------------------------------------------------------------------------
function route() {
  const [tab, id] = (location.hash.slice(1) || "overview").split("/");
  $$(".tab").forEach(s => s.hidden = s.id !== tab);
  $$("#tabs a").forEach(a => a.classList.toggle("active", a.dataset.tab === tab));
  if (id && (!state.exp || state.exp.id !== id)) selectExperiment(id);
  if (tab === "gantt") drawGantt();
}

// ---- data ------------------------------------------------------------------------------
async function refreshExperiments() {
  try {
    state.exps = await api("/api/experiments");
  } catch (e) { return flash(`Could not load experiments: ${e.message}`); }
  renderOverview(); renderExperimentList(); renderPickers();
  const active = state.exps.some(e => e.status === "queued" || e.status === "running");
  if (state.exp && state.exps.find(e => e.id === state.exp.id)?.status !== state.exp.status) {
    await selectExperiment(state.exp.id, true);
  } else if (state.exp && active) {
    const fresh = state.exps.find(e => e.id === state.exp.id);
    if (fresh) { state.exp.progress = fresh.progress; renderExperimentDetail(); }
  }
  clearTimeout(state.poll);
  if (active) state.poll = setTimeout(refreshExperiments, 1200);
}

async function selectExperiment(id, keepSelection = false) {
  try {
    state.exp = await api(`/api/experiments/${encodeURIComponent(id)}`);
  } catch (e) { return flash(e.message); }
  const groups = groupsOf(state.exp);
  if (!keepSelection || !groups.has(state.group)) state.group = groups.keys().next().value || "";
  renderExperimentDetail(); renderPickers(); renderResults();
  await pickFirstRun();
}

function groupsOf(exp) {
  const g = new Map();
  for (const r of exp?.rows || []) {
    const k = `${r.workload_id}@${r.cluster_cores}`;
    if (!g.has(k)) g.set(k, []);
    g.get(k).push(r);
  }
  return g;
}

async function pickFirstRun() {
  const rows = (groupsOf(state.exp).get(state.group) || []).filter(r => r.status === "ok");
  if (!rows.some(r => r.run_id === state.runId)) state.runId = rows[0]?.run_id || "";
  await loadRun();
}

async function loadRun() {
  state.run = null; state.page = 0; state.job = null;
  renderPickers();
  if (state.exp && state.runId) {
    try { state.run = await api(`/api/experiments/${state.exp.id}/runs/${state.runId}`); }
    catch (e) { flash(e.message); }
  }
  drawGantt(); renderJobs();
}

// ---- A. overview -----------------------------------------------------------------------
async function renderOverview() {
  let ov;
  try { ov = await api("/api/overview"); } catch (e) { return; }
  const tiles = [["Experiments", ov.total_experiments], ["Runs ok", ov.runs_ok], ["Runs failed", ov.runs_failed],
                 ["Policies", ov.policies.length], ["Workloads", ov.workloads],
                 ["Running / queued", (ov.by_status.running || 0) + (ov.by_status.queued || 0)]];
  $("#ov-tiles").innerHTML = tiles.map(([k, v]) => `<div class="tile"><div class="v">${esc(v)}</div><div class="k">${esc(k)}</div></div>`).join("");
  $("#ov-policies").innerHTML = state.policies.map(p =>
    `<li>${swatch(p.id)}<b>${esc(p.id)}</b> <span class="muted">${esc(p.name)}${p.preemptive_capable ? " &middot; can preempt" : ""}</span></li>`).join("");
  $("#ov-recent").innerHTML = table([
    ["created", "Created"], ["name", "Name", false, e => esc(e.name || e.id)],
    ["status", "Status", false, e => badge(e.status)],
    ["runs", "Runs ok / failed", true, e => e.status === "completed" ? `${e.runs_ok} / ${e.runs_failed}` : `${e.progress[0]} / ${e.progress[1]} done`],
  ], ov.recent, { rowAttrs: e => `class="click" data-go="experiments/${esc(e.id)}"` });
}

// ---- B. configuration ------------------------------------------------------------------
function paramInputs(policy, prefix) {
  const presets = Object.keys(policy.presets || {});
  const picker = presets.length
    ? `<label>Preset <select data-preset="${esc(prefix)}" data-policy="${esc(policy.id)}"><option value="">defaults</option>${
        presets.map(n => `<option>${esc(n)}</option>`).join("")}</select></label>` : "";
  return picker + policy.params.map(p => {
    const name = `${prefix}:${p.name}`;
    if (p.type === "bool") {
      const label = p.name === "preemptive" ? "preemptive execution" : p.name;
      return `<label class="inline"><input type="checkbox" name="${esc(name)}" ${p.default ? "checked" : ""}> ${esc(label)}</label>`;
    }
    const numeric = p.type === "int" || p.type === "float";  // text, not number: "inf" must be typeable
    return `<label>${esc(p.name)} <input name="${esc(name)}" ${numeric ? 'inputmode="decimal"' : ""} value="${esc(p.default)}" data-type="${esc(p.type)}"></label>`;
  }).join("");
}

// Fill a policy's parameter fields from one of its presets ("" = the policy's defaults).
function applyPreset(prefix, policyId, presetName) {
  const f = $("#cfg"), policy = state.policies.find(x => x.id === policyId);
  const values = presetName ? policy.presets[presetName] : {};
  for (const p of policy.params) {
    const el = f.elements[`${prefix}:${p.name}`];
    const v = p.name in values ? values[p.name] : p.default;
    if (!el) continue;
    if (p.type === "bool") el.checked = !!v; else el.value = String(v);
  }
  if (prefix === `p:${policyId}` && presetName) f.querySelector(`[name=policy][value="${policyId}"]`).checked = true;
  updateSummary();
}

function renderConfigure() {
  const w = state.workloads;
  $("#cfg-synth").innerHTML = w.synthetic.map(s =>
    `<label><input type="checkbox" name="synth" value="${esc(s.name)}" ${s.name === "heavy" ? "checked" : ""}>
     <span><b>${esc(s.name)}</b> <span class="muted small">offered load ${esc(s.offered_load)}; ${esc(s.description)}</span></span></label>`).join("");
  $("#cfg-csv").innerHTML = w.csv.map(c =>
    `<label><input type="checkbox" name="csv" value="${esc(c.path)}" data-cores="${esc(c.cluster_cores ?? "")}">
     <span>CSV <b>${esc(c.name)}</b>${c.cluster_cores ? ` <span class="muted small">${esc(c.cluster_cores)} CPU cores</span>` : ""}</span></label>`).join("");
  // a real log only makes sense on its own machine size: ticking it sets the cluster's CPU cores
  $$("#cfg-csv [name=csv]").forEach(c => c.addEventListener("change", () => {
    if (c.checked && c.dataset.cores) { $("#cfg").elements.cluster_cores.value = c.dataset.cores; updateSummary(); }
  }));
  $("#cfg-policies").innerHTML = state.policies.map(p => `
    <div class="policy">
      <header><label class="inline"><input type="checkbox" name="policy" value="${esc(p.id)}" ${["fifo", "sjf", "adaptive_multifactor"].includes(p.id) ? "checked" : ""}>
        ${swatch(p.id)}<b>${esc(p.id)}</b></label><span class="muted small">${esc(p.name)}${p.preemptive_capable ? " &middot; supports preemption" : ""}</span></header>
      <div class="doc">${esc(p.doc.split("\n\n")[0])}</div>
      ${p.params.length ? `<div class="params">${paramInputs(p, `p:${p.id}`)}</div>` : ""}
    </div>`).join("");
  updateSummary();
}

let variantCount = 0;
function addVariant() {
  const i = ++variantCount;
  const div = document.createElement("div");
  div.className = "policy variant";
  div.innerHTML = `<header>
      <label>Variant label <input name="vlabel" value="variant_${i}" pattern="[A-Za-z0-9_.-]+"></label>
      <label>Runs policy <select name="vbase">${state.policies.filter(p => p.params.length).map(p => `<option>${esc(p.id)}</option>`).join("")}</select></label>
      <button type="button" class="ghost small" data-remove>remove</button></header>
    <div class="params"></div>`;
  const fill = () => {
    const p = state.policies.find(x => x.id === $("[name=vbase]", div).value);
    $(".params", div).innerHTML = paramInputs(p, `v${i}`);
  };
  $("[name=vbase]", div).addEventListener("change", fill);
  $("[data-remove]", div).addEventListener("click", () => { div.remove(); updateSummary(); });
  div.dataset.i = i;
  $("#cfg-variants").append(div);
  fill(); updateSummary();
}

function readParams(form, prefix, policy) {
  const out = {};
  for (const p of policy.params) {
    const el = form.elements[`${prefix}:${p.name}`];
    if (!el) continue;
    const s = el.value.trim();
    if (p.type === "bool") out[p.name] = el.checked;
    else if (el.dataset.type === "int" || el.dataset.type === "float") {
      if (/^inf(inity)?$/i.test(s)) { out[p.name] = "inf"; continue; }  // JSON has no infinity; the API converts it
      const n = Number(s);
      if (s === "" || Number.isNaN(n)) throw new Error(`${policy.id} ${p.name}: "${s}" is not a number`);
      out[p.name] = n;
    } else out[p.name] = s;
  }
  return out;
}

function buildRequest() {
  const f = $("#cfg");
  const n = parseInt(f.elements.n_jobs.value, 10);
  const seeds = f.elements.seeds.value.split(",").map(s => s.trim()).filter(Boolean).map(Number);
  const workloads = [
    ...$$("[name=synth]:checked", f).map(c => `synth:${c.value}:n=${n}:seed=${seeds[0] ?? 0}`),
    ...$$("[name=csv]:checked", f).map(c => c.value),
  ];
  const strategies = [], strategy_params = {}, variants = {};
  for (const c of $$("[name=policy]:checked", f)) {
    const p = state.policies.find(x => x.id === c.value);
    strategies.push(p.id);
    if (p.params.length) strategy_params[p.id] = readParams(f, `p:${p.id}`, p);
  }
  for (const v of $$(".variant", f)) {
    const label = $("[name=vlabel]", v).value.trim();
    const p = state.policies.find(x => x.id === $("[name=vbase]", v).value);
    strategies.push(label);
    variants[label] = { strategy: p.id, params: readParams(f, `v${v.dataset.i}`, p) };
  }
  const body = { name: f.elements.name.value.trim(), cluster_cores: parseInt(f.elements.cluster_cores.value, 10),
                 workloads, strategies, strategy_params, seeds };
  if (Object.keys(variants).length) body.variants = variants;
  return body;
}

function updateSummary() {
  if (!state.workloads) return;
  let b;
  try { b = buildRequest(); } catch (e) { $("#cfg-summary").textContent = e.message; return; }
  const synth = b.workloads.filter(w => w.startsWith("synth:")).length;
  const runs = (synth * Math.max(1, b.seeds.length) + (b.workloads.length - synth)) * b.strategies.length;
  $("#cfg-summary").textContent = `${b.workloads.length} workload(s) x ${b.strategies.length} strategy configuration(s)` +
    `${b.seeds.length > 1 ? ` x ${b.seeds.length} seeds` : ""} = ${runs} run(s)`;
}

async function submitConfig(ev) {
  ev.preventDefault();
  let b;
  try { b = buildRequest(); } catch (e) { return flash(`Not submitted: ${e.message}`); }
  if (!b.workloads.length) return flash("Select at least one workload.");
  if (!b.strategies.length) return flash("Select at least one scheduling policy.");
  if (!(b.cluster_cores > 0)) return flash("Cluster CPU cores must be a positive integer.");
  if (b.seeds.some(s => !Number.isInteger(s) || s < 0)) return flash("Seeds must be non-negative integers.");
  const btn = $("#cfg button[type=submit]");
  btn.disabled = true;
  try {
    const e = await api("/api/experiments", { method: "POST", body: JSON.stringify(b) });
    flash(`Experiment ${e.id} queued (${e.progress[1]} runs).`, true);
    location.hash = `experiments/${e.id}`;
    await refreshExperiments();
  } catch (e) { flash(`Not submitted: ${e.message}`); }
  finally { btn.disabled = false; }
}

// ---- C. execution and G. history -------------------------------------------------------
function renderExperimentDetail() {
  const e = state.exp, box = $("#exp-detail");
  if (!e) { box.hidden = true; return; }
  box.hidden = false;
  const [done, total] = e.progress;
  const failed = (e.rows || []).filter(r => r.status === "failed");
  box.innerHTML = `<h2>${esc(e.name || "Experiment")} ${badge(e.status)}</h2>
    <dl class="kv">
      <dt>Experiment id</dt><dd>${esc(e.id)}</dd>
      <dt>Progress</dt><dd><div class="bar" title="${done} of ${total} runs"><i style="width:${total ? 100 * done / total : 0}%"></i></div> ${done} of ${total} runs</dd>
      <dt>Strategies</dt><dd>${e.request.strategies.map(s => swatch(s) + esc(s)).join(", ")}</dd>
      <dt>Workloads</dt><dd>${e.request.workloads.map(esc).join(", ")}${e.request.seeds?.length ? ` (seeds ${e.request.seeds.join(", ")})` : ""}</dd>
      <dt>Cluster</dt><dd>${esc(e.request.cluster_cores)} CPU cores</dd>
      <dt>Created / finished</dt><dd>${esc(e.created)} / ${esc(e.finished || "-")}</dd>
      <dt>Engine</dt><dd>${esc(e.manifest?.engine_versions?.join(", ") || e.engine)}</dd>
      ${e.error ? `<dt>Error</dt><dd>${esc(e.error)}</dd>` : ""}
    </dl>
    ${failed.length ? `<h2>Failed runs (${failed.length})</h2>` + table([["strategy", "Strategy"], ["workload_id", "Workload"], ["error", "Error"]], failed) : ""}
    <details><summary>Saved configuration (reproducible)</summary><pre>${esc(JSON.stringify(e.request, null, 2))}</pre></details>
    <div class="row end">
      <button type="button" class="ghost" data-go="results/${esc(e.id)}" ${e.status === "completed" ? "" : "disabled"}>View results</button>
      <button type="button" data-rerun="${esc(e.id)}">Rerun with this configuration</button>
    </div>`;
}

function renderExperimentList() {
  $("#exp-list").innerHTML = table([
    ["created", "Created"], ["name", "Name", false, e => esc(e.name || "-")], ["id", "Id"],
    ["status", "Status", false, e => badge(e.status)],
    ["progress", "Progress", false, e => `<div class="bar"><i style="width:${e.progress[1] ? 100 * e.progress[0] / e.progress[1] : 0}%"></i></div>`],
    ["runs", "Ok / failed", true, e => e.status === "completed" ? `${e.runs_ok} / ${e.runs_failed}` : ""],
    ["strategies", "Strategies", false, e => e.request.strategies.map(esc).join(", ")],
    ["act", "", false, e => `<button type="button" class="small ghost" data-rerun="${esc(e.id)}">rerun</button>`],
  ], state.exps, { rowAttrs: e => `class="click ${state.exp?.id === e.id ? "sel" : ""}" data-go="experiments/${esc(e.id)}"` });
}

async function rerun(id) {
  try {
    const e = await api(`/api/experiments/${encodeURIComponent(id)}/rerun`, { method: "POST" });
    flash(`Rerun queued as ${e.id}. Identical configuration, so identical results are expected.`, true);
    location.hash = `experiments/${e.id}`;
    await refreshExperiments();
  } catch (err) { flash(err.message); }
}

// ---- pickers shared by D, E, F ---------------------------------------------------------
function renderPickers() {
  const done = state.exps.filter(e => e.status === "completed");
  const expOpts = done.map(e => `<option value="${esc(e.id)}" ${state.exp?.id === e.id ? "selected" : ""}>${esc(e.name || e.id)} (${esc(e.id)})</option>`).join("")
    || `<option value="">no completed experiments yet</option>`;
  const groups = [...groupsOf(state.exp).keys()];
  const groupOpts = groups.map(g => `<option value="${esc(g)}" ${g === state.group ? "selected" : ""}>${esc(g.replace(/@(\d+)$/, " - $1 CPU cores"))}</option>`).join("");
  const runs = (groupsOf(state.exp).get(state.group) || []);
  const runOpts = runs.map(r => `<option value="${esc(r.run_id)}" ${r.run_id === state.runId ? "selected" : ""} ${r.status === "ok" ? "" : "disabled"}>${esc(r.strategy)}${r.status === "ok" ? "" : " (failed)"}</option>`).join("");
  $$("#res-exp, .pick-exp").forEach(s => s.innerHTML = expOpts);
  $$("#res-group, .pick-group").forEach(s => s.innerHTML = groupOpts);
  $$(".pick-run").forEach(s => s.innerHTML = runOpts);
}

// ---- D. results ------------------------------------------------------------------------
function renderResults() {
  const rows = groupsOf(state.exp).get(state.group) || [];
  if (!rows.length) {
    $("#res-table").innerHTML = `<p class="muted">Pick a completed experiment.</p>`;
    $("#res-charts").innerHTML = ""; $("#res-export").innerHTML = ""; return;
  }
  $("#res-table").innerHTML = table([
    ["strategy", "Strategy", false, r => swatch(r.strategy) + esc(r.strategy)],
    ["status", "Status", false, r => r.status === "ok" ? "ok" : `<b>failed</b>: ${esc(r.error)}`],
    ...TABLE_METRICS.map(m => [m, m.replaceAll("_", " "), true]),
  ], rows);
  $("#res-charts").innerHTML = METRICS.map(([m, label, better]) =>
    `<div class="chart"><h3>${esc(label)} <span class="muted small">(${better} is better)</span></h3>${barChart(rows, m)}<div class="tip" hidden></div></div>`).join("");
  $$("#res-charts .chart").forEach(c => {
    const tip = $(".tip", c);
    c.addEventListener("mousemove", ev => {
      const t = ev.target.closest("[data-tip]");
      if (!t) { tip.hidden = true; return; }
      const box = c.getBoundingClientRect();
      tip.textContent = t.dataset.tip; tip.hidden = false;
      tip.style.left = `${Math.min(ev.clientX - box.left + 10, box.width - 160)}px`;
      tip.style.top = `${ev.clientY - box.top - 30}px`;
    });
    c.addEventListener("mouseleave", () => tip.hidden = true);
  });
  const id = state.exp.id;
  $("#res-export").innerHTML = `<p><a href="/api/experiments/${id}/compare.csv">Comparison table (CSV), every workload</a></p>` +
    table([["strategy", "Strategy"],
           ["files", "Per-job records / summary", false, r => r.status === "ok"
             ? `<a href="/api/experiments/${id}/runs/${r.run_id}/records.csv">records.csv</a> &middot; <a href="/api/experiments/${id}/runs/${r.run_id}/summary.json">summary.json</a>` : "failed: no files"]], rows) +
    `<p class="small">Charts (PNG, every workload and seed): ${METRICS.map(([m, l]) => `<a href="/api/experiments/${id}/plots/${m}.png" target="_blank" rel="noopener">${esc(l)}</a>`).join(" &middot; ")}</p>`;
}

function barChart(rows, metric) {
  const W = 340, H = 220, L = 46, B = 74, T = 8;
  const short = s => s.length > 13 ? `${s.slice(0, 12)}…` : s;  // full name in the hover tooltip and table
  const ok = rows.filter(r => r.status === "ok" && r[metric] != null);
  const max = Math.max(...ok.map(r => r[metric]), 0) || 1;
  const step = (W - L - 8) / rows.length, bw = Math.min(28, step * 0.62);
  const y = v => T + (H - T - B) * (1 - v / max);
  const ticks = [0, 0.5, 1].map(f => f * max);
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(metric)} by strategy">`;
  for (const t of ticks) svg += `<line class="gridline" x1="${L}" x2="${W - 4}" y1="${y(t)}" y2="${y(t)}"/><text x="${L - 4}" y="${y(t) + 3}" text-anchor="end">${esc(fmt(+t.toPrecision(3)))}</text>`;
  rows.forEach((r, i) => {
    const cx = L + step * i + step / 2;
    if (r.status === "ok" && r[metric] != null) {
      const top = y(r[metric]), h = Math.max(H - B - top, 0.5);
      // bar with rounded data end (4px) anchored square on the baseline
      svg += `<path d="M${cx - bw / 2},${H - B} v${-(h - Math.min(4, h))} q0,${-Math.min(4, h)} ${Math.min(4, bw / 2)},${-Math.min(4, h)} h${bw - 2 * Math.min(4, bw / 2)} q${Math.min(4, bw / 2)},0 ${Math.min(4, bw / 2)},${Math.min(4, h)} v${h - Math.min(4, h)} z" fill="${color(r.strategy)}"/>`;
      svg += `<rect x="${cx - step / 2}" y="${T}" width="${step}" height="${H - T - B}" fill="transparent" data-tip="${esc(r.strategy)}: ${esc(fmt(r[metric]))}"/>`;
    } else {
      svg += `<text x="${cx}" y="${H - B - 4}" text-anchor="middle">failed</text>`;
    }
    svg += `<text transform="translate(${cx - 3},${H - B + 10}) rotate(40)"><title>${esc(r.strategy)}</title>${esc(short(r.strategy))}</text>`;
  });
  return svg + `<line class="axis" x1="${L}" x2="${W - 4}" y1="${H - B}" y2="${H - B}"/></svg>`;
}

// ---- E. Gantt --------------------------------------------------------------------------
let ganttHits = [];
function drawGantt() {
  const cv = $("#gantt-canvas"), cap = $("#gantt-caption");
  ganttHits = [];
  const run = state.run;
  if (!run) { cv.width = cv.height = 0; cap.textContent = "Pick a completed experiment, workload and strategy."; return; }
  const s = run.summary, cores = s.cluster_cores;
  if (!run.lanes) { cv.width = cv.height = 0; cap.textContent = `Gantt drawn for at most ${run.gantt_max_cores} CPU cores; this run has ${cores}. Use the job table.`; return; }
  cap.textContent = `${s.strategy} on ${s.workload}, ${cores} CPU cores: average waiting time ${fmt(s.average_waiting_time)}, max ${fmt(s.max_waiting_time)}, ${s.total_preemptions} preemption(s).`;
  const recs = new Map(run.records.map(r => [String(r.job_id), r]));
  const t0 = Math.min(...run.records.map(r => r.arrival_time)), t1 = Math.max(...run.records.map(r => r.finish_time));
  const wrap = $("#gantt-wrap"), dpr = window.devicePixelRatio || 1;
  const row = cores <= 16 ? 16 : cores <= 32 ? 10 : cores <= 64 ? 6 : cores <= 200 ? 3 : Math.max(0.5, 1000 / cores), L = 40, B = 28;
  const W = Math.max(wrap.clientWidth, 640), H = cores * row + B + 6;
  cv.width = W * dpr; cv.height = H * dpr; cv.style.width = `${W}px`; cv.style.height = `${H}px`;
  const g = cv.getContext("2d");
  g.scale(dpr, dpr);
  const x = t => L + (W - L - 10) * (t - t0) / Math.max(t1 - t0, 1);
  g.fillStyle = css("--surface"); g.fillRect(0, 0, W, H);
  g.fillStyle = css("--idle"); g.fillRect(x(t0), 4, x(t1) - x(t0), cores * row);
  const fill = color(s.strategy), hatch = hatchPattern(g, fill);
  for (const [jid, a, b, lane, n] of run.lanes) {
    const rec = recs.get(String(jid)), resumed = rec && a !== rec.start_time;
    const rx = x(a), ry = 4 + (cores - lane - n) * row, rw = Math.max(x(b) - x(a), 1), rh = n * row;
    g.fillStyle = resumed ? hatch : fill; g.fillRect(rx, ry, rw, rh);
    if (rh >= 4 && rw >= 4) { g.strokeStyle = css("--surface"); g.lineWidth = 1; g.strokeRect(rx + 0.5, ry + 0.5, rw - 1, rh - 1); }
    ganttHits.push({ rx, ry, rw, rh, rec, a, b });
  }
  g.fillStyle = css("--text-2"); g.font = "10px system-ui, sans-serif"; g.textAlign = "right";
  for (let c = 0; c <= cores; c += Math.max(1, Math.round(cores / 8))) g.fillText(String(c), L - 6, 4 + (cores - c) * row + 3);
  g.textAlign = "center";
  for (let i = 0; i <= 6; i++) { const t = t0 + (t1 - t0) * i / 6; g.fillText(String(Math.round(t)), x(t), H - 10); }
}

function hatchPattern(g, base) {
  const p = document.createElement("canvas"); p.width = p.height = 6;
  const c = p.getContext("2d");
  c.fillStyle = base; c.fillRect(0, 0, 6, 6);
  c.strokeStyle = css("--surface"); c.lineWidth = 1.2;
  c.beginPath(); c.moveTo(0, 6); c.lineTo(6, 0); c.stroke();
  return g.createPattern(p, "repeat");
}

function ganttHit(ev) {
  const r = $("#gantt-canvas").getBoundingClientRect(), px = ev.clientX - r.left, py = ev.clientY - r.top;
  return ganttHits.find(h => px >= h.rx && px <= h.rx + h.rw && py >= h.ry && py <= h.ry + h.rh);
}

// ---- F. jobs ---------------------------------------------------------------------------
const JOB_COLS = [["job_id", "Job"], ["arrival_time", "Arrival", true], ["start_time", "First start", true],
  ["finish_time", "Finish", true], ["runtime", "Runtime", true], ["waiting_time", "Waiting", true],
  ["turnaround_time", "Turnaround", true], ["required_cores", "CPU cores", true],
  ["preemption_count", "Preemptions", true],
  ["execution_segments", "Execution segments", false, r => esc(r.execution_segments.map(([a, b]) => `[${a}, ${b})`).join(" "))]];

function renderJobs() {
  const run = state.run;
  if (!run) { $("#job-table").innerHTML = `<p class="muted">Pick a completed experiment, workload and strategy.</p>`; $("#job-pager").innerHTML = $("#job-detail").innerHTML = ""; return; }
  const q = $("#job-filter").value.trim().toLowerCase(), pre = $("#job-preempted").checked;
  const [k, dir] = state.sort;
  const rows = run.records.filter(r => (!q || String(r.job_id).toLowerCase().includes(q)) && (!pre || r.preemption_count > 0))
    .sort((a, b) => (typeof a[k] === "number" && typeof b[k] === "number" ? a[k] - b[k] : String(a[k]).localeCompare(String(b[k]), undefined, { numeric: true })) * dir);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  state.page = Math.min(state.page, pages - 1);
  $("#job-table").innerHTML = table(JOB_COLS, rows.slice(state.page * PAGE, (state.page + 1) * PAGE),
    { sortable: true, rowAttrs: r => `class="click ${state.job === String(r.job_id) ? "sel" : ""}" data-job="${esc(r.job_id)}"` });
  $("#job-pager").innerHTML = `<span class="muted">${rows.length} of ${run.records.length} jobs &middot; page ${state.page + 1} of ${pages}</span>
    <button type="button" class="small ghost" data-page="-1" ${state.page ? "" : "disabled"}>previous</button>
    <button type="button" class="small ghost" data-page="1" ${state.page < pages - 1 ? "" : "disabled"}>next</button>`;
  const j = state.job != null && run.records.find(r => String(r.job_id) === state.job);
  $("#job-detail").innerHTML = j ? `<h2>Job ${esc(j.job_id)} - ${esc(run.summary.strategy)}</h2><dl class="kv">${
    JOB_COLS.map(([key, label, , render]) => `<dt>${esc(label)}</dt><dd>${render ? render(j) : esc(j[key])}</dd>`).join("")}
    <dt>Checks</dt><dd>waiting = finish - arrival - runtime: ${j.waiting_time === j.finish_time - j.arrival_time - j.runtime ? "ok" : "FAILED"};
    segments sum to runtime: ${j.execution_segments.reduce((s, [a, b]) => s + b - a, 0) === j.runtime ? "ok" : "FAILED"}</dd></dl>` : "";
}

// ---- wiring ----------------------------------------------------------------------------
document.addEventListener("click", ev => {
  const go = ev.target.closest("[data-go]");
  const re = ev.target.closest("[data-rerun]");
  if (re) { ev.stopPropagation(); return rerun(re.dataset.rerun); }
  if (go && !go.disabled) location.hash = go.dataset.go;
  const th = ev.target.closest("#job-table th.sort");
  if (th) { state.sort = [th.dataset.k, state.sort[0] === th.dataset.k ? -state.sort[1] : 1]; renderJobs(); }
  const tr = ev.target.closest("#job-table tr[data-job]");
  if (tr) { state.job = tr.dataset.job; renderJobs(); }
  const pg = ev.target.closest("[data-page]");
  if (pg) { state.page += +pg.dataset.page; renderJobs(); }
});
document.addEventListener("change", async ev => {
  const t = ev.target;
  if (t.matches("#res-exp, .pick-exp") && t.value) { location.hash = `${location.hash.slice(1).split("/")[0]}/${t.value}`; }
  else if (t.matches("#res-group, .pick-group")) { state.group = t.value; renderResults(); renderPickers(); await pickFirstRun(); }
  else if (t.matches(".pick-run")) { state.runId = t.value; await loadRun(); }
  else if (t.matches("#job-preempted")) { state.page = 0; renderJobs(); }
  else if (t.matches("select[data-preset]")) applyPreset(t.dataset.preset, t.dataset.policy, t.value);
  if (t.closest("#cfg")) updateSummary();
});
$("#cfg").addEventListener("input", updateSummary);
$("#cfg").addEventListener("submit", submitConfig);
$("#add-variant").addEventListener("click", addVariant);
$("#job-filter").addEventListener("input", () => { state.page = 0; renderJobs(); });
const cv = $("#gantt-canvas"), tip = $("#gantt-tip");
cv.addEventListener("mousemove", ev => {
  const h = ganttHit(ev);
  if (!h) { tip.hidden = true; cv.style.cursor = ""; return; }
  const r = h.rec, w = $("#gantt-wrap").getBoundingClientRect();
  cv.style.cursor = "pointer";
  tip.innerHTML = `<b>job ${esc(r.job_id)}</b> segment [${h.a}, ${h.b})<br>arrival ${r.arrival_time}, waiting ${r.waiting_time}, ${r.required_cores} CPU core(s)<br>runtime ${r.runtime}, preemptions ${r.preemption_count}`;
  tip.hidden = false;
  tip.style.left = `${Math.min(ev.clientX - w.left + 12, w.width - 220)}px`; tip.style.top = `${ev.clientY - w.top + 12}px`;
});
cv.addEventListener("mouseleave", () => tip.hidden = true);
cv.addEventListener("click", ev => { const h = ganttHit(ev); if (h) { state.job = String(h.rec.job_id); location.hash = `jobs/${state.exp.id}`; renderJobs(); } });
window.addEventListener("hashchange", route);
window.addEventListener("resize", () => { if (!$("#gantt").hidden) drawGantt(); });

(async function init() {
  try {
    [state.policies, state.workloads] = await Promise.all([api("/api/policies"), api("/api/workloads")]);
  } catch (e) { return flash(`The API is not reachable: ${e.message}`); }
  renderConfigure();
  await refreshExperiments();
  if (!location.hash.includes("/")) {
    const last = state.exps.find(e => e.status === "completed");
    if (last) await selectExperiment(last.id);
  }
  route();
})();
