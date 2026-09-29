#!/usr/bin/env python3
"""Build the n8n workflow JSON files for the demos.

Keeping the workflows in code makes them reviewable and easy to regenerate:
    python scripts/build_demo_workflows.py
"""
import json
import os
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "workflows")

LLM_URL = "http://127.0.0.1:8770/chat"

UPLOAD_PAGE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Invoice Automation Demo</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b1220;--card:#111b2e;--line:#1e2b45;--text:#e8eefc;--muted:#8fa3c8;--accent:#4f8cff;--ok:#22c55e;--warn:#f59e0b;--bad:#ef4444}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:linear-gradient(160deg,#0b1220,#0e1730);color:var(--text);min-height:100vh}
.wrap{max-width:840px;margin:0 auto;padding:40px 20px}
h1{font-size:24px;margin:0 0 6px}.sub{color:var(--muted);margin:0 0 28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin-bottom:18px}
.drop{border:2px dashed #2b3c60;border-radius:12px;padding:36px;text-align:center;cursor:pointer;transition:.15s}
.drop.hover{border-color:var(--accent);background:#0f1a31}
.btn{display:inline-block;background:var(--accent);color:#fff;border:0;border-radius:9px;padding:11px 18px;font-weight:600;cursor:pointer}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
.badge{display:inline-block;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:700}
.badge.pass{background:rgba(34,197,94,.15);color:var(--ok)}.badge.review{background:rgba(245,158,11,.15);color:var(--warn)}
.check{color:var(--ok)}.check.bad{color:var(--bad)}
.spinner{width:22px;height:22px;border:3px solid #2b3c60;border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;display:inline-block;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
pre{background:#0a1122;border:1px solid var(--line);border-radius:10px;padding:12px;overflow:auto;font-size:12px;color:#bcd0f5}
</style></head><body><div class="wrap">
<h1>Invoice &amp; document automation</h1>
<p class="sub">Upload a PDF invoice &mdash; an LLM extracts the fields, business rules validate the totals, and the row is appended to the ledger.</p>
<div class="card">
  <div id="drop" class="drop"><p style="margin:0 0 12px">Drop your invoice PDF here</p><button class="btn" id="pick">Choose PDF</button><input id="file" type="file" accept="application/pdf" hidden></div>
  <p id="status" style="margin:14px 0 0;color:var(--muted)"></p>
</div>
<div id="result" style="display:none">
  <div class="card"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
    <b id="doc-title"></b><span id="badge" class="badge"></span></div>
    <table id="fields"></table></div>
  <div class="card"><b>Validation checks</b><table id="checks"></table></div>
  <div class="card"><b>Raw extracted JSON</b><pre id="raw"></pre></div>
</div>
</div>
<script>
const drop=document.getElementById('drop'),file=document.getElementById('file'),status=document.getElementById('status');
let t0=0;
document.getElementById('pick').onclick=()=>file.click();
drop.onclick=e=>{if(e.target===drop||e.target.tagName==='P')file.click()};
drop.ondragover=e=>{e.preventDefault();drop.classList.add('hover')};
drop.ondragleave=()=>drop.classList.remove('hover');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('hover');if(e.dataTransfer.files[0])send(e.dataTransfer.files[0])};
file.onchange=()=>{if(file.files[0])send(file.files[0])};
async function send(f){
  if(f.type!=='application/pdf'){status.textContent='Please upload a PDF file.';return}
  status.innerHTML='<span class="spinner"></span> Extracting fields with the LLM&hellip;';
  t0=performance.now();
  const fd=new FormData();fd.append('data',f);
  try{
    const r=await fetch('/webhook/doc-automation/process',{method:'POST',body:fd});
    const d=await r.json();
    render(d);
    status.textContent='Done in '+((performance.now()-t0)/1000).toFixed(1)+'s';
  }catch(e){status.textContent='Error: '+e.message}
}
function render(d){
  document.getElementById('result').style.display='block';
  const doc=d.document||{};
  document.getElementById('doc-title').textContent=(doc.vendor||'Unknown vendor')+' &middot; '+(doc.invoice_number||'?');
  const badge=document.getElementById('badge');badge.textContent=d.status;badge.className='badge '+(d.status==='PASS'?'pass':'review');
  const fields=[['Date',doc.date],['Currency',doc.currency],['Subtotal',doc.subtotal],['Tax',doc.tax],['Total',doc.total],['Line items',(doc.line_items||[]).length]];
  document.getElementById('fields').innerHTML=fields.map(f=>'<tr><th style="color:var(--muted);font-weight:500">'+f[0]+'</th><td>'+f[1]+'</td></tr>').join('');
  document.getElementById('checks').innerHTML=d.checks.map(c=>'<tr><td class="check'+(c.ok?'':' bad')+'">'+(c.ok?'&#10003;':'&#10007;')+' '+c.name+'</td><td style="color:var(--muted)">'+c.detail+'</td></tr>').join('');
  document.getElementById('raw').textContent=JSON.stringify(doc,null,2);
}
</script></body></html>"""

EXTRACT_SYSTEM_PROMPT = (
    "You are an invoice data extraction engine. Read the invoice text and return ONLY a JSON object "
    "(no markdown, no commentary) with exactly this shape: "
    '{"invoice_number": "<string>", "date": "<YYYY-MM-DD>", "vendor": "<string>", '
    '"currency": "<3-letter code>", "line_items": [{"description": "<string>", "quantity": <number>, '
    '"unit_price": <number>, "amount": <number>}], "subtotal": <number>, "tax": <number or null>, '
    '"total": <number>}. '
    "Use dot as decimal separator and numbers without currency symbols. "
    "transcribe the values exactly as printed on the document. If a field is missing use null."
)

BUILD_LLM_REQUEST_JS = """const text = ($input.first().json.text || '').slice(0, 12000);
const system = %s;
const user = 'Invoice text:\\n' + text;
return [{ json: { messages: [
  { role: 'system', content: system },
  { role: 'user', content: user }
] } }];
""" % json.dumps(EXTRACT_SYSTEM_PROMPT)

PARSE_VALIDATE_JS = """const resp = $input.first().json;
let content = (resp.choices && resp.choices[0] && resp.choices[0].message.content) || '';
content = content.trim();
if (content.startsWith('```')) {
  content = content.replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
}
const start = content.indexOf('{');
const end = content.lastIndexOf('}');
if (start === -1 || end === -1) {
  throw new Error('LLM did not return JSON: ' + content.slice(0, 200));
}
const doc = JSON.parse(content.slice(start, end + 1));

const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v));
const checks = [];
for (const field of ['invoice_number', 'date', 'vendor', 'currency', 'total']) {
  const ok = doc[field] !== undefined && doc[field] !== null && doc[field] !== '';
  checks.push({ name: 'required field: ' + field, ok, detail: String(doc[field] ?? 'missing') });
}
const dateOk = typeof doc.date === 'string' && /^\\d{4}-\\d{2}-\\d{2}$/.test(doc.date);
checks.push({ name: 'date format YYYY-MM-DD', ok: dateOk, detail: String(doc.date) });

const items = Array.isArray(doc.line_items) ? doc.line_items : [];
const itemsSum = items.reduce((acc, it) => acc + Number(it.amount ?? (num(it.quantity) * num(it.unit_price)) ?? 0), 0);
const subtotal = num(doc.subtotal) ?? 0;
const tax = num(doc.tax) ?? 0;
const total = num(doc.total) ?? 0;
const subtotalOk = Math.abs(itemsSum - subtotal) <= 0.02;
checks.push({ name: 'subtotal matches line items', ok: subtotalOk, detail: 'items=' + itemsSum.toFixed(2) + ' stated=' + subtotal.toFixed(2) });
const totalOk = Math.abs(subtotal + tax - total) <= 0.02;
checks.push({ name: 'total matches subtotal + tax', ok: totalOk, detail: 'expected=' + (subtotal + tax).toFixed(2) + ' stated=' + total.toFixed(2) });

const status = checks.every((c) => c.ok) ? 'PASS' : 'REVIEW';

return [{ json: {
  status,
  document: doc,
  checks,
  items_count: items.length
} }];
"""


def node(name, ntype, type_version, parameters, position, node_id=None, webhook_id=None, extra=None):
    n = {
        "parameters": parameters,
        "id": node_id or str(uuid.uuid4()),
        "name": name,
        "type": ntype,
        "typeVersion": type_version,
        "position": position,
    }
    if webhook_id:
        n["webhookId"] = webhook_id
    if extra:
        n.update(extra)
    return n


def build_doc_automation():
    nodes = [
        node("Upload Page", "n8n-nodes-base.webhook", 2, {
            "httpMethod": "GET",
            "path": "doc-automation",
            "responseMode": "responseNode",
            "options": {},
        }, [0, 0], webhook_id="demo-doc-page"),

        node("Serve Upload Page", "n8n-nodes-base.respondToWebhook", 1.4, {
            "respondWith": "text",
            "responseBody": UPLOAD_PAGE_HTML,
            "options": {
                "responseHeaders": {
                    "entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}],
                },
            },
        }, [220, 0]),

        node("Process Invoice", "n8n-nodes-base.webhook", 2, {
            "httpMethod": "POST",
            "path": "doc-automation/process",
            "responseMode": "responseNode",
            "options": {},
        }, [0, 220], webhook_id="demo-doc-process"),

        node("Extract PDF Text", "n8n-nodes-base.extractFromFile", 1, {
            "operation": "pdf",
            "binaryPropertyName": "data",
            "options": {},
        }, [220, 220]),

        node("Build LLM Request", "n8n-nodes-base.code", 2, {
            "jsCode": BUILD_LLM_REQUEST_JS,
        }, [440, 220]),

        node("LLM Extract", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST",
            "url": LLM_URL,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ messages: $json.messages, temperature: 0 }) }}",
            "options": {"timeout": 60000},
        }, [660, 220]),

        node("Parse & Validate", "n8n-nodes-base.code", 2, {
            "jsCode": PARSE_VALIDATE_JS,
        }, [880, 220]),

        node("Create Ledger Table", "n8n-nodes-base.dataTable", 1.1, {
            "resource": "table",
            "operation": "create",
            "tableName": "invoices",
            "columns": {
                "column": [
                    {"name": "invoice_number", "type": "string"},
                    {"name": "date", "type": "string"},
                    {"name": "vendor", "type": "string"},
                    {"name": "currency", "type": "string"},
                    {"name": "subtotal", "type": "number"},
                    {"name": "tax", "type": "number"},
                    {"name": "total", "type": "number"},
                    {"name": "status", "type": "string"},
                ],
            },
            "options": {"createIfNotExists": True},
        }, [1120, 340]),

        node("Log to Ledger", "n8n-nodes-base.dataTable", 1.1, {
            "resource": "row",
            "operation": "insert",
            "dataTableId": {"__rl": True, "mode": "name", "value": "invoices"},
            "columns": {
                "mappingMode": "defineBelow",
                "value": {
                    "invoice_number": "={{ $('Parse & Validate').first().json.document.invoice_number }}",
                    "date": "={{ $('Parse & Validate').first().json.document.date }}",
                    "vendor": "={{ $('Parse & Validate').first().json.document.vendor }}",
                    "currency": "={{ $('Parse & Validate').first().json.document.currency }}",
                    "subtotal": "={{ Number($('Parse & Validate').first().json.document.subtotal) }}",
                    "tax": "={{ Number($('Parse & Validate').first().json.document.tax || 0) }}",
                    "total": "={{ Number($('Parse & Validate').first().json.document.total) }}",
                    "status": "={{ $('Parse & Validate').first().json.status }}",
                },
            },
            "options": {},
        }, [1340, 340]),

        node("Report", "n8n-nodes-base.respondToWebhook", 1.4, {
            "respondWith": "json",
            "responseBody": "={{ JSON.stringify({ status: $json.status, document: $json.document, checks: $json.checks }) }}",
            "options": {
                "responseHeaders": {
                    "entries": [{"name": "Access-Control-Allow-Origin", "value": "*"}],
                },
            },
        }, [1120, 160]),
    ]

    connections = {
        "Upload Page": {"main": [[{"node": "Serve Upload Page", "type": "main", "index": 0}]]},
        "Process Invoice": {"main": [[{"node": "Extract PDF Text", "type": "main", "index": 0}]]},
        "Extract PDF Text": {"main": [[{"node": "Build LLM Request", "type": "main", "index": 0}]]},
        "Build LLM Request": {"main": [[{"node": "LLM Extract", "type": "main", "index": 0}]]},
        "LLM Extract": {"main": [[{"node": "Parse & Validate", "type": "main", "index": 0}]]},
        "Parse & Validate": {"main": [[
            {"node": "Report", "type": "main", "index": 0},
            {"node": "Create Ledger Table", "type": "main", "index": 0},
        ]]},
        "Create Ledger Table": {"main": [[{"node": "Log to Ledger", "type": "main", "index": 0}]]},
    }

    return {
        "id": "demoDocAutomat01",
        "name": "Demo 01 · Invoice & Document Automation",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "versionId": str(uuid.uuid4()),
        "meta": {"templateCredsSetupCompleted": True},
        "tags": [],
        "pinData": {},
    }


def build_lead_gen():
    landing_html = """<!doctype html>
<html><head><meta charset="utf-8"><title>Lead Gen Demo</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b1220;--card:#111b2e;--line:#1e2b45;--text:#e8eefc;--muted:#8fa3c8;--accent:#4f8cff;--ok:#22c55e;--warn:#f59e0b;--bad:#ef4444}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:linear-gradient(160deg,#0b1220,#0e1730);color:var(--text);min-height:100vh}
.wrap{max-width:760px;margin:0 auto;padding:40px 20px}
h1{font-size:24px;margin:0 0 6px}.sub{color:var(--muted);margin:0 0 28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;margin-bottom:18px}
label{display:block;font-size:13px;color:var(--muted);margin:12px 0 4px}
input,textarea{width:100%;background:#0a1122;border:1px solid var(--line);color:var(--text);border-radius:9px;padding:10px 12px;font:inherit}
.btn{display:inline-block;background:var(--accent);color:#fff;border:0;border-radius:9px;padding:11px 18px;font-weight:600;cursor:pointer;margin-top:16px}
.gauge{font-size:34px;font-weight:800}.tier{display:inline-block;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:700}
.tier.hot{background:rgba(239,68,68,.15);color:var(--bad)}.tier.warm{background:rgba(245,158,11,.15);color:var(--warn)}.tier.cold{background:rgba(143,163,200,.15);color:var(--muted)}
ul{margin:8px 0 0;padding-left:20px;color:var(--muted)}li{margin:4px 0}
pre{background:#0a1122;border:1px solid var(--line);border-radius:10px;padding:12px;white-space:pre-wrap;font-size:13px;color:#bcd0f5}
</style></head><body><div class="wrap">
<h1>Lead generation &amp; enrichment</h1>
<p class="sub">The form posts to n8n: the workflow enriches the lead, scores it with an LLM and drafts the follow-up email.</p>
<div class="card">
  <label>Name</label><input id="name" placeholder="Jane Cooper">
  <label>Email</label><input id="email" placeholder="jane@company.com">
  <label>Company</label><input id="company" placeholder="Company Inc.">
  <label>Website</label><input id="website" placeholder="https://example.com">
  <label>What do they need?</label><textarea id="message" rows="3" placeholder="They asked about automating their invoicing..."></textarea>
  <button class="btn" id="send">Score lead</button>
</div>
<div id="result" style="display:none">
  <div class="card"><div style="display:flex;align-items:center;gap:16px"><div class="gauge" id="score"></div><span class="tier" id="tier"></span></div><ul id="reasons"></ul></div>
  <div class="card"><b>Suggested angle</b><p id="angle" style="color:var(--muted)"></p><b>Follow-up draft</b><pre id="email_draft"></pre></div>
</div>
</div>
<script>
document.getElementById('send').onclick=async()=>{
  const lead={name:v('name'),email:v('email'),company:v('company'),website:v('website'),message:v('message')};
  const r=await fetch('/webhook/lead-gen/process',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(lead)});
  const d=await r.json();
  document.getElementById('result').style.display='block';
  document.getElementById('score').textContent=d.score;
  const t=document.getElementById('tier');t.textContent=d.tier;t.className='tier '+String(d.tier||'').toLowerCase();
  document.getElementById('reasons').innerHTML=(d.reasons||[]).map(x=>'<li>'+x+'</li>').join('');
  document.getElementById('angle').textContent=d.suggested_angle||'';
  document.getElementById('email_draft').textContent=d.followup_email||'';
};
function v(id){return document.getElementById(id).value}
</script></body></html>"""

    build_prompt_js = """const raw = $input.first().json;
const lead = raw.body || raw;
const website = (lead.website || '').trim();
return [{ json: {
  lead,
  website,
  messages: [
    { role: 'system', content: %s },
    { role: 'user', content: 'Lead data (JSON):\\n' + JSON.stringify(lead, null, 2) }
  ]
} }];
""" % json.dumps(
        "You are a B2B lead qualification analyst. Given a lead, return ONLY a JSON object: "
        '{"score": <0-100 integer>, "tier": "HOT"|"WARM"|"COLD", "reasons": ["..."], '
        '"suggested_angle": "<one sentence on how to approach>", '
        '"followup_email": "<short, friendly follow-up email draft in English, 3-4 sentences>"}. '
        "Score based on: clarity of need, company fit, budget signals and urgency in the message. "
        "No markdown, no commentary."
    )

    enrich_lead_js = r"""const prev = $input.first().json;
let siteText = '';
const url = (prev.website || '').trim();
if (url) {
  try {
    const html = await this.helpers.httpRequest({ method: 'GET', url, timeout: 10000, encoding: 'utf8' });
    siteText = String(html)
      .replace(/<script[\s\S]*?<\/script>/gi, ' ')
      .replace(/<style[\s\S]*?<\/style>/gi, ' ')
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 5000);
  } catch (e) {
    siteText = '';
  }
}
const messages = prev.messages.slice();
if (siteText) {
  messages.push({ role: 'user', content: 'Website content for enrichment:\n' + siteText });
}
return [{ json: { messages, website_text: siteText } }];
"""

    parse_lead_js = r"""const resp = $input.first().json;
let content = (resp.choices && resp.choices[0] && resp.choices[0].message.content) || '';
content = content.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
const start = content.indexOf('{');
const end = content.lastIndexOf('}');
if (start === -1) throw new Error('LLM did not return JSON: ' + content.slice(0, 200));
const out = JSON.parse(content.slice(start, end + 1));

const lead = $('Process Lead').first().json.body;
const emailOk = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(lead.email || '');
const scoreOk = Number.isFinite(Number(out.score)) && Number(out.score) >= 0 && Number(out.score) <= 100;
const tierOk = ['HOT', 'WARM', 'COLD'].includes(String(out.tier).toUpperCase());

return [{ json: {
  score: Number(out.score),
  tier: String(out.tier || '').toUpperCase(),
  reasons: Array.isArray(out.reasons) ? out.reasons : [],
  suggested_angle: out.suggested_angle || '',
  followup_email: out.followup_email || '',
  lead,
  checks: [
    { name: 'valid lead email', ok: emailOk, detail: lead.email || 'missing' },
    { name: 'score in range 0-100', ok: scoreOk, detail: String(out.score) },
    { name: 'tier is HOT/WARM/COLD', ok: tierOk, detail: String(out.tier) }
  ]
} }];
"""

    nodes = [
        node("Landing Page", "n8n-nodes-base.webhook", 2, {
            "httpMethod": "GET", "path": "lead-gen", "responseMode": "responseNode", "options": {},
        }, [0, 0], webhook_id="demo-lead-page"),
        node("Serve Landing Page", "n8n-nodes-base.respondToWebhook", 1.4, {
            "respondWith": "text", "responseBody": landing_html,
            "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]}},
        }, [220, 0]),
        node("Process Lead", "n8n-nodes-base.webhook", 2, {
            "httpMethod": "POST", "path": "lead-gen/process", "responseMode": "responseNode", "options": {},
        }, [0, 220], webhook_id="demo-lead-process"),
        node("Build Research Prompt", "n8n-nodes-base.code", 2, {"jsCode": build_prompt_js}, [220, 220]),
        node("Enrich Lead", "n8n-nodes-base.code", 2, {"jsCode": enrich_lead_js}, [440, 220]),
        node("LLM Score", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": LLM_URL,
            "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ messages: $json.messages, temperature: 0 }) }}",
            "options": {"timeout": 60000},
        }, [660, 220]),
        node("Parse Lead", "n8n-nodes-base.code", 2, {"jsCode": parse_lead_js}, [880, 220]),
        node("Report", "n8n-nodes-base.respondToWebhook", 1.4, {
            "respondWith": "json",
            "responseBody": "={{ JSON.stringify({ score: $json.score, tier: $json.tier, reasons: $json.reasons, suggested_angle: $json.suggested_angle, followup_email: $json.followup_email, checks: $json.checks }) }}",
            "options": {"responseHeaders": {"entries": [{"name": "Access-Control-Allow-Origin", "value": "*"}]}},
        }, [1120, 100]),
        node("Create Leads Table", "n8n-nodes-base.dataTable", 1.1, {
            "resource": "table", "operation": "create", "tableName": "leads",
            "columns": {"column": [
                {"name": "name", "type": "string"},
                {"name": "email", "type": "string"},
                {"name": "company", "type": "string"},
                {"name": "website", "type": "string"},
                {"name": "score", "type": "number"},
                {"name": "tier", "type": "string"},
                {"name": "message", "type": "string"},
            ]},
            "options": {"createIfNotExists": True},
        }, [1120, 300]),
        node("Log Lead", "n8n-nodes-base.dataTable", 1.1, {
            "resource": "row", "operation": "insert",
            "dataTableId": {"__rl": True, "mode": "name", "value": "leads"},
            "columns": {"mappingMode": "defineBelow", "value": {
                "name": "={{ $('Parse Lead').first().json.lead.name }}",
                "email": "={{ $('Parse Lead').first().json.lead.email }}",
                "company": "={{ $('Parse Lead').first().json.lead.company }}",
                "website": "={{ $('Parse Lead').first().json.lead.website }}",
                "score": "={{ Number($('Parse Lead').first().json.score) }}",
                "tier": "={{ $('Parse Lead').first().json.tier }}",
                "message": "={{ $('Parse Lead').first().json.lead.message }}",
            }},
            "options": {},
        }, [1340, 300]),
    ]

    connections = {
        "Landing Page": {"main": [[{"node": "Serve Landing Page", "type": "main", "index": 0}]]},
        "Process Lead": {"main": [[{"node": "Build Research Prompt", "type": "main", "index": 0}]]},
        "Build Research Prompt": {"main": [[{"node": "Enrich Lead", "type": "main", "index": 0}]]},
        "Enrich Lead": {"main": [[{"node": "LLM Score", "type": "main", "index": 0}]]},
        "LLM Score": {"main": [[{"node": "Parse Lead", "type": "main", "index": 0}]]},
        "Parse Lead": {"main": [[
            {"node": "Report", "type": "main", "index": 0},
            {"node": "Create Leads Table", "type": "main", "index": 0},
        ]]},
        "Create Leads Table": {"main": [[{"node": "Log Lead", "type": "main", "index": 0}]]},
    }

    return {
        "id": "demoLeadGen00001",
        "name": "Demo 02 · Lead Generation & Enrichment",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "versionId": str(uuid.uuid4()),
        "meta": {"templateCredsSetupCompleted": True},
        "tags": [],
        "pinData": {},
    }


def build_support_agent():
    chat_html = """<!doctype html>
<html><head><meta charset="utf-8"><title>AI Support Agent Demo</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b1220;--card:#111b2e;--line:#1e2b45;--text:#e8eefc;--muted:#8fa3c8;--accent:#4f8cff;--ok:#22c55e;--warn:#f59e0b}
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:linear-gradient(160deg,#0b1220,#0e1730);color:var(--text);height:100vh;display:flex}
.wrap{max-width:980px;margin:0 auto;padding:28px 20px;display:flex;gap:18px;width:100%}
.chat{flex:2;background:var(--card);border:1px solid var(--line);border-radius:14px;display:flex;flex-direction:column;overflow:hidden}
.chat header{padding:14px 18px;border-bottom:1px solid var(--line);font-weight:700}
.msgs{flex:1;overflow:auto;padding:18px;display:flex;flex-direction:column;gap:10px}
.msg{max-width:78%;padding:10px 14px;border-radius:12px;white-space:pre-wrap}
.msg.user{align-self:flex-end;background:var(--accent);color:#fff}
.msg.bot{align-self:flex-start;background:#0a1122;border:1px solid var(--line)}
.typing{color:var(--muted);font-style:italic}
.form{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line)}
input{flex:1;background:#0a1122;border:1px solid var(--line);color:var(--text);border-radius:9px;padding:10px 12px;font:inherit}
.btn{background:var(--accent);color:#fff;border:0;border-radius:9px;padding:10px 16px;font-weight:600;cursor:pointer}
.trace{flex:1;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
.trace h3{margin:0 0 12px;font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.trace .row{margin:10px 0;font-size:14px}.trace .k{color:var(--muted);font-size:12px}
.badge{display:inline-block;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:700}
.badge.handoff{background:rgba(245,158,11,.15);color:var(--warn)}.badge.auto{background:rgba(34,197,94,.15);color:var(--ok)}
</style></head><body><div class="wrap">
<div class="chat"><header>Northwind Bakery · Support</header>
<div class="msgs" id="msgs"><div class="msg bot">Hi! I&#39;m the Northwind assistant. Ask about orders, pricing or delivery — if I can&#39;t help, I&#39;ll pass you to a human.</div></div>
<div class="form"><input id="input" placeholder="Type a message..." autocomplete="off"><button class="btn" id="send">Send</button></div></div>
<div class="trace"><h3>Agent trace</h3><div id="trace"><p style="color:var(--muted)">Waiting for the first message...</p></div></div>
</div>
<script>
const msgs=document.getElementById('msgs'),input=document.getElementById('input'),trace=document.getElementById('trace');
let history=[];
const sessionId='s-'+Math.random().toString(36).slice(2,10);
document.getElementById('send').onclick=send;
input.addEventListener('keydown',e=>{if(e.key==='Enter')send()});
function add(text,cls){const d=document.createElement('div');d.className='msg '+cls;d.textContent=text;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;return d}
async function send(){
  const text=input.value.trim();if(!text)return;input.value='';
  add(text,'user');history.push({role:'user',content:text});
  const t=add('typing...','bot typing');
  try{
    const r=await fetch('/webhook/support-agent/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:sessionId,messages:history})});
    const d=await r.json();
    t.remove();add(d.reply,'bot');history.push({role:'assistant',content:d.reply});
    trace.innerHTML='<div class="row"><div class="k">intent</div><div>'+d.intent+'</div></div>'
      +'<div class="row"><div class="k">sentiment</div><div>'+d.sentiment+'</div></div>'
      +'<div class="row"><span class="badge '+(d.handoff?'handoff':'auto')+'">'+(d.handoff?'HANDOFF TO HUMAN':'AUTO-RESOLVED')+'</span></div>'
      +(d.handoff_reason?'<div class="row"><div class="k">reason</div><div>'+d.handoff_reason+'</div></div>':'');
  }catch(e){t.textContent='Error: '+e.message}
}
</script></body></html>"""

    agent_prompt_js = """const raw = $input.first().json;
const payload = raw.body || raw;
const messages = Array.isArray(payload.messages) ? payload.messages.slice(-12) : [];
const system = %s;
return [{ json: { messages: [{ role: 'system', content: system }].concat(messages) } }];
""" % json.dumps(
        "You are the support assistant for 'Northwind Bakery', a small bakery. "
        "You answer questions about products, prices, opening hours and delivery, and you help customers place orders. "
        "Business facts: open Mon-Sat 8:00-19:00; sourdough $6; gluten-free bread $8; delivery within the city $5 (free over $40); "
        "custom cakes need 48h notice; refunds handled by a human. "
        "Rules: be concise and friendly. Never invent prices or policies. "
        "Escalate (handoff=true) when: the customer asks for a refund or complaint, asks for something outside the menu, "
        "is clearly frustrated, or explicitly asks for a human, or provides contact details to be called back. "
        "Return ONLY a JSON object: "
        '{"reply": "<message to the customer>", "intent": "<short label>", "sentiment": "positive"|"neutral"|"negative", '
        '"handoff": true|false, "handoff_reason": "<short reason or empty>"}'
    )

    parse_agent_js = """const resp = $input.first().json;
let content = (resp.choices && resp.choices[0] && resp.choices[0].message.content) || '';
content = content.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
const start = content.indexOf('{');
const end = content.lastIndexOf('}');
if (start === -1) throw new Error('Agent did not return JSON: ' + content.slice(0, 200));
const out = JSON.parse(content.slice(start, end + 1));
const chatRaw = $('Chat').first().json;
const chatBody = chatRaw.body || chatRaw;
const session = chatBody.session_id || 'demo-session';

return [{ json: {
  reply: out.reply || 'Let me connect you with a human.',
  intent: out.intent || 'unknown',
  sentiment: out.sentiment || 'neutral',
  handoff: Boolean(out.handoff),
  handoff_reason: out.handoff_reason || '',
  session_id: session,
  transcript: (chatBody.messages || []).map(m => (m.role === 'user' ? 'Customer: ' : 'Agent: ') + m.content).join('\\n'),
} }];
"""

    nodes = [
        node("Chat Page", "n8n-nodes-base.webhook", 2, {
            "httpMethod": "GET", "path": "support-agent", "responseMode": "responseNode", "options": {},
        }, [0, 0], webhook_id="demo-agent-page"),
        node("Serve Chat Page", "n8n-nodes-base.respondToWebhook", 1.4, {
            "respondWith": "text", "responseBody": chat_html,
            "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/html; charset=utf-8"}]}},
        }, [220, 0]),
        node("Chat", "n8n-nodes-base.webhook", 2, {
            "httpMethod": "POST", "path": "support-agent/chat", "responseMode": "responseNode", "options": {},
        }, [0, 220], webhook_id="demo-agent-chat"),
        node("Agent Prompt", "n8n-nodes-base.code", 2, {"jsCode": agent_prompt_js}, [220, 220]),
        node("LLM Agent", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": LLM_URL,
            "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ messages: $json.messages, temperature: 0.2 }) }}",
            "options": {"timeout": 60000},
        }, [440, 220]),
        node("Parse Agent Reply", "n8n-nodes-base.code", 2, {"jsCode": parse_agent_js}, [660, 220]),
        node("Reply", "n8n-nodes-base.respondToWebhook", 1.4, {
            "respondWith": "json",
            "responseBody": "={{ JSON.stringify({ reply: $json.reply, intent: $json.intent, sentiment: $json.sentiment, handoff: $json.handoff, handoff_reason: $json.handoff_reason }) }}",
            "options": {"responseHeaders": {"entries": [{"name": "Access-Control-Allow-Origin", "value": "*"}]}},
        }, [900, 100]),
        node("Needs Handoff?", "n8n-nodes-base.if", 2.2, {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{
                    "id": str(uuid.uuid4()),
                    "leftValue": "={{ $json.handoff }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        }, [900, 320]),
        node("Create Handoffs Table", "n8n-nodes-base.dataTable", 1.1, {
            "resource": "table", "operation": "create", "tableName": "handoffs",
            "columns": {"column": [
                {"name": "session_id", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "intent", "type": "string"},
                {"name": "sentiment", "type": "string"},
                {"name": "transcript", "type": "string"},
            ]},
            "options": {"createIfNotExists": True},
        }, [1120, 400]),
        node("Log Handoff", "n8n-nodes-base.dataTable", 1.1, {
            "resource": "row", "operation": "insert",
            "dataTableId": {"__rl": True, "mode": "name", "value": "handoffs"},
            "columns": {"mappingMode": "defineBelow", "value": {
                "session_id": "={{ $('Parse Agent Reply').first().json.session_id }}",
                "reason": "={{ $('Parse Agent Reply').first().json.handoff_reason }}",
                "intent": "={{ $('Parse Agent Reply').first().json.intent }}",
                "sentiment": "={{ $('Parse Agent Reply').first().json.sentiment }}",
                "transcript": "={{ $('Parse Agent Reply').first().json.transcript }}",
            }},
            "options": {},
        }, [1340, 400]),
    ]

    connections = {
        "Chat Page": {"main": [[{"node": "Serve Chat Page", "type": "main", "index": 0}]]},
        "Chat": {"main": [[{"node": "Agent Prompt", "type": "main", "index": 0}]]},
        "Agent Prompt": {"main": [[{"node": "LLM Agent", "type": "main", "index": 0}]]},
        "LLM Agent": {"main": [[{"node": "Parse Agent Reply", "type": "main", "index": 0}]]},
        "Parse Agent Reply": {"main": [[
            {"node": "Reply", "type": "main", "index": 0},
            {"node": "Needs Handoff?", "type": "main", "index": 0},
        ]]},
        "Needs Handoff?": {"main": [
            [{"node": "Create Handoffs Table", "type": "main", "index": 0}],
            [],
        ]},
        "Create Handoffs Table": {"main": [[{"node": "Log Handoff", "type": "main", "index": 0}]]},
    }

    return {
        "id": "demoSupportAgent1",
        "name": "Demo 03 · AI Support Agent (webchat + handoff)",
        "nodes": nodes,
        "connections": connections,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "versionId": str(uuid.uuid4()),
        "meta": {"templateCredsSetupCompleted": True},
        "tags": [],
        "pinData": {},
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    for workflow, filename in (
        (build_doc_automation(), "doc-automation.json"),
        (build_lead_gen(), "lead-gen.json"),
        (build_support_agent(), "ai-support-agent.json"),
    ):
        path = os.path.join(OUT, filename)
        with open(path, "w") as f:
            json.dump(workflow, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
