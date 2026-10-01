# AI Automation Demos

Production-style automation workflows built with **n8n** + **LLM agents**, designed for small businesses that want to remove repetitive manual work.

These are the reference implementations behind my Upwork services. Each demo is a self-contained n8n workflow with sample data and a short architecture note.

## Quickstart (one command, no API keys)

```bash
make up      # starts n8n + a deterministic mock LLM
make demo    # drives all three workflows over HTTP and asserts on the results
make ui      # prints the URLs to open in the browser
make down    # stops everything
```

`make demo` starts the stack if needed and runs the end-to-end smoke test:

```
01 invoice automation
  PASS  invoice_001.pdf -> status PASS
  PASS  invoice_003.pdf -> status REVIEW (deliberate total mismatch caught)
02 lead generation & scoring
  PASS  hot lead -> tier HOT
  PASS  vague lead -> tier COLD
03 AI support agent (webchat + human handoff)
  PASS  price question -> answered without handoff
  PASS  refund request -> handoff true
✅ all 12 checks passed
```

Then open <http://localhost:5688> (n8n UI — on the first visit it asks you to create a local owner account; that stays on your machine) or jump straight to the demo pages served by the workflows:

| Page | URL |
|------|-----|
| Invoice upload | <http://localhost:5688/webhook/doc-automation> |
| Lead capture form | <http://localhost:5688/webhook/lead-gen> |
| Support chat | <http://localhost:5688/webhook/support-agent> |

### Why a *mock* LLM?

The workflows talk to any OpenAI-compatible chat endpoint (`messages` → `choices[0].message.content`). So the repo ships a tiny deterministic stand-in — [`scripts/mock_llm.py`](scripts/mock_llm.py), stdlib only — that answers the same contract with rules instead of a model:

| Workflow | What the mock does |
|----------|--------------------|
| doc-automation | regex parser over the text the PDF extractor produced — it really does read the PDF |
| lead-gen | deterministic scoring on the keywords found in the lead payload |
| ai-support-agent | canned policy answers + handoff detection |

That keeps the demos **runnable offline, in seconds, with zero cost and zero keys** — and because it is deterministic, the smoke test is meaningful instead of flaky. Swap `LLM_HOST` in `docker-compose.yml` (or the `LLM` node URL in the UI) for a real model to see the same pipelines answer with a real LLM.

## Demos

| # | Demo | What it does | Status |
|---|------|--------------|--------|
| 01 | [Invoice & document automation](docs/doc-automation.md) | Upload a PDF invoice → LLM extracts structured fields → validation rules flag mismatches → Data Table ledger + HTML report | ✅ |
| 02 | [Lead generation & enrichment](docs/lead-gen.md) | Form webhook → site enrichment + LLM scoring (HOT/WARM/COLD) → Data Table + follow-up email draft | ✅ |
| 03 | [AI support agent](docs/ai-support-agent.md) | Webchat agent on n8n: business FAQ + qualification + human handoff with transcript logging | ✅ |

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

The workflows call an **OpenAI-compatible chat endpoint**. Out of the box they point at the mock LLM in this compose stack; in my own setup they point at a local `llm-router` (DeepSeek backend), so the whole thing runs with no external SaaS dependencies. To use OpenAI, Groq, Ollama or any other provider, change the URL in the `LLM` HTTP node — the request/response shape is the standard `messages` → `choices[0].message.content`.

## Run the workflows manually

If you'd rather not use Docker:

1. Import a workflow: n8n → *Import from File* → `workflows/<demo>.json`
2. Replace the LLM URL in the `LLM` node with your endpoint
3. Activate the workflow and use the webhook URL shown on the webhook node

Full instructions per demo in `docs/`.

## What's in the repo

```
docker-compose.yml          n8n + mock LLM, one command
docker/entrypoint.sh        imports + publishes the workflows on boot
scripts/mock_llm.py         deterministic OpenAI-compatible stand-in
scripts/smoke_test.sh       end-to-end test of all three demos
scripts/build_demo_workflows.py   generator for the workflow JSONs
workflows/*.json            the importable n8n workflows
samples/*.pdf               sample invoices (one with a deliberate mismatch)
docs/*.md                   architecture notes per demo
```

## License

MIT
