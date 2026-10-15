"""Self-contained, presentation-ready HTML report for a Dependency Exit Capsule.

Editorial layout: masthead -> summary (headline figures + plain paragraph) ->
charts (risk profile, test results before/after, issues by type, version age)
-> key findings -> overview table -> appendix with full evidence.
No external assets; prints cleanly. Team name: DEPEXIT_TEAM (default "Travis Tanner").
"""
from __future__ import annotations

import html
import json
import os

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dependency Exit Capsule — __TEAM__</title>
<style>
:root{
  --paper:#fcfcfb; --band:#f3f3f0; --ink:#16181d; --ink2:#4b505a; --mute:#80858f; --rule:#dcdcd6; --rule2:#ecece7;
  --accent:#1f3a5f;
  --good:#1e8a3a; --good-bar:#0ca30c; --crit:#c03535; --crit-bar:#d03b3b; --serious:#ec835a; --low:#b9bcc4; --none:#e3e4e8;
  --obs:#2a6db5; --ver:#1e8a3a; --ai:#6250d6; --series:#2a78d6; --series-soft:#9ec5f4;
  --serif:"Iowan Old Style","Charter","Source Serif Pro",Georgia,"Times New Roman",serif;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 var(--sans);font-variant-numeric:tabular-nums}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12.5px}
