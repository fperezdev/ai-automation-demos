# Demo 03 — AI Support Agent (webchat + human handoff)

A chat agent that answers customer questions from your business facts, and escalates to a human exactly when it should.

## Problem

Small businesses lose sales answering the same questions all day, and ignore DMs at night. A naive bot that answers everything is worse than nothing — it needs to know when to hand off.

## What this workflow does

1. A **webhook serves a chat page** (`GET /webhook/support-agent`) — the page keeps the conversation history client-side, so the agent is stateless.
2. Each message posts to `POST /webhook/support-agent/chat` with `{session_id, messages[]}`.
3. The **LLM answers using only the business facts** defined in the system prompt (products, prices, hours, delivery, policies) and returns strict JSON:
   - `reply` — the message to the customer
   - `intent` + `sentiment`
   - `handoff` + `handoff_reason`
4. **Handoff rules** are explicit in the prompt: refunds, complaints, out-of-menu requests, frustrated customers or an explicit request for a human.
5. When handoff is triggered, the conversation is **logged to the `handoffs` Data Table** with the full transcript, so a human can pick it up with context.
6. The chat page also shows an **agent trace panel** (intent, sentiment, handoff badge) — useful when demoing or debugging.

## Architecture

```
 chat page (browser, keeps history)
        │  {session_id, messages}
        ▼
 Webhook ──▶ Agent Prompt ──▶ LLM Agent ──▶ Parse Agent Reply ──▶ Respond reply
                                                    │
                                                    ▼
                                        Needs Handoff? ──▶ Create Handoffs Table ──▶ Log Handoff
```

## Run it

1. Import `workflows/ai-support-agent.json` into n8n and activate it.
2. Open `http://<your-n8n>/webhook/support-agent` and chat.
3. Or from the command line:

```sh
curl -X POST http://localhost:5678/webhook/support-agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"s-1","messages":[{"role":"user","content":"Do you have gluten-free bread?"}]}'

curl -X POST http://localhost:5678/webhook/support-agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"s-1","messages":[{"role":"user","content":"My order arrived stale, I want a refund"}]}'
```

The second call returns `handoff: true` and writes the transcript to the `handoffs` table.

## Production adapters

| Demo uses | Swap for |
|---|---|
| Webchat page | WhatsApp Cloud API / Telegram / Instagram DM adapters (same agent node) |
| Client-side history | Postgres/Redis session store for multi-channel memory |
| `handoffs` Data Table | Slack / email notification to the support team |
| Business facts in the prompt | RAG over your docs / product catalog |

The agent prompt is a single string in the *Agent Prompt* node — update the business facts and escalation rules without touching any code.