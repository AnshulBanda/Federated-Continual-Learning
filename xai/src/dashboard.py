"""Build a static, bank-local review dashboard from explanation JSON files."""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def build_dashboard(reports_root: Path, output_file: Path) -> int:
    cases: list[dict[str, Any]] = []
    for path in sorted(reports_root.glob("**/reports/validation_*/explanation.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
            case["_relative_report"] = str(path.relative_to(reports_root))
            cases.append(case)
        except (OSError, json.JSONDecodeError):
            continue
    if not cases:
        raise ValueError(f"no validation explanation JSON files found under {reports_root}")
    payload = json.dumps(cases, ensure_ascii=False).replace("</", "<\\/")
    page = r'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Federated AML XAI review</title>
<style>
:root{color-scheme:dark;--bg:#0b1220;--panel:#111c2e;--line:#26364d;--muted:#9db0c8;--ink:#ecf4ff;--accent:#63d6c3;--warn:#f6c66a}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,Segoe UI,sans-serif}header{padding:26px max(24px,calc((100vw - 1160px)/2));border-bottom:1px solid var(--line);background:#0d1728}h1{font-size:24px;margin:0}header p{color:var(--muted);margin:6px 0 0}.layout{max-width:1160px;margin:auto;padding:24px;display:grid;grid-template-columns:290px 1fr;gap:20px}.panel,section{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}.filters{position:sticky;top:16px;height:max-content}label{display:block;color:var(--muted);font-size:12px;margin:12px 0 5px}select,input{width:100%;padding:10px;border-radius:8px;border:1px solid var(--line);background:#0b1423;color:var(--ink)}.badge{display:inline-block;color:var(--accent);border:1px solid #28665d;border-radius:99px;padding:2px 9px;font-size:12px}.score{font-size:36px;font-weight:700;color:var(--accent)}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.card{padding:12px;background:#0c1626;border-radius:9px;border:1px solid var(--line)}h2{font-size:17px;margin:0 0 12px}h3{font-size:14px;margin:0 0 8px;color:var(--accent)}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:7px;border-bottom:1px solid var(--line)}small,.muted{color:var(--muted)}.notice{border-left:3px solid var(--warn);padding:8px 12px;background:#242116;color:#e7d8b1;margin:14px 0}.bar{height:8px;background:#26364d;border-radius:99px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}ul{padding-left:20px}.empty{color:var(--muted)}@media(max-width:760px){.layout{grid-template-columns:1fr}.filters{position:static}.grid{grid-template-columns:1fr}}
</style>
<header><h1>Federated AML · XAI review</h1><p>Validation-only, per-transaction model explanations · local review view</p></header>
<main class="layout"><aside class="panel filters"><h2>Find a case</h2><label for="bank">Bank</label><select id="bank"></select><label for="case">Transaction</label><select id="case"></select><label for="query">Search ID</label><input id="query" placeholder="Filter transaction IDs"><p class="notice">This dashboard describes model behavior. A score or explanation does not establish fraud, laundering typology, or intent. Transaction-level content is bank-local.</p><small id="count"></small></aside><article id="detail"></article></main>
<script>
const cases=__DATA__;const bank=document.querySelector('#bank'),pick=document.querySelector('#case'),query=document.querySelector('#query');
const esc=x=>String(x??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function banks(){const vals=[...new Set(cases.map(x=>x.bank))];bank.innerHTML=vals.map(x=>`<option>${esc(x)}</option>`).join('');fill()}
function fill(){const arr=cases.filter(x=>x.bank===bank.value&&String(x.transaction_id).includes(query.value));pick.innerHTML=arr.map((x,i)=>`<option value="${esc(x.transaction_id)}">${esc(x.transaction_id)} · ${esc(x.prediction?.class)} · ${Number(x.prediction?.probability||0).toFixed(3)}</option>`).join('');document.querySelector('#count').textContent=`${arr.length} matching cases`;show(arr[0])}
function show(x){if(!x){document.querySelector('#detail').innerHTML='<p class="empty">No matching cases.</p>';return}const f=x.feature_explanation?.features||[],t=x.temporal_explanation||{},g=x.graph_explanation||{},v=x.verification||{},cf=x.counterfactual_explanation||{},mg=x.per_member_graph_evidence||[];const rows=f.map(a=>`<tr><td>${esc(a.feature)}</td><td>${Number(a.shap_logit||0).toFixed(4)}</td><td>${esc(a.value)}</td></tr>`).join('');const edges=(g.important_edges||[]).map(e=>`<tr><td>${esc(e.source??e.src)}</td><td>→ ${esc(e.target??e.dst)}</td><td>${Number(e.delta_probability||0).toFixed(5)}</td></tr>`).join('');const memberGraphs=mg.map(m=>`<p>Seed ${esc(m.seed)}: ${esc(m.graph_explanation?.candidate_count??0)} candidates · ${esc(m.graph_explanation?.window_event_count??0)} events</p>`).join('');document.querySelector('#detail').innerHTML=`<section><span class="badge">${esc(x.bank)} · ${esc(x.split)}</span><h2 style="margin-top:12px">Transaction ${esc(x.transaction_id)}</h2><small>${esc(x.timestamp)} · ${esc(x.prediction?.score_type)}</small><div class="score">${Number(x.prediction?.probability||0).toFixed(4)}</div><small>threshold ${esc(x.prediction?.threshold??'not calibrated')} · ${esc(x.prediction?.class??'ensemble score only')}</small><div class="grid" style="margin-top:18px"><div class="card"><h3>Feature evidence</h3><small>${esc(x.feature_explanation?.units||'Interventional SHAP · account memory held fixed')}</small><table><tr><th>Feature</th><th>Contribution</th><th>Value</th></tr>${rows||'<tr><td colspan="3">No feature evidence recorded</td></tr>'}</table></div><div class="card"><h3>Temporal context</h3><p>${esc(t.evidence_type||'No temporal summary')}</p><p>Observation window: ${esc(t.observation_window_batches)} batches</p><p>Endpoint events: ${esc(t.target_endpoint_event_count)}</p><p>Since sender last seen: ${esc(t.time_since_last_seen_seconds?.sender)} sec</p><p>Since receiver last seen: ${esc(t.time_since_last_seen_seconds?.receiver)} sec</p><small>${esc(t.timing_semantics)}</small></div><div class="card"><h3>Graph perturbation</h3><p>${esc(g.method||'Member-level temporal perturbation')} · ${esc(g.candidate_count??'—')} candidates · ${esc(g.window_event_count??'—')} events</p>${memberGraphs}<table><tr><th>From</th><th>To</th><th>Δ probability</th></tr>${edges||'<tr><td colspan="3">Graph details are in the member reports; no ensemble graph attribution is asserted.</td></tr>'}</table><small>${esc(g.limitations||'Graph evidence remains member-level; it is not an exact ensemble perturbation.')}</small></div><div class="card"><h3>Counterfactual</h3>${cf.status?`<p>${esc(cf.status)} · ${esc(cf.method)}</p><p>Evaluated: ${esc(cf.candidates_evaluated)} candidates</p>`:'<p>Not yet computed for this case.</p>'}<small>${esc(cf.interpretation||'A counterfactual is model sensitivity under constrained feature changes, not advice or causal evidence.')}</small></div></div><p class="notice">Prediction parity: ${v.passed?'passed':'not recorded'} · XAI score error ${esc(v.absolute_errors?.original_vs_xai)}. Verify the checkpoint and preprocessing in the run manifest before sharing.</p><small>Report artifact: ${esc(x._relative_report)}</small></section>`}
bank.addEventListener('change',fill);query.addEventListener('input',fill);pick.addEventListener('change',()=>show(cases.find(x=>x.bank===bank.value&&String(x.transaction_id)===pick.value)));banks();
</script></html>'''.replace("__DATA__", payload)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(page, encoding="utf-8")
    return len(cases)
