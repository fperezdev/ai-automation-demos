#!/usr/bin/env python3
"""Build the n8n workflow for Demo 04 — WhatsApp Dental Assistant (RAG).

The workflow answers WhatsApp questions for an invented dental clinic using a
retrieval-augmented generation (RAG) step: a lightweight TF-IDF retrieval over a
small knowledge base selects the relevant FAQ chunks, which are injected as
context into the LLM prompt. Channel is the WhatsApp Cloud API (Meta).

Regenerate with:
    python scripts/build_whatsapp_agent.py
"""
import json
import os
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "workflows")

LLM_URL = "http://127.0.0.1:8770/chat"

# ---------------------------------------------------------------------------
# Business: invented dental clinic (Ñuñoa, Santiago de Chile)
# ---------------------------------------------------------------------------
BUSINESS = {
    "name": "Clínica Dental Sonrisa Ñuñoa",
    "whatsapp_display": "+56 9 5555 0101",
    "facts": (
        "Clínica dental de barrio en Ñuñoa, Santiago. Equipo de 3 odontólogos y "
        "2 asistentes. Antes respondían el WhatsApp a mano; este asistente "
        "responde las consultas frecuentes y deriva a una persona cuando corresponde."
    ),
}

# Knowledge base (chunks). Kept inside the "Retrieve FAQ" node so the workflow is
# self-contained and importable.
KB = [
    {
        "id": "horarios",
        "topic": "Horarios de atención",
        "text": (
            "Atendemos de lunes a viernes de 9:00 a 19:00 y sábados de 10:00 a 14:00. "
            "Domingos y festivos permanecemos cerrados. La última hora que se puede agendar "
            "es 30 minutos antes del cierre."
        ),
    },
    {
        "id": "precios",
        "topic": "Precios y presupuestos",
        "text": (
            "Consulta de evaluación: $15.000. Destartraje / limpieza dental: $35.000. "
            "Blanqueamiento: $120.000. Resina (restauración): $45.000. Extracción simple: $40.000. "
            "Endodoncia: desde $150.000. El presupuesto definitivo se entrega después de la evaluación."
        ),
    },
    {
        "id": "ubicacion",
        "topic": "Ubicación y cómo llegar",
        "text": (
            "Estamos en Av. Irarrázaval 3421, Ñuñoa, Santiago (segundo piso). A 3 minutos "
            "caminando del Metro Chile España (Línea 3). El edificio tiene estacionamiento con convenio."
        ),
    },
    {
        "id": "agenda",
        "topic": "Agendar, reagendar o cancelar hora",
        "text": (
            "Puedes agendar por WhatsApp: envíanos tu nombre completo, RUT y el día u horario de "
            "preferencia, y confirmamos en el momento. Para reagendar o cancelar, avisa con al menos "
            "24 horas de anticipación, sin costo."
        ),
    },
    {
        "id": "pagos",
        "topic": "Convenios, previsión y formas de pago",
        "text": (
            "Atendemos Fonasa (con bono) e Isapre (modalidad reembolso). Aceptamos débito, crédito "
            "hasta 3 cuotas sin interés y transferencia. Convenios con empresas: 15% de descuento "
            "presentando credencial."
        ),
    },
    {
        "id": "urgencias",
        "topic": "Urgencias dentales",
        "text": (
            "Si tienes dolor agudo —una muela que duele mucho—, una emergencia o una urgencia dental, "
            "tiene preferencia: contamos con cupos de urgencia el mismo día dentro del horario de atención. "
            "Fuera de horario derivamos a un servicio de urgencia dental 24 horas."
        ),
    },
    {
        "id": "servicios",
        "topic": "Servicios y tratamientos",
        "text": (
            "Realizamos odontología general, limpiezas, blanqueamientos, restauraciones (resinas), "
            "endodoncias, extracciones y control de niños. Ortodoncia e implantes se evalúan con "
            "presupuesto aparte."
        ),
    },
]

