# Demo 01 — Invoice & Document Automation

Turn a folder of PDF invoices into a validated ledger, without manual typing.

## Problem

Small businesses receive invoices as PDF attachments. Someone has to open each one, copy the invoice number, date, vendor, amounts and tax into a spreadsheet, and hope no total is wrong. It is slow, boring and error-prone.

## What this workflow does

1. A **webhook serves an upload page** (`GET /webhook/doc-automation`).
2. The PDF is posted to `POST /webhook/doc-automation/process`.
3. **Extract from File** pulls the raw text out of the PDF.
4. An **LLM extracts structured fields** (invoice number, date, vendor, currency, line items, subtotal, tax, total) and returns strict JSON.
5. A **Code node runs validation rules**:
   - required fields present
   - date format `YYYY-MM-DD`
   - line items sum matches the subtotal
   - subtotal + tax matches the total
6. Every document is **appended to the `invoices` ledger** (n8n Data Table; swap for Google Sheets, Airtable or your CRM).
7. The browser gets an instant report with a `PASS` / `REVIEW` badge and the failed checks highlighted.

`REVIEW` means "a human should look at this one" — exactly the invoices you want flagged: total mismatches, missing fields, wrong dates.

## Architecture

```
 upload page (browser)
        │  multipart PDF
        ▼
 Webhook ──▶ Extract from File ──▶ Build LLM Request ──▶ LLM (HTTP)
                                                          │ JSON
                                                          ▼
                        Create Data Table ◀── Parse & Validate ──▶ Respond report
                                │
                                ▼
                          Log to Ledger (Data Table: invoices)
```

The LLM node calls an **OpenAI-compatible endpoint**. Default: a local router at `http://127.0.0.1:8770/chat` (DeepSeek `deepseek-flash`). Change the URL to use OpenAI, Groq, Ollama, etc.

## Run it

1. Import `workflows/doc-automation.json` into n8n.
2. Activate the workflow (production webhooks are only served by active workflows).
3. Open `http://<your-n8n>/webhook/doc-automation` and upload one of the sample invoices.
4. Or from the command line:

```sh
curl -F "data=@samples/invoice_001.pdf;type=application/pdf" \
     http://localhost:5678/webhook/doc-automation/process
```

Generate the sample PDFs yourself with:

```sh
pip install reportlab
python scripts/make_sample_invoices.py
```

- `invoice_001.pdf` / `invoice_002.pdf` → clean invoices (`PASS`)
- `invoice_003.pdf` → **deliberate total mismatch** (`REVIEW`) to show validation

## Production adapters

| Demo uses | Swap for |
|---|---|
| n8n Data Table `invoices` | Google Sheets / Airtable / Postgres / your ERP |
| Upload page | Email inbox trigger (IMAP node) or Drive folder watcher |
| Local LLM router | OpenAI / Anthropic / any OpenAI-compatible endpoint |

The validation rules are plain JavaScript in the *Parse & Validate* node, so they can be extended with your own checks (duplicate invoice detection, PO matching, currency limits).