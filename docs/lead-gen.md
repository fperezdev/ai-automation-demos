# Demo 02 — Lead Generation & Enrichment

Turn raw form submissions into scored, enriched leads with a ready-to-send follow-up email.

## Problem

Leads arrive as plain form messages. Someone has to research the company, decide if it is worth pursuing, and write a follow-up email — usually hours later. Good leads go cold.

## What this workflow does

1. A **webhook serves a landing form** (`GET /webhook/lead-gen`).
2. The form posts to `POST /webhook/lead-gen/process`.
3. A **Code node enriches the lead**: if a website is provided, it fetches the page and strips it to plain text (no external APIs, no browser).
4. The **LLM scores the lead** (0-100) using the message, company data and the website content, and returns strict JSON:
   - `score` + `tier` (`HOT` / `WARM` / `COLD`)
   - `reasons[]` — why it scored that way
   - `suggested_angle` — how to approach
   - `followup_email` — a ready-to-send draft
5. **Validation checks** confirm the email format, score range and tier before the lead is accepted.
6. Every lead is **appended to the `leads` Data Table** (swap for your CRM) and the browser gets the full report instantly.

## Architecture

```
 landing form (browser)
        │  JSON
        ▼
 Webhook ──▶ Build Research Prompt ──▶ Enrich Lead (fetch + strip site) ──▶ LLM Score
                                                                              │ JSON
                          Create Leads Table ◀── Parse Lead ──▶ Respond report
                                  │
                                  ▼
                            Log Lead (Data Table: leads)
```

The LLM node calls an **OpenAI-compatible endpoint** (default: local router at `http://127.0.0.1:8770/chat`).

## Run it

1. Import `workflows/lead-gen.json` into n8n and activate it.
2. Open `http://<your-n8n>/webhook/lead-gen` and submit the form.
3. Or from the command line:

```sh
curl -X POST http://localhost:5678/webhook/lead-gen/process \
  -H 'Content-Type: application/json' \
  -d '{"name":"Jane Cooper","email":"jane@acme.com","company":"Acme Corp",
       "website":"https://example.com",
       "message":"We need to automate invoice processing, budget approved for this quarter."}'
```

## Production adapters

| Demo uses | Swap for |
|---|---|
| n8n Data Table `leads` | HubSpot / Pipedrive / Airtable / your CRM |
| Website fetch in a Code node | Clearbit / Apollo / Hunter for richer enrichment |
| `followup_email` returned in the UI | Gmail / Outlook node to send it automatically |
| Local LLM router | OpenAI / Anthropic / any OpenAI-compatible endpoint |

Scoring rules are plain JavaScript in the *Parse Lead* node — adjust the rubric, weights or add your own qualification criteria.