# ---------------------------------------------------------------------------
# Code nodes
# ---------------------------------------------------------------------------

VERIFY_JS = r"""// WhatsApp Cloud API webhook verification (GET).
// Meta sends ?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
// We echo back hub.challenge when the token matches WHATSAPP_VERIFY_TOKEN
// (if the env var is unset we accept any token so the demo works out of the box).
const q = $input.first().json.query || {};
const mode = q['hub.mode'] || q.hub_mode || '';
const token = q['hub.verify_token'] || q.hub_verify_token || '';
const challenge = q['hub.challenge'] || q.hub_challenge || '';
const expected = (() => { try { return ($env && $env.WHATSAPP_VERIFY_TOKEN) || ''; } catch (e) { return ''; } })();
const ok = mode === 'subscribe' && (!expected || token === expected);
return [{ json: { ok, challenge: ok ? challenge : '', body: ok ? challenge : 'forbidden' } }];
"""

PARSE_INCOMING_JS = r"""// Accepts both a real WhatsApp Cloud API payload and a simple test payload:
//   real : { object: 'whatsapp_business_account', entry: [...] }
//   test : { messages: [{role,content}...] }  or  { text: '...', history: [...] }
const raw = $input.first().json;
const body = raw.body || raw;

let sender = '';
let text = '';
let messages = [];

if (body.object === 'whatsapp_business_account') {
  // ---- WhatsApp Cloud API ----
  const change = (((body.entry || [])[0] || {}).changes || [])[0] || {};
  const value = change.value || {};
  const msg = ((value.messages || [])[0]) || {};
  sender = msg.from || '';
  text = (msg.text && msg.text.body) || (msg.button && msg.button.text) || '';
  // Meta delivers one message per webhook; conversation context lives in a
  // session store in production (see docs). The demo answers each turn from the KB.
  messages = [{ role: 'user', content: text }];
} else if (Array.isArray(body.messages)) {
  // ---- test payload with a full conversation ----
  messages = body.messages.filter((m) => m && m.content).map((m) => ({ role: m.role || 'user', content: String(m.content) }));
  sender = body.from || 'test-user';
  const last = [...messages].reverse().find((m) => m.role === 'user');
  text = last ? last.content : '';
} else {
  // ---- test payload, single message ----
  text = String(body.text || '');
  sender = body.from || 'test-user';
  messages = [{ role: 'user', content: text }];
}

if (!text) {
  throw new Error('No message text found in payload');
}
return [{ json: { sender, text, messages } }];
"""

RETRIEVE_JS = (
    r"""// Lightweight retrieval-augmented generation (RAG) step.
// TF-IDF over the clinic knowledge base: tokenize (Spanish, accent- and
// stopword-normalised), score each chunk against the user's question with a
// cosine-like tf-idf dot product, and keep the best matches.
const KB = """
    + json.dumps(KB, ensure_ascii=False)
    + r""";

const STOP = new Set(('de la que el en y a los del se las por un para con no una su al lo como mas pero sus le ya o este si porque esta entre cuando muy sin sobre tambien me hasta hay donde quien desde todo nos durante todos uno les ni contra otros ese eso ante ellos e esto mi antes algunos que unos yo otro otras otra el tanto esa estos mucho quienes nada muchos cual poco ella estar estas algunas algo nosotros mi mis tu te ti tus ellas nosotras vosostros vosostras os mio mia mios mias tuyo tuya tuyos tuyas suyo suya suyos suyas nuestro nuestra nuestros nuestras vuestro vuestra vuestros vuestras esos esas estoy estas esta estamos estais estan este este estemos esteis esten estare estaras estara estaremos estareis estaran estaria estarias estariamos estariais estarian estaba estabas estabamos estabais estaban estuve estuviste estuvo estuvimos estuvisteis estuvieron estuviera estuvieras estuvieramos estuvierais estuvieran estuviese estuvieses estuviesemos estuvieseis estuviesen estando estado estada estados estadas estad hola buenas buenos favor gracias queria quisiera necesito podrian puede podria tienen tiene hay'.split(' ')));

function norm(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ');
}
function toks(s) {
  return norm(s)
    .split(/\s+/)
    .filter((t) => t.length > 2 && !STOP.has(t));
}

// Document frequency for the idf term.
const docs = KB.map((d) => toks(d.topic + ' ' + d.text));
const df = {};
for (const doc of docs) {
  for (const t of new Set(doc)) df[t] = (df[t] || 0) + 1;
}
const N = KB.length;
const idf = (t) => Math.log(1 + N / (1 + (df[t] || 0)));

const query = toks($json.text);
const qset = {};
for (const t of query) qset[t] = (qset[t] || 0) + 1;

const scored = KB.map((d, i) => {
  const doc = docs[i];
  const len = doc.length || 1;
  let score = 0;
  for (const t of Object.keys(qset)) {
    const tf = doc.filter((w) => w === t).length / len;
    score += (qset[t] / query.length) * tf * idf(t);
  }
  return { id: d.id, topic: d.topic, text: d.text, score: Number(score.toFixed(4)) };
});

scored.sort((a, b) => b.score - a.score);
const top = scored.filter((s) => s.score > 0).slice(0, 3);
const match = top.length ? top[0].score : 0;

return [{ json: {
  sender: $json.sender,
  text: $json.text,
  messages: $json.messages,
  retrieved: top,
  retrieval_score: match,
  has_context: top.length > 0,
} }];
"""
)

