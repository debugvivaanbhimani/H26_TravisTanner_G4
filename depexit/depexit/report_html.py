"""Self-contained HTML report for a capsule (no external assets, works offline)."""
from __future__ import annotations

import html
import json

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dependency Exit Capsule</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--panel2:#1d212a;--ink:#e8eaf0;--mute:#9aa3b2;--line:#2a2f3a;
--obs:#4ea1ff;--ver:#2fbf71;--ai:#b07cff;--hi:#ff5d5d;--med:#f5a524;--lo:#8fa3bf;--ok:#2fbf71;--bad:#ff5d5d}
@media (prefers-color-scheme: light){:root{--bg:#f6f7f9;--panel:#fff;--panel2:#f1f3f6;--ink:#141821;--mute:#5b6576;--line:#e2e6ec}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:28px 32px 18px;border-bottom:1px solid var(--line)}
h1{margin:0 0 4px;font-size:22px;letter-spacing:-.01em}h2{font-size:16px;margin:28px 0 10px}h3{font-size:13px;margin:18px 0 8px;text-transform:uppercase;letter-spacing:.06em;color:var(--mute)}
.sub{color:var(--mute);font-size:13px}main{padding:8px 32px 60px;max-width:1280px}
.legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.tag{display:inline-flex;align-items:center;gap:6px;font-size:11px;font-weight:700;letter-spacing:.06em;padding:2px 8px;border-radius:999px;border:1px solid}
.t-OBSERVED{color:var(--obs);border-color:var(--obs)}.t-VERIFIED{color:var(--ver);border-color:var(--ver)}.t-AI{color:var(--ai);border-color:var(--ai)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:20px}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.kpi .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}.kpi .l{color:var(--mute);font-size:12px}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;color:var(--mute);font-weight:600;background:var(--panel2)}
tr.row{cursor:pointer}tr.row:hover td{background:var(--panel2)}
.sev{font-weight:700;font-size:12px;text-transform:uppercase}.sev-high{color:var(--hi)}.sev-medium{color:var(--med)}.sev-low{color:var(--lo)}.sev-none{color:var(--mute)}
.st{font-size:12px;font-weight:700;padding:2px 8px;border-radius:6px;background:var(--panel2)}
.st-verified{color:var(--ok)}.st-unresolved,.st-failed,.st-error{color:var(--bad)}
code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
pre{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;max-height:380px;white-space:pre-wrap}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:16px 0;scroll-margin-top:12px}
.card h2{margin:0 0 4px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sec{border-left:3px solid var(--line);padding:2px 0 2px 14px;margin:14px 0}
.sec.OBSERVED{border-color:var(--obs)}.sec.VERIFIED{border-color:var(--ver)}.sec.AI{border-color:var(--ai)}
.sec>.h{display:flex;gap:8px;align-items:center;margin-bottom:6px;font-weight:600}
ul{margin:4px 0;padding-left:20px}li{margin:2px 0}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:800px){.grid2{grid-template-columns:1fr}main,header{padding-left:16px;padding-right:16px}}
.runs{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.run{background:var(--panel2);border-radius:10px;padding:10px 12px}.run .n{font-size:12px;color:var(--mute)}.run .r{font-weight:700;font-variant-numeric:tabular-nums}
.bar{height:8px;border-radius:4px;background:var(--bad);overflow:hidden;margin-top:6px}.bar>i{display:block;height:100%;background:var(--ok)}
details summary{cursor:pointer;color:var(--mute);font-size:12px}
.diff .a{color:var(--ok)}.diff .d{color:var(--bad)}.diff .h{color:var(--obs)}
.filters{display:flex;gap:8px;margin:12px 0}.filters button{background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:5px 10px;cursor:pointer;font-size:12px}
.filters button.on{border-color:var(--obs);color:var(--obs)}
</style></head><body>
<header><h1 id="title"></h1><div class="sub" id="meta"></div>
<div class="legend" id="legend"></div></header>
<main><div class="kpis" id="kpis"></div>
<h2>Dependencies</h2>
<div class="filters" id="filters"></div>
<table><thead><tr><th>Dependency</th><th>Observed risk</th><th>Top indicator</th><th>AI action → replacement</th><th>Verification</th></tr></thead><tbody id="tbody"></tbody></table>
<div id="combined"></div>
<div id="cards"></div>
<h2>Reproduce</h2><pre id="repro"></pre>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const tag = p => `<span class="tag t-${p}">${p === 'AI' ? 'AI-GENERATED' : p}</span>`;
const fmt = s => s ? `${s.passed||0} passed · ${(s.failed||0)+(s.error||0)} failed` : 'not run';
const pct = s => s && s.total ? Math.round(100*((s.passed||0)+(s.skipped||0))/s.total) : 0;
const repo = D.target_repository;
$('#title').textContent = 'Dependency Exit Capsule — ' + (repo.remote || repo.input);
$('#meta').innerHTML = `commit <code>${esc((repo.commit||'').slice(0,12))}</code> · Python ${esc(D.python_target)} · ${esc(D.finished_at)}` +
  (D.ai_model ? ` · model <code>${esc(D.ai_model.name)}</code> via ${esc(D.ai_model.provider)}` : ' · AI disabled');
$('#legend').innerHTML = Object.entries(D.provenance_legend).map(([k,v]) => `<span title="${esc(v)}">${tag(k)} <span class="sub">${esc(v)}</span></span>`).join('');
const S = D.summary;
const kpi = (v,l,p) => `<div class="kpi"><div class="v">${v}</div><div class="l">${l} ${p?tag(p):''}</div></div>`;
$('#kpis').innerHTML = kpi(S.dependencies_analysed,'dependencies analysed','OBSERVED') +
  kpi(`<span class="sev-high">${S.observed_risk.high}</span> / <span class="sev-medium">${S.observed_risk.medium}</span> / <span class="sev-low">${S.observed_risk.low}</span>`,'high / medium / low risk','OBSERVED') +
  kpi(fmt(S.baseline_tests).replace(' · ','<br>'),'baseline (original deps)','VERIFIED') +
  kpi(`${S.migrations_verified} / ${S.migrations_attempted}`,'migrations verified','VERIFIED') +
  (S.combined_tests ? kpi(fmt(S.combined_tests).replace(' · ','<br>'),'all migrations combined','VERIFIED') : '') +
  kpi(S.ai_ungrounded_claims,'AI outputs failing grounding check','OBSERVED');
let filter = 'all';
const filters = {all:'All', high:'High risk', medium:'Medium', verified:'Verified', unresolved:'Unresolved'};
function drawTable(){
  $('#filters').innerHTML = Object.entries(filters).map(([k,v]) => `<button class="${filter===k?'on':''}" data-f="${k}">${v}</button>`).join('');
  document.querySelectorAll('#filters button').forEach(b => b.onclick = () => {filter=b.dataset.f; drawTable();});
  $('#tbody').innerHTML = D.capsules.filter(c => filter==='all' || c.observed.observed_risk===filter || c.status===filter ||
      (filter==='unresolved' && ['failed','error','unresolved'].includes(c.status))).map(c => {
    const ai = c.ai_recommendation || {}, rep = ai.proposed_replacement || {};
    const top = (c.observed.risk_indicators||[]).slice().sort((a,b)=>({high:0,medium:1,low:2}[a.severity]-({high:0,medium:1,low:2}[b.severity])))[0];
    return `<tr class="row" onclick="document.getElementById('dep-${esc(c.dependency)}').scrollIntoView({behavior:'smooth'})">
      <td><code>${esc(c.dependency)}</code></td><td class="sev sev-${c.observed.observed_risk}">${c.observed.observed_risk}</td>
      <td>${top ? esc(top.kind.replaceAll('_',' ')) : '—'}</td>
      <td>${ai.action ? `<b>${esc(ai.action)}</b> ${rep.package ? '→ <code>'+esc(rep.package)+' '+esc(rep.version_spec||'')+'</code>':''}` : '—'}</td>
      <td><span class="st st-${c.status}">${esc(c.status.replaceAll('_',' '))}</span></td></tr>`;}).join('');
}
drawTable();
function diff(t){return '<pre class="diff">'+esc(t).split('\n').map(l=>l.startsWith('+')&&!l.startsWith('+++')?`<span class="a">${l}</span>`:l.startsWith('-')&&!l.startsWith('---')?`<span class="d">${l}</span>`:l.startsWith('@@')?`<span class="h">${l}</span>`:l).join('\n')+'</pre>';}
const C = D.combined_migration;
if (C && C.run) $('#combined').innerHTML = `<div class="card"><h2>All verified migrations applied together ${tag('VERIFIED')}</h2>
  <div class="runs">${runBox('Original dependencies', D.baseline_run.summary)}${runBox('All replacements together', C.run.summary)}</div>
  <p>Verdict: <b>${esc(C.comparison.verdict)}</b> · fixed: ${esc((C.comparison.fixed||[]).join(', ')||'none')} · regressed: ${esc((C.comparison.regressed||[]).map(r=>r.test).join(', ')||'none')}
  ${C.edit_conflicts && C.edit_conflicts.length ? ' · <span class="sev-high">'+C.edit_conflicts.length+' edit conflict(s)</span>':''}</p>
  ${C.patch_file ? `<p class="sub">Patch: <code>${esc(C.patch_file)}</code></p>`:''}</div>`;
function runBox(n,s){return `<div class="run"><div class="n">${esc(n)}</div><div class="r">${fmt(s)}</div><div class="bar"><i style="width:${pct(s)}%"></i></div></div>`;}
$('#cards').innerHTML = D.capsules.map(c => {
  const o = c.observed, d = o.dependency_details, ai = c.ai_recommendation, v = c.ai_claim_verification, ex = c.execution, g = c.compatibility_gaps;
  let h = `<div class="card" id="dep-${esc(c.dependency)}"><h2><code>${esc(c.dependency)}</code><span class="sev sev-${o.observed_risk}">${o.observed_risk} risk</span><span class="st st-${c.status}">${esc(c.status.replaceAll('_',' '))}</span></h2>
  <div class="sub">${d.declared.length ? d.declared.map(x=>`<code>${esc(x.raw)}</code> in ${esc(x.file)}`).join(' · ') : '<b class="sev-high">not declared in any manifest</b>'}
   · installed <code>${esc(d.installed_version_in_baseline||'—')}</code> · latest <code>${esc(d.latest_version||'?')}</code> (${esc(d.latest_released||'?')})</div>`;
  h += `<div class="sec OBSERVED"><div class="h">Risk indicators ${tag('OBSERVED')}</div><ul>${(o.risk_indicators||[]).map(i=>`<li><span class="sev sev-${i.severity}">${i.severity}</span> <code>${esc(i.id)}</code> ${esc(i.detail)} <span class="sub">(${esc(i.source)})</span></li>`).join('')||'<li>none</li>'}</ul></div>`;
  h += `<div class="sec OBSERVED"><div class="h">Usage locations ${tag('OBSERVED')}</div><details ${o.usage_locations.length<8?'open':''}><summary>${o.usage_locations.length} location(s)</summary><ul>${o.usage_locations.map(u=>`<li><code>${esc(u.file)}:${u.line}</code> <span class="sub">[${esc(u.kind)}]</span> <code>${esc(u.code)}</code></li>`).join('')||'<li>not imported by repository source</li>'}</ul></details></div>`;
  if (ai) { const rep = ai.proposed_replacement||{};
    h += `<div class="sec AI"><div class="h">Recommendation ${tag('AI')}</div>
    <p><b>${esc(ai.action)}</b>${rep.package?` → <code>${esc(rep.package)} ${esc(rep.version_spec||'')}</code>`:''} · AI risk <span class="sev sev-${esc(ai.risk_level)}">${esc(ai.risk_level)}</span> · confidence ${esc(ai.confidence)}</p>
    <p>${esc(ai.risk_summary)}</p><p class="sub">${esc(ai.rationale)}</p>
    <div class="grid2"><div><b>Migration steps</b><ol>${(ai.migration_steps||[]).map(s=>`<li>${esc(s)}</li>`).join('')}</ol></div>
    <div><b>Suggested tests</b><ul>${(ai.suggested_tests||[]).map(s=>`<li>${esc(s)}</li>`).join('')}</ul></div></div></div>`; }
  if (v) h += `<div class="sec OBSERVED"><div class="h">Checks on the AI output ${tag('OBSERVED')}</div><ul>
    <li>Grounded: <b class="${v.grounded?'st-verified':'sev-high'}">${v.grounded}</b> · cited evidence that exists: ${esc((v.cited_indicator_ids_valid||[]).length)} · cited evidence that does NOT exist: <b>${esc((v.cited_indicator_ids_invalid||[]).join(', ')||'none')}</b></li>
    ${v.replacement_check?`<li>Replacement: ${esc(v.replacement_check)}</li>`:''}
    ${(v.uncited_high_indicators||[]).length?`<li>High-severity evidence the AI ignored: ${esc(v.uncited_high_indicators.join(', '))}</li>`:''}</ul></div>`;
  if (ex) { const cmp = ex.comparison||{};
    h += `<div class="sec VERIFIED"><div class="h">Executed tests ${tag('VERIFIED')}</div>
    <div class="runs">${runBox('Original dependency — project tests', ex.baseline_original)}${runBox('Replacement — project tests', ex.candidate_replacement)}${runBox('AI equivalence test on original', ex.equivalence_test_on_original)}${runBox('AI equivalence test on replacement', ex.equivalence_test_on_replacement)}</div>
    <p class="sub">AI-written equivalence test: ${ex.equivalence_test_valid ? '<b class="st-verified">valid — passed on both sides</b>' : '<b>not valid or not run — discarded; verification uses the project\'s own tests</b>'}</p>
    <p>Verdict <b>${esc(cmp.verdict)}</b> · AI fix attempts used: ${esc(ex.fix_attempts)} · fixed: ${esc((cmp.fixed||[]).join(', ')||'none')}</p>
    ${(ex.attempts||[]).map(a=>`<details><summary>Attempt ${a.attempt}: ${esc(a.comparison.verdict)} — ${a.edits.filter(e=>e.applied).length}/${a.edits.length} edits applied</summary>
      <p class="sub">${tag('AI')} ${esc(a.ai_explanation)}</p>
      <ul>${(a.candidate_run?.commands||[]).map(c=>`<li><code>${esc(c.command)}</code> → exit ${c.exit_code} (${c.duration_s}s)</li>`).join('')}</ul></details>`).join('')}
    ${ex.patch_file?`<details><summary>Patch (${esc(ex.patch_file)})</summary>${diff((D.__patches||{})[c.dependency]||'')}</details>`:''}</div>`; }
  h += `<div class="grid2"><div class="sec VERIFIED"><div class="h">Compatibility gaps observed ${tag('VERIFIED')}</div><ul>${g.observed.items.map(x=>`<li><b>${esc(x.type.replaceAll('_',' '))}</b> ${esc(x.test||'')} <span class="sub">${esc(x.detail||'')}</span></li>`).join('')||'<li>none observed</li>'}</ul></div>
  <div class="sec AI"><div class="h">Gaps expected by AI ${tag('AI')}</div><ul>${g.expected_by_ai.items.map(x=>`<li>${esc(typeof x==='string'?x:JSON.stringify(x))}</li>`).join('')||'<li>none</li>'}</ul></div></div>`;
  h += `<div class="sec"><div class="h">Open concerns & limitations</div><ul>${c.open_concerns_and_limitations.map(x=>`<li>${esc(x)}</li>`).join('')||'<li>none</li>'}</ul></div></div>`;
  return h; }).join('');
$('#repro').textContent = D.reproduce.steps.map((s,i)=>`${i+1}. ${s}`).join('\n') + '\n\nor: ./replay.sh';
</script></body></html>
"""


def render_html(doc: dict, patches: dict | None = None) -> str:
    slim = dict(doc)
    payload = json.dumps(slim, default=str).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload)
