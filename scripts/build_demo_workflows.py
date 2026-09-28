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


def main():
    os.makedirs(OUT, exist_ok=True)
    workflow = build_doc_automation()
    path = os.path.join(OUT, "doc-automation.json")
    with open(path, "w") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