BUILD_PROMPT_JS = (
    r"""// Build the RAG-augmented prompt: retrieved KB chunks go in as context.
const prev = $input.first().json;
const context = (prev.retrieved || [])
  .map((r) => '- [' + r.topic + '] ' + r.text)
  .join('\n');

const system = """
    + json.dumps(
        "Eres el asistente virtual por WhatsApp de la \"Clínica Dental Sonrisa Ñuñoa\", "
        "una clínica dental en Ñuñoa, Santiago de Chile. "
        + BUSINESS["facts"]
        + " Respondes SOLO con la información del CONTEXTO entregado; si algo no está en el "
        "contexto, no lo inventes: ofrece derivar con una persona del equipo. "
        "Estilo: mensajes breves y cordiales de WhatsApp, en español neutro con tuteo. "
        "Usa siempre 'tú'/'tienes'/'puedes'; NUNCA uses voseo ('vos', 'tenés', 'tenís', 'podés', 'querés', 'sabés'). "
        "Sin markdown, máximo 3 oraciones. Nunca des diagnósticos ni indicaciones clínicas. "
        "Marca handoff=true cuando: sea una urgencia fuera de horario, un reclamo o problema, "
        "el cliente pida hablar con una persona, o la respuesta no esté en el contexto. "
        "Devuelve SOLO un objeto JSON: {\"reply\": \"<mensaje>\", \"intent\": \"<etiqueta>\", "
        "\"sentiment\": \"positive\"|\"neutral\"|\"negative\", \"handoff\": true|false, "
        "\"handoff_reason\": \"<motivo o vacío>\"}",
        ensure_ascii=False,
    )
    + r""";

const messages = [{ role: 'system', content: system }];
messages.push({ role: 'user', content: 'CONTEXTO (base de conocimiento):\n' + (context || '(sin coincidencias en la base)') });
for (const m of (prev.messages || [])) messages.push(m);

return [{ json: {
  messages,
  sender: prev.sender,
  intent_hint: prev.has_context ? 'kb_match' : 'no_context',
  sources: (prev.retrieved || []).map((r) => r.topic),
} }];
"""
)

