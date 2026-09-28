# AI Automation Demos

Production-style automation workflows built with **n8n** + **LLM agents**, designed for small businesses that want to remove repetitive manual work.

These are the reference implementations behind my Upwork services. Each demo is a self-contained n8n workflow (importable JSON) with sample data and a short architecture note.

## Demos

| # | Demo | What it does | Status |
|---|------|--------------|--------|
| 01 | [Invoice & document automation](docs/doc-automation.md) | Upload a PDF invoice → LLM extracts structured fields → validation rules flag mismatches → CSV/Sheets row + HTML report | ✅ |
| 02 | [Lead generation & enrichment](docs/lead-gen.md) | Form webhook → enrich + score leads with an LLM → structured table → follow-up email draft | 🚧 |
| 03 | [AI support agent](docs/ai-support-agent.md) | Webchat agent on n8n: business FAQ + lead qualification + human handoff | 🚧 |

## Architecture

```
Client (form / upload / chat)
        │  webhook
        ▼
  ┌───────────┐     ┌──────────────────────┐
  │   n8n     │────▶│  LLM endpoint        │
  │ workflow  │◀────│  (OpenAI-compatible) │
  └─────┬─────┘     └──────────────────────┘
        │
        ├──▶ validation / business rules (Code nodes)
        ├──▶ CSV / Google Sheets / CRM adapter
        └──▶ HTML report or chat reply
```

The workflows call an **OpenAI-compatible chat endpoint**. By default they point to a local `llm-router` at `http://127.0.0.1:8770/chat` (DeepSeek backend), so the whole demo runs with zero external SaaS dependencies. To use OpenAI, Groq, Ollama or any other provider, change the URL in the `LLM` HTTP node — the request/response shape is the standard `messages` → `choices[0].message.content`.

## Run it

1. Import a workflow: n8n → *Import from File* → `workflows/<demo>.json`
2. Replace the LLM URL in the `LLM` node if you are not running the local router
3. Activate the workflow and use the webhook URL shown on the webhook node

Full instructions per demo in `docs/`.

## License

MIT