.wrap{max-width:1040px;margin:0 auto;padding:0 28px}
/* masthead */
.mast{border-bottom:1px solid var(--ink);padding:26px 0 14px;display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px}
.brand .mark{width:30px;height:30px;background:var(--accent);display:grid;place-items:center;color:#fff;font:700 13px/1 var(--sans);letter-spacing:.02em}
.brand .name{font:700 15px/1.1 var(--sans);letter-spacing:.22em;text-transform:uppercase}
.brand .name small{display:block;font-weight:500;letter-spacing:.08em;color:var(--mute);font-size:11px;margin-top:4px;text-transform:uppercase}
.mast .doc{font-size:12px;color:var(--mute);text-align:right;letter-spacing:.04em}
.titleblock{padding:44px 0 30px;border-bottom:1px solid var(--rule)}
.titleblock h1{font:600 46px/1.08 var(--serif);margin:0 0 12px;letter-spacing:-.01em}
.titleblock .sub{font:400 19px/1.5 var(--serif);color:var(--ink2);margin:0;max-width:760px}
.facts{display:grid;grid-template-columns:repeat(5,auto);justify-content:start;gap:6px 36px;margin-top:24px;font-size:13px}
.facts dt{color:var(--mute);font-size:11px;letter-spacing:.08em;text-transform:uppercase}
.facts dd{margin:2px 0 0;font-weight:600}
/* sections */
section{padding:40px 0;border-bottom:1px solid var(--rule)}
.sechead{display:grid;grid-template-columns:56px 1fr;align-items:baseline;margin-bottom:22px}
.num{font:600 13px/1 var(--sans);color:var(--mute);letter-spacing:.06em}
h2{font:600 27px/1.2 var(--serif);margin:0;letter-spacing:-.005em}
.intro{grid-column:2;color:var(--ink2);margin:8px 0 0;max-width:720px}
h3{font:600 17px/1.3 var(--serif);margin:0 0 4px}
.cap{font-size:13px;color:var(--mute);margin:0 0 14px}
/* headline figures */
.figs{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;border-top:2px solid var(--ink);border-bottom:1px solid var(--rule)}
.fig{padding:18px 20px 18px 0}
.fig + .fig{padding-left:20px;border-left:1px solid var(--rule)}
.fig .v{font:600 44px/1 var(--sans);letter-spacing:-.02em}
.fig .v .of{font-size:24px;color:var(--mute);font-weight:500}
.fig .v .from{color:var(--mute);font-size:30px;font-weight:500}
.fig .v .arr{color:var(--mute);font-size:24px;margin:0 6px;font-weight:400}
.fig .l{font-size:13px;color:var(--ink2);margin-top:8px}
.fig.good .v .to{color:var(--good)}
.fig.bad .v{color:var(--crit)}
.story{font:400 19px/1.65 var(--serif);color:var(--ink);max-width:780px;margin:28px 0 0}
.story b{font-weight:600}
.tag{font:700 10px/1 var(--sans);letter-spacing:.1em;text-transform:uppercase;margin-left:6px;vertical-align:2px}
.t-OBSERVED{color:var(--obs)}.t-VERIFIED{color:var(--ver)}.t-AI{color:var(--ai)}
/* charts */
.charts{display:grid;grid-template-columns:1fr 1fr;gap:44px 56px}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.chart svg text{font-family:var(--sans);fill:var(--ink2);font-size:12px}
.chart svg .lbl{fill:var(--ink);font-weight:600}
.chart svg .muted{fill:var(--mute)}
.legend{display:flex;flex-wrap:wrap;gap:6px 18px;font-size:12.5px;color:var(--ink2);margin-top:10px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:-1px}
.wide{grid-column:1 / -1}
.tip{position:fixed;pointer-events:none;background:var(--ink);color:#fff;font-size:12px;padding:6px 9px;border-radius:4px;opacity:0;transition:opacity .1s;z-index:9;max-width:300px}
/* pipeline */
.pipe{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--rule)}
.step{padding:16px 16px 4px 0;position:relative}
.step + .step{padding-left:16px;border-left:1px solid var(--rule)}
.step .v{font:600 30px/1 var(--sans)}
.step .l{font-size:13px;color:var(--ink2);margin-top:6px}
/* findings */
.find{display:grid;grid-template-columns:180px 1fr auto;gap:18px;padding:16px 0;border-top:1px solid var(--rule2);cursor:pointer;align-items:baseline}
.find:hover .fname{text-decoration:underline}
.fname{font:600 18px/1.2 var(--serif)}
.fkind{font-weight:600;color:var(--ink)}
.fdetail{color:var(--ink2);font-size:14px}
.status{font-size:12px;font-weight:600;white-space:nowrap}
.st-verified{color:var(--good)}.st-unresolved,.st-failed,.st-error{color:var(--crit)}
.st-observed_only,.st-recommendation_only,.st-no_action{color:var(--mute)}
.sev{font-size:12px;font-weight:600;text-transform:capitalize}
.sev::before{content:"";display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;vertical-align:0}
.sev-high{color:var(--crit)}.sev-high::before{background:var(--crit-bar)}
.sev-medium{color:#b55a2b}.sev-medium::before{background:var(--serious)}
.sev-low{color:var(--ink2)}.sev-low::before{background:var(--low)}
.sev-none{color:var(--mute)}.sev-none::before{background:var(--none)}
/* table */
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);font-weight:600;padding:0 12px 10px 0;border-bottom:2px solid var(--ink)}
td{padding:11px 12px 11px 0;border-bottom:1px solid var(--rule2);vertical-align:top}
tr.row{cursor:pointer}tr.row:hover td{background:var(--band)}
td.dep{font-weight:600}
/* reading guide */
.guide{display:grid;grid-template-columns:repeat(3,1fr);gap:28px}
.guide p{margin:6px 0 0;color:var(--ink2);font-size:14px}
/* appendix */
.appendix{background:var(--band);border-top:3px double var(--rule);margin-top:0;padding:44px 0 60px}
.appendix .sechead{margin-bottom:12px}
.toolbar{display:flex;gap:6px;flex-wrap:wrap;margin:0 0 18px 56px}
.toolbar button{font:inherit;font-size:12.5px;background:transparent;border:1px solid var(--rule);color:var(--ink2);border-radius:3px;padding:5px 11px;cursor:pointer}
.toolbar button.on{border-color:var(--ink);color:var(--ink)}
details.dep{background:#fff;border:1px solid var(--rule);margin:0 0 -1px;font-size:14px}
details.dep>summary{list-style:none;cursor:pointer;padding:14px 18px;display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
details.dep>summary::-webkit-details-marker{display:none}
details.dep>summary .chev{color:var(--mute);display:inline-block;width:10px;transition:transform .15s}
details.dep[open]>summary .chev{transform:rotate(90deg)}
details.dep>summary .dname{font:600 17px/1.2 var(--serif)}
details.dep>summary .dmeta{color:var(--mute);font-size:12.5px;margin-left:auto}
.dbody{padding:2px 18px 20px 44px;border-top:1px solid var(--rule2)}
.blk{margin-top:18px}
.blk .bh{font:600 13px/1 var(--sans);letter-spacing:.04em;text-transform:uppercase;color:var(--ink2);margin-bottom:8px}
.blk ul,.blk ol{margin:4px 0;padding-left:18px}.blk li{margin:3px 0;color:var(--ink2)}
.blk p{margin:6px 0;color:var(--ink2)}
.runs{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--rule2);margin-top:6px}
.run{padding:10px 12px 8px 0}.run + .run{padding-left:12px;border-left:1px solid var(--rule2)}
.run .t{font-size:11.5px;color:var(--mute)}.run .v{font-weight:600;margin-top:2px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:24px}
pre{background:#fafaf8;border:1px solid var(--rule2);padding:12px;overflow:auto;max-height:340px;white-space:pre-wrap;margin:8px 0;font-size:12px}
.diff .a{color:var(--good)}.diff .d{color:var(--crit)}.diff .h{color:var(--obs)}
.small{font-size:12.5px;color:var(--mute)}
footer{padding:26px 0 40px;font-size:12px;color:var(--mute);display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
@media (max-width:860px){
  .figs,.charts,.guide,.two,.pipe{grid-template-columns:1fr}.fig + .fig,.step + .step{border-left:none;padding-left:0;border-top:1px solid var(--rule)}
  .facts{grid-template-columns:1fr 1fr}.find{grid-template-columns:1fr}.sechead{grid-template-columns:1fr}.intro{grid-column:1}
  .toolbar{margin-left:0}.runs{grid-template-columns:1fr 1fr}.titleblock h1{font-size:36px}
}
@media print{.toolbar{display:none}.appendix{page-break-before:always;background:#fff}details.dep{page-break-inside:avoid}.tip{display:none}}
</style></head><body>
<div class="tip" id="tip"></div>
<div class="wrap">
  <header class="mast">
    <div class="brand"><div class="mark">TT</div><div class="name">__TEAM__<small>Dependency Resilience · Track 1</small></div></div>
    <div class="doc" id="docmeta"></div>
  </header>
  <div class="titleblock">
    <h1>Dependency Exit Capsule</h1>
    <p class="sub" id="sub"></p>
    <dl class="facts" id="facts"></dl>
  </div>

  <section>
    <div class="sechead"><span class="num">01</span><h2>Summary</h2></div>
    <div class="figs" id="figs"></div>
    <p class="story" id="story"></p>
  </section>

  <section>
    <div class="sechead"><span class="num">02</span><h2>Results at a glance</h2>
      <p class="intro">Each chart is drawn directly from the observed and verified data in this capsule. Hover any bar or point for exact values.</p></div>
    <div class="charts">
      <div class="chart"><h3>Risk profile</h3><p class="cap">Dependencies by observed risk level<span class="tag t-OBSERVED">Observed</span></p><div id="c-risk"></div></div>
      <div class="chart"><h3>Test results, before and after</h3><p class="cap">The project's own test suite<span class="tag t-VERIFIED">Verified</span></p><div id="c-tests"></div></div>
      <div class="chart"><h3>Issues found, by type</h3><p class="cap">Number of risk indicators detected<span class="tag t-OBSERVED">Observed</span></p><div id="c-kinds"></div></div>
      <div class="chart"><h3>How out of date</h3><p class="cap">Release year of the installed version vs the latest release<span class="tag t-OBSERVED">Observed</span></p><div id="c-age"></div></div>
    </div>
  </section>

  <section>
    <div class="sechead"><span class="num">03</span><h2>From analysis to proof</h2>
      <p class="intro">How many dependencies made it through each stage of the pipeline.</p></div>
    <div class="pipe" id="pipe"></div>
  </section>

  <section id="combinedSec" hidden>
    <div class="sechead"><span class="num">04</span><h2>All verified fixes, applied together</h2>
      <p class="intro" id="combinedIntro"></p></div>
    <div id="combined"></div>
  </section>

  <section>
    <div class="sechead"><span class="num" id="numFind">05</span><h2>Key findings</h2>
      <p class="intro">The highest-risk dependencies. Select one to open its full evidence in the appendix.</p></div>
    <div id="findings"></div>
  </section>

  <section>
    <div class="sechead"><span class="num" id="numAll">06</span><h2>Every dependency</h2>
      <p class="intro">Sorted by observed risk.</p></div>
    <table><thead><tr><th>Dependency</th><th>Risk</th><th>Main issue</th><th>Proposed action</th><th>Result</th></tr></thead><tbody id="tbody"></tbody></table>
  </section>

  <section>
    <div class="sechead"><span class="num" id="numGuide">07</span><h2>How to read this report</h2>
      <p class="intro">Every statement carries a label showing where it came from. AI suggestions are never mixed with facts.</p></div>
    <div class="guide" id="guide"></div>
  </section>
</div>

<div class="appendix"><div class="wrap">
  <div class="sechead"><span class="num">A</span><h2>Appendix — detailed evidence</h2>
    <p class="intro">The full technical record for each dependency: risk indicators, usage locations, AI reasoning, fact-checks, executed test runs, patches and open concerns.</p></div>
  <div class="toolbar" id="toolbar"></div>
  <div id="details"></div>
  <div class="blk" style="margin:32px 0 0 56px"><div class="bh">Reproduce this evidence</div><pre id="repro"></pre></div>
  <footer id="footer"></footer>
</div></div>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nice = s => String(s || '').replaceAll('_', ' ');
const tag = p => `<span class="tag t-${p}">${p === 'AI' ? 'AI-generated' : p.toLowerCase()}</span>`;
const pass = s => s ? (s.passed||0) : 0, fail = s => s ? (s.failed||0) + (s.error||0) : 0, total = s => s ? (s.total||0) : 0;
const fmt = s => s && total(s) ? `${pass(s)} passed · ${fail(s)} failed` : 'not run';
const RISK = {high:0, medium:1, low:2, none:3};
const repo = D.target_repository, S = D.summary, C = D.combined_migration, caps = D.capsules;
const repoName = (repo.remote || repo.input || '').replace(/\.git$/,'').replace(/^https?:\/\/github.com\//,'');
const model = D.ai_model ? D.ai_model.name : null;

/* tooltip */
const tip = $('#tip');
function bindTips(root){ root.querySelectorAll('[data-tip]').forEach(el => {
  el.addEventListener('mousemove', e => { tip.textContent = el.dataset.tip; tip.style.opacity = 1;
    tip.style.left = Math.min(e.clientX + 14, innerWidth - 320) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; });
  el.addEventListener('mouseleave', () => tip.style.opacity = 0); }); }

/* header */
const date = (D.finished_at||'').slice(0,10);
$('#docmeta').innerHTML = `Report generated ${esc(date)}<br>${esc(D.generated_by.name)} ${esc(D.generated_by.version)}`;
$('#sub').textContent = `An AI-assisted review of the third-party dependencies in ${repoName}: what is at risk, what should replace it, and which replacements were proven to work by running the project's own tests.`;
$('#facts').innerHTML = [['Repository', repoName], ['Commit', (repo.commit||'').slice(0,10)], ['Python', D.python_target],
  ['AI model', model || 'none'], ['Model access', D.ai_model ? D.ai_model.provider : '—']]
  .map(([k,v]) => `<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('');

/* 01 summary */
const base = S.baseline_tests || {};
/* keep the project's own tests separate from the AI-written equivalence tests */
function splitRun(run){ const z = () => ({passed:0,failed:0,error:0,skipped:0,total:0}); const proj = z(), eqt = z();
  Object.entries((run && run.tests) || {}).forEach(([k,v]) => { const t = k.includes('test_depexit_') ? eqt : proj; t[v.status] = (t[v.status]||0) + 1; t.total++; });
  return [proj, eqt]; }
const [comb, eqComb] = (C && C.run && C.run.tests) ? splitRun(C.run) : [S.combined_tests, null];
const figs = [];
if (comb && total(comb)) figs.push(`<div class="fig good"><div class="v"><span class="from">${pass(base)}/${total(base)}</span><span class="arr">→</span><span class="to">${pass(comb)}/${total(comb)}</span></div><div class="l">project tests passing, before → after verified fixes${tag('VERIFIED')}</div></div>`);
else figs.push(`<div class="fig"><div class="v">${pass(base)}<span class="of">/${total(base)}</span></div><div class="l">tests passing with the original dependencies${tag('VERIFIED')}</div></div>`);
figs.push(`<div class="fig bad"><div class="v">${S.observed_risk.high}</div><div class="l">high-risk dependencies${tag('OBSERVED')}</div></div>`);
figs.push(`<div class="fig"><div class="v" style="color:var(--good)">${S.migrations_verified}<span class="of"> / ${S.migrations_attempted}</span></div><div class="l">AI fixes proven by tests${tag('VERIFIED')}</div></div>`);
figs.push(`<div class="fig"><div class="v">${S.dependencies_analysed}</div><div class="l">dependencies analysed${tag('OBSERVED')}</div></div>`);
$('#figs').innerHTML = figs.join('');
const subtle = caps.filter(c => (c.observed.risk_indicators||[]).some(i => ['manifest_conflict','private_api_usage','monkeypatching','undeclared_dependency','import_fails'].includes(i.kind))).map(c => c.dependency);
let story = `We examined <b>${S.dependencies_analysed} dependencies</b> of ${esc(repoName)}, reading its manifests and source code, checking every package on PyPI and running its test suite on Python ${esc(D.python_target)}. `;
story += `<b>${S.observed_risk.high} are high risk</b>${subtle.length ? `, including ${subtle.slice(0,5).map(esc).join(', ')}` : ''}. With the original dependencies, ${pass(base)} of ${total(base)} tests pass. `;
if (S.migrations_attempted) {
  story += `${esc(model || 'The AI')} proposed fixes for ${S.migrations_attempted} ${S.migrations_attempted===1?'dependency':'dependencies'}; each was applied in a clean environment and tested, and <b>${S.migrations_verified} ${S.migrations_verified===1?'was':'were'} proven to work</b>`;
  story += S.migrations_unresolved ? `, while ${S.migrations_unresolved} could not be verified and ${S.migrations_unresolved===1?'is':'are'} documented with the exact errors.` : '.';
  if (comb && total(comb)) story += ` With every verified fix applied together, <b>${pass(comb)} of ${total(comb)} of the project's own tests pass</b>`;
  if (eqComb && total(eqComb)) story += `, and all ${pass(eqComb)} of ${total(eqComb)} AI-written equivalence tests pass, each of which was first confirmed to pass on the original code.`;
  else if (comb && total(comb)) story += '.';
}
$('#story').innerHTML = story;

/* 02 charts — inline SVG, no libraries */
const W = 460;
function riskChart(){
  const order = [['high','High','var(--crit-bar)'],['medium','Medium','var(--serious)'],['low','Low','var(--low)'],['none','None','var(--none)']];
  const tot = S.dependencies_analysed || 1, gap = 2, H = 34; let x = 0, svg = '';
  order.forEach(([k,lab,col]) => { const n = S.observed_risk[k] || 0; if (!n) return;
    const w = (W - gap*3) * n / tot;
    svg += `<rect x="${x}" y="8" width="${w}" height="${H}" rx="3" fill="${col}" data-tip="${lab} risk: ${n} of ${tot} dependencies"/>`;
    if (w > 24) svg += `<text x="${x + w/2}" y="${8 + H/2 + 4}" text-anchor="middle" class="lbl" style="fill:${k==='high'?'#fff':'var(--ink)'}">${n}</text>`;
    x += w + gap; });
  $('#c-risk').innerHTML = `<svg viewBox="0 0 ${W} 50" role="img" aria-label="Risk profile">${svg}</svg>
    <div class="legend">${order.map(([k,lab,col]) => `<span><i style="background:${col}"></i>${lab} · ${S.observed_risk[k]||0}</span>`).join('')}</div>`;
}
function testsChart(){
  const rows = [['Original dependencies', base]];
  if (comb && total(comb)) rows.push(['After verified fixes', comb]);
  const max = Math.max(...rows.map(r => total(r[1])), 1), labelW = 150, bw = W - labelW - 70, H = 26, rowH = 46;
  let svg = '';
  rows.forEach(([lab, s], i) => { const y = i * rowH + 6, p = pass(s), f = fail(s);
    const wp = bw * p / max, wf = bw * f / max;
    svg += `<text x="0" y="${y + H/2 + 4}" class="lbl">${lab}</text>`;
    svg += `<rect x="${labelW}" y="${y}" width="${Math.max(wp,0)}" height="${H}" rx="3" fill="var(--good-bar)" data-tip="${lab}: ${p} passed"/>`;
    if (f) svg += `<rect x="${labelW + wp + 2}" y="${y}" width="${wf}" height="${H}" rx="3" fill="var(--crit-bar)" data-tip="${lab}: ${f} failed"/>`;
    svg += `<text x="${labelW + wp + (f ? wf + 2 : 0) + 8}" y="${y + H/2 + 4}">${p}/${total(s)}</text>`; });
  $('#c-tests').innerHTML = `<svg viewBox="0 0 ${W} ${rows.length * rowH}" role="img" aria-label="Test results">${svg}</svg>
    <div class="legend"><span><i style="background:var(--good-bar)"></i>Passed</span><span><i style="background:var(--crit-bar)"></i>Failed</span></div>
    <p class="small" style="margin-top:8px">Project's own tests only.${eqComb && total(eqComb) ? ` AI-written equivalence tests are counted separately (${pass(eqComb)}/${total(eqComb)} passing).` : ''}</p>`;
}
function kindsChart(){
  const counts = {};
  caps.forEach(c => (c.observed.risk_indicators||[]).forEach(i => counts[i.kind] = (counts[i.kind]||0) + 1));
  const rows = Object.entries(counts).sort((a,b) => b[1]-a[1]).slice(0, 8);
  if (!rows.length) { $('#c-kinds').innerHTML = '<p class="small">No issues found.</p>'; return; }
  const max = rows[0][1], labelW = 190, bw = W - labelW - 30, H = 16, rowH = 26;
  const svg = rows.map(([k,n], i) => { const y = i * rowH + 4, w = Math.max(bw * n / max, 4);
    return `<text x="${labelW - 10}" y="${y + H/2 + 4}" text-anchor="end">${esc(nice(k))}</text>
      <rect x="${labelW}" y="${y}" width="${w}" height="${H}" rx="3" fill="var(--series)" data-tip="${esc(nice(k))}: ${n}"/>
      <text x="${labelW + w + 6}" y="${y + H/2 + 4}" class="lbl">${n}</text>`; }).join('');
  $('#c-kinds').innerHTML = `<svg viewBox="0 0 ${W} ${rows.length * rowH + 4}" role="img" aria-label="Issues by type">${svg}</svg>`;
}
function ageChart(){
  const yr = s => s ? parseFloat(s.slice(0,4)) + (parseInt(s.slice(5,7)) - 1) / 12 : null;
  const rows = caps.map(c => { const d = c.observed.dependency_details, ir = d.installed_release || {};
      return {n: c.dependency, a: yr(ir.released), b: yr(d.latest_released), av: ir.version, bv: d.latest_version, ad: ir.released, bd: d.latest_released}; })
    .filter(r => r.a && r.b).sort((x,y) => x.a - y.a).slice(0, 12);
  if (!rows.length) { $('#c-age').innerHTML = '<p class="small">No release dates available.</p>'; return; }
  const lo = Math.floor(Math.min(...rows.map(r => r.a))), hi = Math.ceil(Math.max(...rows.map(r => r.b), new Date().getFullYear()));
  const labelW = 120, pw = W - labelW - 12, rowH = 22, top = 6, sx = v => labelW + pw * (v - lo) / Math.max(hi - lo, 1);
  let svg = '';
  for (let y = lo; y <= hi; y++) { if ((hi - lo) > 8 && y % 2) continue;
    svg += `<line x1="${sx(y)}" x2="${sx(y)}" y1="${top}" y2="${top + rows.length * rowH}" stroke="var(--rule2)"/>
      <text x="${sx(y)}" y="${top + rows.length * rowH + 14}" text-anchor="middle" class="muted" style="font-size:11px">${y}</text>`; }
  rows.forEach((r, i) => { const y = top + i * rowH + rowH/2;
    svg += `<text x="${labelW - 10}" y="${y + 4}" text-anchor="end">${esc(r.n)}</text>`;
    if (Math.abs(r.b - r.a) > 0.05) svg += `<line x1="${sx(r.a)}" x2="${sx(r.b)}" y1="${y}" y2="${y}" stroke="var(--series-soft)" stroke-width="2"/>`;
    svg += `<circle cx="${sx(r.a)}" cy="${y}" r="5" fill="var(--paper)" stroke="var(--ink2)" stroke-width="2" data-tip="${esc(r.n)} installed ${esc(r.av)} — released ${esc(r.ad)}"/>`;
    svg += `<circle cx="${sx(r.b)}" cy="${y}" r="5" fill="var(--series)" stroke="var(--paper)" stroke-width="2" data-tip="${esc(r.n)} latest ${esc(r.bv)} — released ${esc(r.bd)}"/>`; });
  $('#c-age').innerHTML = `<svg viewBox="0 0 ${W} ${top + rows.length * rowH + 20}" role="img" aria-label="Version age">${svg}</svg>
    <div class="legend"><span><i style="background:var(--paper);border:2px solid var(--ink2);border-radius:50%;width:8px;height:8px"></i>Installed version released</span><span><i style="background:var(--series);border-radius:50%"></i>Latest release</span></div>`;
}
riskChart(); testsChart(); kindsChart(); ageChart();

/* 03 pipeline */
const flagged = caps.filter(c => c.observed.observed_risk !== 'none').length;
const proposed = caps.filter(c => c.ai_recommendation && c.ai_recommendation.action && c.ai_recommendation.action !== 'keep').length;
$('#pipe').innerHTML = [[S.dependencies_analysed,'dependencies analysed','OBSERVED'],[flagged,'flagged with at least one risk','OBSERVED'],
  [proposed,'given an AI migration plan','AI'],[S.migrations_verified,'fixes proven by running tests','VERIFIED']]
  .map(([v,l,p]) => `<div class="step"><div class="v">${v}</div><div class="l">${l}${tag(p)}</div></div>`).join('');

/* 04 combined */
let secN = 4;
if (C && C.run) {
  $('#combinedSec').hidden = false;
  const cmp = C.comparison || {};
  $('#combinedIntro').innerHTML = `The project's own test suite, run on the original dependencies and again with every verified replacement applied at once.${tag('VERIFIED')}`;
  $('#combined').innerHTML = `<div class="figs" style="grid-template-columns:1fr 1fr"><div class="fig"><div class="v" style="font-size:32px">${fmt(D.baseline_run.summary)}</div><div class="l">original dependencies</div></div>
    <div class="fig good"><div class="v" style="font-size:32px;color:var(--good)">${fmt(comb)}</div><div class="l">all verified replacements together — project's own tests</div></div></div>
    ${eqComb && total(eqComb) ? `<p class="small" style="margin-top:12px">Plus <b>${pass(eqComb)} of ${total(eqComb)}</b> AI-written equivalence tests passing on the combined replacement (each one was first confirmed to pass on the original code). ${tag('VERIFIED')}</p>` : ''}
    <p class="small" style="margin-top:12px">Tests fixed: ${esc((cmp.fixed||[]).join(', ')||'none')} · Tests broken: ${esc((cmp.regressed||[]).map(r=>r.test).join(', ')||'none')}${C.patch_file ? ` · Patch file: <code>${esc(C.patch_file)}</code>`:''}</p>`;
  secN = 5;
}
['numFind','numAll','numGuide'].forEach((id,i) => $('#'+id).textContent = String(secN + i).padStart(2,'0'));

/* findings + table */
const topI = c => (c.observed.risk_indicators||[]).slice().sort((a,b) => RISK[a.severity]-RISK[b.severity])[0];
const sorted = caps.slice().sort((a,b) => RISK[a.observed.observed_risk]-RISK[b.observed.observed_risk] || (a.status==='verified'?-1:1));
const shortDetail = s => { s = String(s||'').replace(/\(\/[^)]*\)/g,'').replace(/\s+/g,' '); return s.length > 190 ? s.slice(0,190)+'…' : s; };
$('#findings').innerHTML = sorted.filter(c => c.observed.observed_risk==='high').map(c => { const t = topI(c);
  return `<div class="find" data-dep="${esc(c.dependency)}"><div class="fname">${esc(c.dependency)}</div>
    <div><span class="fkind">${esc(nice(t ? t.kind : ''))}.</span> <span class="fdetail">${esc(shortDetail(t ? t.detail : ''))}</span></div>
    <div class="status st-${c.status}">${esc(nice(c.status))}</div></div>`; }).join('') || '<p class="small">No high-risk dependencies.</p>';
$('#tbody').innerHTML = sorted.map(c => { const ai = c.ai_recommendation || {}, rep = ai.proposed_replacement || {}, t = topI(c);
  const act = ai.action ? `${esc(ai.action)}${rep.package ? ' → <code>'+esc(rep.package)+' '+esc(rep.version_spec||'')+'</code>' : ''}` : '<span class="small">—</span>';
  return `<tr class="row" data-dep="${esc(c.dependency)}"><td class="dep">${esc(c.dependency)}</td><td><span class="sev sev-${c.observed.observed_risk}">${esc(c.observed.observed_risk)}</span></td>
    <td>${t ? esc(nice(t.kind)) : '<span class="small">—</span>'}</td><td>${act}</td><td><span class="status st-${c.status}">${esc(nice(c.status))}</span></td></tr>`; }).join('');

/* guide */
$('#guide').innerHTML = [['OBSERVED','Read directly from the repository, its syntax tree, PyPI or GitHub. Deterministic; no AI involved.'],
  ['VERIFIED','Produced by installing dependencies in a clean environment and actually running the tests.'],
  ['AI','Suggested by Gemma 4. A recommendation, not a fact, until a verified section confirms it.']]
  .map(([p,t]) => `<div><h3 class="t-${p}" style="font-family:var(--sans);font-size:13px;letter-spacing:.1em;text-transform:uppercase">${p === 'AI' ? 'AI-generated' : p.toLowerCase()}</h3><p>${t}</p></div>`).join('');

/* appendix */
function diff(t){return '<pre class="diff">'+esc(t).split('\n').map(l=>l.startsWith('+')&&!l.startsWith('+++')?`<span class="a">${l}</span>`:l.startsWith('-')&&!l.startsWith('---')?`<span class="d">${l}</span>`:l.startsWith('@@')?`<span class="h">${l}</span>`:l).join('\n')+'</pre>';}
const runBox = (t,s) => `<div class="run"><div class="t">${esc(t)}</div><div class="v">${fmt(s)}</div></div>`;
const blk = (title, p, inner) => `<div class="blk"><div class="bh">${esc(title)}${p ? tag(p) : ''}</div>${inner}</div>`;
const str = x => typeof x === 'string' ? x : JSON.stringify(x);
function card(c){
  const o=c.observed, d=o.dependency_details, ai=c.ai_recommendation, v=c.ai_claim_verification, ex=c.execution, g=c.compatibility_gaps;
  let h = `<details class="dep" id="dep-${esc(c.dependency)}"><summary><span class="chev">›</span><span class="dname">${esc(c.dependency)}</span>
    <span class="sev sev-${o.observed_risk}">${esc(o.observed_risk)} risk</span><span class="status st-${c.status}">${esc(nice(c.status))}</span>
    <span class="dmeta">installed ${esc(d.installed_version_in_baseline||'—')} · latest ${esc(d.latest_version||'?')}</span></summary><div class="dbody">`;
  h += `<p class="small" style="margin-top:14px">${d.declared.length ? d.declared.map(x=>`<code>${esc(x.raw)}</code> in ${esc(x.file)}`).join(' · ') : '<b style="color:var(--crit)">Not declared in any manifest</b>'}</p>`;
  h += blk('Risk indicators','OBSERVED', `<ul>${(o.risk_indicators||[]).map(i=>`<li><span class="sev sev-${i.severity}">${i.severity}</span> — ${esc(i.detail)} <span class="small">(${esc(i.source)} · <code>${esc(i.id)}</code>)</span></li>`).join('')||'<li>none</li>'}</ul>`);
  h += blk('Where it is used','OBSERVED', `<ul>${(o.usage_locations||[]).slice(0,25).map(u=>`<li><code>${esc(u.file)}:${u.line}</code> <span class="small">${esc(u.kind)}</span> <code>${esc(u.code)}</code></li>`).join('')||'<li>Not imported by the repository source.</li>'}</ul>`);
  if (ai) { const rep = ai.proposed_replacement||{};
    h += blk('Recommendation','AI', `<p><b>${esc(ai.action)}</b>${rep.package?` → <code>${esc(rep.package)} ${esc(rep.version_spec||'')}</code>`:''} · AI-assessed risk: ${esc(ai.risk_level)} · confidence ${esc(ai.confidence)}</p>
      <p>${esc(ai.risk_summary)}</p>${ai.rationale?`<p class="small">${esc(ai.rationale)}</p>`:''}
      <div class="two"><div><b>Migration steps</b><ol>${(ai.migration_steps||[]).map(s=>`<li>${esc(str(s))}</li>`).join('')}</ol></div>
      <div><b>Suggested tests</b><ul>${(ai.suggested_tests||[]).map(s=>`<li>${esc(str(s))}</li>`).join('')}</ul></div></div>`); }
  if (v) h += blk('Fact-check of the AI answer','OBSERVED', `<ul><li>Grounded in real evidence: <b style="color:${v.grounded?'var(--good)':'var(--crit)'}">${v.grounded?'yes':'no'}</b> · valid citations: ${(v.cited_indicator_ids_valid||[]).length} · citations to evidence that does not exist: ${esc((v.cited_indicator_ids_invalid||[]).join(', ')||'none')}</li>
    ${v.replacement_check?`<li>Replacement check: ${esc(v.replacement_check)}</li>`:''}${(v.uncited_high_indicators||[]).length?`<li>High-severity evidence the AI did not address: ${esc(v.uncited_high_indicators.join(', '))}</li>`:''}</ul>`);
  if (ex) { const cmp = ex.comparison||{};
    h += blk('Executed tests','VERIFIED', `<div class="runs">${runBox('Original · project tests', ex.baseline_original)}${runBox('Replacement · project tests', ex.candidate_replacement)}${runBox('AI equivalence test · original', ex.equivalence_test_on_original)}${runBox('AI equivalence test · replacement', ex.equivalence_test_on_replacement)}</div>
      <p>Verdict: <b>${esc(nice(cmp.verdict))}</b> · AI repair attempts used: ${esc(ex.fix_attempts)} · tests fixed: ${esc((cmp.fixed||[]).join(', ')||'none')}</p>
      <p class="small">AI-written equivalence test: ${ex.equivalence_test_valid ? 'valid — passed on both sides' : 'not valid or not run, so it was discarded; the verdict relies on the project\'s own tests'}</p>
      ${(ex.attempts||[]).map(a=>`<details><summary class="small">Attempt ${a.attempt}: ${esc(nice(a.comparison.verdict))} — ${a.edits.filter(e=>e.applied).length}/${a.edits.length} edits applied</summary>
        <p class="small">${tag('AI')} ${esc(a.ai_explanation||'')}</p><ul>${(a.candidate_run?.commands||[]).map(c=>`<li class="small"><code>${esc(c.command)}</code> → exit ${c.exit_code} (${c.duration_s}s)</li>`).join('')}</ul></details>`).join('')}
      ${ex.patch_file?`<details><summary class="small">Patch (${esc(ex.patch_file)})</summary>${diff((D.__patches||{})[c.dependency]||'')}</details>`:''}`); }
  h += `<div class="two">${blk('Compatibility gaps observed','VERIFIED', `<ul>${g.observed.items.map(x=>`<li><b>${esc(nice(x.type))}</b> ${esc(x.test||'')} <span class="small">${esc(x.detail||'')}</span></li>`).join('')||'<li>none observed</li>'}</ul>`)}
    ${blk('Gaps expected by the AI','AI', `<ul>${g.expected_by_ai.items.map(x=>`<li>${esc(str(x))}</li>`).join('')||'<li>none</li>'}</ul>`)}</div>`;
  h += blk('Open concerns and limitations','', `<ul>${c.open_concerns_and_limitations.map(x=>`<li>${esc(x)}</li>`).join('')||'<li>none</li>'}</ul>`);
  return h + '</div></details>';
}
let filter = 'all';
const filters = {all:'All', high:'High risk', verified:'Verified', unresolved:'Not verified'};
function drawDetails(){
  $('#toolbar').innerHTML = Object.entries(filters).map(([k,v]) => `<button class="${filter===k?'on':''}" data-f="${k}">${v}</button>`).join('') +
    '<button data-x="open">Expand all</button><button data-x="close">Collapse all</button>';
  document.querySelectorAll('#toolbar [data-f]').forEach(b => b.onclick = () => {filter=b.dataset.f; drawDetails();});
  document.querySelector('#toolbar [data-x=open]').onclick = () => document.querySelectorAll('details.dep').forEach(d=>d.open=true);
  document.querySelector('#toolbar [data-x=close]').onclick = () => document.querySelectorAll('details.dep').forEach(d=>d.open=false);
  $('#details').innerHTML = sorted.filter(c => filter==='all' || c.observed.observed_risk===filter || c.status===filter ||
     (filter==='unresolved' && ['failed','error','unresolved'].includes(c.status))).map(card).join('');
}
drawDetails();
function jump(dep){ filter='all'; drawDetails(); const el=document.getElementById('dep-'+dep); if(el){el.open=true; el.scrollIntoView({behavior:'smooth',block:'start'});} }
document.querySelectorAll('[data-dep]').forEach(el => el.onclick = () => jump(el.dataset.dep));
window.addEventListener('beforeprint', () => document.querySelectorAll('details').forEach(d => d.open = true));
bindTips(document);
$('#repro').textContent = D.reproduce.steps.map((s,i)=>`${i+1}. ${s}`).join('\n') + '\n\nOr run ./replay.sh from the capsule folder.';
$('#footer').innerHTML = `<span>__TEAM__ · Dependency Exit Capsule</span><span>${esc(D.generated_by.name)} ${esc(D.generated_by.version)} · schema ${esc(D.schema)}</span>`;
</script></body></html>
"""


def render_html(doc: dict, patches: dict | None = None) -> str:
    team = html.escape(os.environ.get("DEPEXIT_TEAM", "Travis Tanner"))
    payload = json.dumps(doc, default=str).replace("</", "<\\/")
    return TEMPLATE.replace("__TEAM__", team).replace("__DATA__", payload)
