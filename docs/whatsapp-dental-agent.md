# Demo 04 — WhatsApp Dental Assistant (RAG + WhatsApp Cloud API)

A WhatsApp assistant for a dental clinic that answers the questions patients ask
every day — opening hours, prices, location, how to book, insurance — straight
from a small knowledge base, and hands the conversation to a human when it should.

## Problem

A small clinic answers the same messages all day by hand and misses the ones that
arrive at night. A generic chatbot that improvises prices or clinical advice is
worse than nothing. The assistant must answer **only** from the clinic's real
information and know when to hand off.

## What this workflow does

1. **WhatsApp Cloud API channel.** A single URL — `https://<host>/webhook/whatsapp-dental` —
   serves both Meta webhook methods: `GET` performs the verification (echoes `hub.challenge`) and
   `POST` receives messages. The *WhatsApp Webhook* node uses *Allow Multiple HTTP Methods*
   (GET + POST), so each method has its own output. The same `POST` also accepts a simple test
   payload (`{from, text}` or `{from, messages[]}`), so the bot can be exercised without Meta
   credentials.
2. **RAG retrieval.** A *Retrieve FAQ* code node runs a lightweight TF-IDF retrieval
   (Spanish, accent- and stopword-normalised) over the clinic knowledge base and
   keeps the best matching chunks.
3. **Grounded answer.** The retrieved chunks are injected as context in the system
   prompt; the LLM answers **only** from that context and returns strict JSON
   (`reply`, `intent`, `sentiment`, `handoff`, `handoff_reason`).
4. **Human handoff.** Urgencies outside opening hours, complaints, or an explicit
   request for a person set `handoff: true`; the transcript is logged to the
   `wa_handoffs` Data Table.
5. **Deterministic output guard.** A small normaliser strips any voseo
   (*tenés/tenís*) the model slips in, keeping the tone neutral.

## Architecture

```
WhatsApp Cloud API ──▶ WhatsApp Incoming (webhook)
                              │
                              ▼
                       Parse Incoming ──▶ Retrieve FAQ (RAG, TF-IDF)
                              │                    │
                              │                    ▼
                              └──────────▶ Build Prompt (context + history)
                                                   │
                                                   ▼
                                              LLM Agent ──▶ Parse Reply
                                                               │
                                        ┌──────────────────────┴───────────────┐
                                        ▼                                      ▼
                                   Reply (webhook)                    Needs Handoff? ──▶ Log to wa_handoffs
```

## Knowledge base

Seven chunks live inside the *Retrieve FAQ (RAG)* node (so the workflow is
self-contained): horarios, precios, ubicación, agendar/reagendar, convenios y
pagos, urgencias, servicios.

## Run it

1. Import `workflows/whatsapp-dental-agent.json` into n8n and activate it.
2. Test a turn from the command line:

```sh
curl -X POST http://localhost:5678/webhook/whatsapp-dental \
  -H 'Content-Type: application/json' \
  -d '{"from":"56911110001","text":"hola, cuánto cuesta una limpieza dental?"}'
```

3. Run the full 3-conversation test suite and generate WhatsApp-style captures:

```sh
python scripts/run_whatsapp_tests.py
python scripts/make_whatsapp_captures.py
```

## Connecting the real channel

Set two environment variables and enable the *Send via Graph API* node:

| Env var | Value |
|---|---|
| `WHATSAPP_TOKEN` | Meta permanent access token |
| `WHATSAPP_PHONE_NUMBER_ID` | Cloud API phone number ID |

Meta's webhook must point at `https://<your-host>/webhook/whatsapp-dental/hook`.
For a test/demo you can use Meta's free Cloud API test number — no SIM required.

## Production adapters

| Demo uses | Swap for |
|---|---|
| Stateless per-message handling | A Postgres/Redis session store for multi-turn memory |
| `wa_handoffs` Data Table | Slack / email alert to the clinic's front desk |
| TF-IDF retrieval in a Code node | A vector store (pgvector, Qdrant) with embeddings |
| Business KB in the node | RAG over the clinic's site, price list and FAQs |