PARSE_REPLY_JS = r"""const resp = $input.first().json;
let content = (resp.choices && resp.choices[0] && resp.choices[0].message.content) || '';
content = content.trim().replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
const start = content.indexOf('{');
const end = content.lastIndexOf('}');

let out;
if (start === -1 || end === -1) {
  // Model returned free text instead of JSON. Salvage a clean reply and only
  // escalate if the wording really signals a handoff.
  const t = content
    .replace(/\s*"?\b(intent|sentiment|handoff|handoff_reason)\b"?\s*:[\s\S]*$/i, '')
    .trim()
    .replace(/[\s,;:"}]+$/, '');
  const esc = /deriv|humano|una persona|urgencia dental 24|fuera de (nuestro )?horario/i.test(t);
  out = { reply: t || 'En breve te contacta una persona del equipo.', intent: 'unstructured', sentiment: 'neutral', handoff: esc, handoff_reason: esc ? 'Derivación en respuesta libre' : '' };
} else {
  out = JSON.parse(content.slice(start, end + 1));
}

const prev = $('Build Prompt').first().json;

// Deterministic guard: normalise any voseo the model slips in.
const TUTEO = [
  [/\bten[eé]s\b/gi, 'tienes'], [/\bten[ií]s\b/gi, 'tienes'], [/\bpod[eé]s\b/gi, 'puedes'],
  [/\bquer[eé]s\b/gi, 'quieres'], [/\bsab[eé]s\b/gi, 'sabes'], [/\bdec[ií]s\b/gi, 'dices'],
  [/\bven[ií]s\b/gi, 'vienes'], [/\bsos\b/gi, 'eres'], [/\bvos\b/gi, 'tú'],
];
const norm = (s) => TUTEO.reduce((acc, [re, rep]) => acc.replace(re, rep), String(s || ''));
const reply = norm(out.reply || 'En breve te contacta una persona del equipo.');

const sender = prev.sender || 'test-user';
const transcript = (prev.messages || [])
  .filter((m) => m.role !== 'system')
  .map((m) => (m.role === 'user' ? 'Cliente: ' : 'Asistente: ') + m.content)
  .join('\n') + '\nAsistente: ' + reply;

return [{ json: {
  reply,
  intent: out.intent || 'unknown',
  sentiment: out.sentiment || 'neutral',
  handoff: Boolean(out.handoff),
  handoff_reason: out.handoff_reason || '',
  sender,
  sources: prev.sources || [],
  transcript,
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


def build():
    nodes = [
        # --- Single webhook: Meta uses ONE callback URL for GET (verification) and POST (messages) ---
        node("WhatsApp Webhook", "n8n-nodes-base.webhook", 2, {
            "multipleMethods": True, "httpMethod": ["GET", "POST"],
            "path": "whatsapp-dental", "responseMode": "responseNode", "options": {},
        }, [0, 120], webhook_id="demo-whatsapp"),

        node("Check Token", "n8n-nodes-base.code", 2, {"jsCode": VERIFY_JS}, [440, 0]),

        node("Verify Response", "n8n-nodes-base.respondToWebhook", 1.4, {
            "respondWith": "text", "responseBody": "={{ $json.body }}",
            "options": {"responseHeaders": {"entries": [{"name": "Content-Type", "value": "text/plain; charset=utf-8"}]}},
        }, [660, 0]),

        node("Parse Incoming", "n8n-nodes-base.code", 2, {"jsCode": PARSE_INCOMING_JS}, [220, 240]),

        node("Retrieve FAQ (RAG)", "n8n-nodes-base.code", 2, {"jsCode": RETRIEVE_JS}, [440, 240]),

        node("Build Prompt", "n8n-nodes-base.code", 2, {"jsCode": BUILD_PROMPT_JS}, [660, 240]),

        node("LLM Agent", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST", "url": LLM_URL, "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ messages: $json.messages, temperature: 0.2, response_format: { type: 'json_object' } }) }}",
            "options": {"timeout": 60000},
        }, [880, 240]),

        node("Parse Reply", "n8n-nodes-base.code", 2, {"jsCode": PARSE_REPLY_JS}, [1100, 240]),

        node("Reply", "n8n-nodes-base.respondToWebhook", 1.4, {
            "respondWith": "json",
            "responseBody": "={{ JSON.stringify({ reply: $json.reply, intent: $json.intent, sentiment: $json.sentiment, handoff: $json.handoff, handoff_reason: $json.handoff_reason, sources: $json.sources }) }}",
            "options": {"responseHeaders": {"entries": [{"name": "Access-Control-Allow-Origin", "value": "*"}]}},
        }, [1320, 120]),

        # --- Handoff logging ---
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
        }, [1320, 380]),

        node("Create Handoffs Table", "n8n-nodes-base.dataTable", 1.1, {
            "resource": "table", "operation": "create", "tableName": "wa_handoffs",
            "columns": {"column": [
                {"name": "sender", "type": "string"},
                {"name": "reason", "type": "string"},
                {"name": "intent", "type": "string"},
                {"name": "sentiment", "type": "string"},
                {"name": "transcript", "type": "string"},
            ]},
            "options": {"createIfNotExists": True},
        }, [1540, 460]),

        node("Log Handoff", "n8n-nodes-base.dataTable", 1.1, {
            "resource": "row", "operation": "insert",
            "dataTableId": {"__rl": True, "mode": "name", "value": "wa_handoffs"},
            "columns": {"mappingMode": "defineBelow", "value": {
                "sender": "={{ $('Parse Reply').first().json.sender }}",
                "reason": "={{ $('Parse Reply').first().json.handoff_reason }}",
                "intent": "={{ $('Parse Reply').first().json.intent }}",
                "sentiment": "={{ $('Parse Reply').first().json.sentiment }}",
                "transcript": "={{ $('Parse Reply').first().json.transcript }}",
            }},
            "options": {},
        }, [1760, 460]),

        # --- Outbound: send the reply through the WhatsApp Cloud API.
        # Disabled by default (needs WHATSAPP_TOKEN + WHATSAPP_PHONE_NUMBER_ID);
        # enable it once the Meta credentials are configured.
        node("Send via Graph API", "n8n-nodes-base.httpRequest", 4.2, {
            "method": "POST",
            "url": "=https://graph.facebook.com/v21.0/{{ $env.WHATSAPP_PHONE_NUMBER_ID }}/messages",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Authorization", "value": "=Bearer {{ $env.WHATSAPP_TOKEN }}"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ messaging_product: 'whatsapp', to: $json.sender, type: 'text', text: { body: $json.reply } }) }}",
            "options": {"timeout": 30000},
        }, [1540, 120], extra={"disabled": True}),
    ]

    connections = {
        "WhatsApp Webhook": {"main": [
            [{"node": "Check Token", "type": "main", "index": 0}],
            [{"node": "Parse Incoming", "type": "main", "index": 0}],
        ]},
        "Check Token": {"main": [[{"node": "Verify Response", "type": "main", "index": 0}]]},
        "Parse Incoming": {"main": [[{"node": "Retrieve FAQ (RAG)", "type": "main", "index": 0}]]},
        "Retrieve FAQ (RAG)": {"main": [[{"node": "Build Prompt", "type": "main", "index": 0}]]},
        "Build Prompt": {"main": [[{"node": "LLM Agent", "type": "main", "index": 0}]]},
        "LLM Agent": {"main": [[{"node": "Parse Reply", "type": "main", "index": 0}]]},
        "Parse Reply": {"main": [[
            {"node": "Reply", "type": "main", "index": 0},
            {"node": "Needs Handoff?", "type": "main", "index": 0},
        ]]},
        "Needs Handoff?": {"main": [[{"node": "Create Handoffs Table", "type": "main", "index": 0}], []]},
        "Create Handoffs Table": {"main": [[{"node": "Log Handoff", "type": "main", "index": 0}]]},
    }

    return {
        "id": "demoWhatsAppDental1",
        "name": "Demo 04 · WhatsApp Dental Assistant (RAG + Cloud API)",
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
    path = os.path.join(OUT, "whatsapp-dental-agent.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build(), f, ensure_ascii=False, indent=2)
    print("wrote", path)


if __name__ == "__main__":
    main()
