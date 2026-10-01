#!/usr/bin/env python3
"""Deterministic, OpenAI-compatible stand-in for the LLM used by these demos.

Why this exists
---------------
The three workflows are built to talk to *any* OpenAI-compatible chat endpoint:
a local model, OpenAI, Groq, Ollama, together with an in-house router... To let
anyone run the demos end to end with **zero API keys and zero cost**, this script
answers the exact same `POST /chat` contract the workflows expect, with rule-based
logic instead of a model:

| Workflow            | What the mock does                                                    |
|---------------------|-----------------------------------------------------------------------|
| doc-automation      | regex parser over the text the PDF extractor produced (real values!)   |
| lead-gen            | deterministic scoring on keywords found in the lead payload            |
| ai-support-agent    | canned policy answers + handoff detection                              |

It is deliberately simple and deterministic (same input -> same output), so the
demo doubles as a smoke test: no randomness, no network, no cost, no keys.

Swap it for a real model by pointing the `LLM` node (or `LLM_URL` in
docker-compose.yml) at any OpenAI-compatible endpoint.

Endpoints
---------
POST /chat  (also /v1/chat/completions) -> {"choices":[{"message":{"content": ...}}]}
GET  /health                           -> {"status":"ok"}

Usage: python scripts/mock_llm.py [--port 8770] [--host 0.0.0.0]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BREAD_PRICES = "sourdough $6, gluten-free bread $8"
HOURS = "Monday to Saturday, 8:00-19:00"
DELIVERY = "delivery within the city is $5, free on orders over $40"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _num(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _last_user_message(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            return str(msg.get("content") or "")
    return ""


def _system_prompt(messages: list[dict]) -> str:
    return "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")


# --------------------------------------------------------------------------- #
# 01 - invoice extraction
# --------------------------------------------------------------------------- #
def extract_invoice(text: str) -> dict:
    """Parse the text layer of an invoice PDF the same way a model would.

    Works on `samples/*.pdf` and on any invoice that keeps a similar layout.
    """
    # The workflow prefixes the prompt with "Invoice text:"; drop it so the
    # first line of the document is the vendor line.
    body = re.sub(r"^\s*Invoice text:\s*", "", text.replace("\r", ""), flags=re.IGNORECASE)
    lines = [ln.strip() for ln in body.split("\n")]

    def find(pattern: str) -> str | None:
        match = re.search(pattern, body, re.IGNORECASE)
        return match.group(1).strip() if match else None

    invoice_number = find(r"Invoice number:\s*([^\s]+)")
    date = find(r"Date:\s*(\d{4}-\d{2}-\d{2})")
    currency = find(r"Currency:\s*([A-Z]{3})")

    vendor = None
    for line in lines:
        if re.search(r"invoice number:", line, re.IGNORECASE):
            break
        candidate = re.sub(r"^\s*INVOICE\b", "", line, flags=re.IGNORECASE).strip()
        if candidate and candidate.upper() != "INVOICE":
            vendor = candidate
            break

    items: list[dict] = []
    in_items = False
    for line in lines:
        if re.search(r"Description", line, re.IGNORECASE) and re.search(r"Qty", line, re.IGNORECASE):
            in_items = True
            continue
        if re.match(r"^Subtotal", line, re.IGNORECASE):
            break
        if not in_items:
            continue
        row = re.match(
            r"^(?P<desc>.+?)\s+(?P<qty>\d+)\s+(?P<unit>[\d.,]+)\s+(?P<amount>[\d.,]+)$",
            line,
        )
        if row:
            qty = _num(row.group("qty"))
            unit = _num(row.group("unit"))
            amount = _num(row.group("amount"))
            if amount is None and qty is not None and unit is not None:
                amount = round(qty * unit, 2)
            items.append(
                {
                    "description": row.group("desc").strip(),
                    "quantity": qty,
                    "unit_price": unit,
                    "amount": amount,
                }
            )

    subtotal = _num(find(r"(?m)^\s*Subtotal[:\s]+([\d.,]+)"))
    tax = _num(find(r"(?m)^\s*Tax\s*\([^)]*\)[:\s]+([\d.,]+)")) or _num(find(r"(?m)^\s*Tax[:\s]+([\d.,]+)"))
    # anchored: plain `TOTAL` also matches inside the word "Subtotal"
    total = _num(find(r"(?m)^\s*TOTAL[:\s]+([\d.,]+)"))

    return {
        "invoice_number": invoice_number,
        "date": date,
        "vendor": vendor,
        "currency": currency,
        "line_items": items,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }


# --------------------------------------------------------------------------- #
# 02 - B2B lead scoring
# --------------------------------------------------------------------------- #
URGENCY_WORDS = ("asap", "urgent", "urgently", "immediately", "this week", "right away", "deadline")
BUDGET_WORDS = ("budget", "usd", "$", "price", "pricing", "quote", "per month", "retainer", "pay")
SCOPE_WORDS = ("automate", "automation", "integrate", "integration", "workflow", "api", "agent", "chatbot", "invoice")


def score_lead(payload: dict) -> dict:
    message = str(payload.get("message") or payload.get("notes") or "")
    lower = message.lower()
    score = 40
    reasons: list[str] = []

    if any(word in lower for word in URGENCY_WORDS):
        score += 20
        reasons.append("explicit urgency/time pressure in the message")
    if any(word in lower for word in BUDGET_WORDS):
        score += 15
        reasons.append("budget signals mentioned in the brief")
    if any(word in lower for word in SCOPE_WORDS):
        score += 15
        reasons.append("asks for a well-scoped automation the profile delivers")
    if payload.get("website"):
        score += 5
        reasons.append("public website provided, easy to verify company fit")
    if len(message) > 160:
        score += 5
        reasons.append("detailed brief with context rather than a one-liner")
    if not reasons:
        reasons.append("generic enquiry: no budget, urgency or scope signals yet")

    score = max(0, min(100, score))
    tier = "HOT" if score >= 75 else "WARM" if score >= 45 else "COLD"
    name = str(payload.get("name") or "there").split()[0]

    return {
        "score": score,
        "tier": tier,
        "reasons": reasons,
        "suggested_angle": (
            f"Reply with a fixed-price first slice for the {lower.split()[0] if lower else 'stated'} problem "
            "and ask for the two data points you need to quote."
        ),
        "followup_email": (
            f"Hi {name}, thanks for reaching out — this looks like a good fit for what I build.\n"
            "I'd start with one workflow end to end: I send you a short plan with a fixed price and a "
            "delivery date, you approve it in writing, and I ship it with a demo video and documentation.\n"
            "Two things help me quote precisely: which tool the data lives in today, and what the "
            "current manual process looks like. Happy to keep everything over email or chat — no calls needed.\n"
            "Best, Francisco"
        ),
    }


# --------------------------------------------------------------------------- #
# 03 - support agent
# --------------------------------------------------------------------------- #
def support_reply(messages: list[dict]) -> dict:
    question = _last_user_message(messages).lower()

    def reply(text: str, intent: str, handoff: bool = False, reason: str = "", sentiment: str = "neutral") -> dict:
        return {
            "reply": text,
            "intent": intent,
            "sentiment": sentiment,
            "handoff": handoff,
            "handoff_reason": reason,
        }

    if any(word in question for word in ("refund", "money back", "charge", "wrong charge", "complaint", "complain")):
        return reply(
            "I'm sorry about that — I've flagged this for the team, and a human will follow up with you "
            "directly about the refund.",
            "refund_or_complaint",
            handoff=True,
            reason="Refunds and complaints are handled by a human",
            sentiment="negative",
        )
    if any(word in question for word in ("human", "person", "agent", "manager", "call me", "phone", "call back")):
        return reply(
            "Of course — I've passed your request to the team and someone will follow up with you directly.",
            "human_requested",
            handoff=True,
            reason="Customer asked for a human / callback",
        )
    if any(word in question for word in ("angry", "terrible", "awful", "useless", "frustrat", "unacceptable")):
        return reply(
            "I'm really sorry — I don't want to make this worse, so I've asked a team member to take over from here.",
            "frustration",
            handoff=True,
            reason="Customer is frustrated",
            sentiment="negative",
        )
    if any(word in question for word in ("hour", "open", "close", "closed")):
        return reply(f"We're open {HOURS}. Anything you'd like me to set aside for you?", "opening_hours")
    if any(word in question for word in ("price", "cost", "how much", "menu", "bread")):
        return reply(
            f"Today we have {BREAD_PRICES}. Anything with a custom design needs 48h notice. Want me to note an order?",
            "pricing",
        )
    if any(word in question for word in ("deliver", "shipping", "bring")):
        return reply(f"Sure — {DELIVERY}. Which neighbourhood are you in?", "delivery")
    if any(word in question for word in ("cake", "custom", "birthday", "wedding")):
        return reply(
            "Custom cakes are definitely possible — they need 48h notice and payment up front. "
            "Tell me the date, size and message and I'll pass it to the kitchen.",
            "custom_cake",
        )
    if any(word in question for word in ("order", "buy", "purchase", "reserve", "book")):
        return reply(
            "Happy to help you order — tell me what you'd like and when you want to pick it up, and I'll confirm availability.",
            "order",
        )
    if any(word in question for word in ("thank", "great", "perfect", "lovely")):
        return reply("Glad to help! Anything else I can check for you?", "thanks", sentiment="positive")
    return reply(
        "I'm not sure about that one, so I've passed it to the team — a human will get back to you shortly.",
        "out_of_scope",
        handoff=True,
        reason="Question outside the documented answers",
    )


# --------------------------------------------------------------------------- #
# router: system prompt decides which task is being asked for
# --------------------------------------------------------------------------- #
def generate(messages: list[dict]) -> dict:
    system = _system_prompt(messages).lower()
    user_text = _last_user_message(messages)

    if os.environ.get("MOCK_LLM_DEBUG"):
        print(f"[mock-llm][debug] user text:\n{user_text[:2000]}\n[mock-llm][debug] ---", flush=True)

    if "invoice data extraction engine" in system:
        return extract_invoice(user_text)
    if "b2b lead qualification analyst" in system:
        raw = re.sub(r"^Lead data \(JSON\):\s*", "", user_text, flags=re.IGNORECASE).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"message": raw}
        return score_lead(payload)
    if "support assistant" in system:
        return support_reply(messages)
    return {"reply": "mock-llm: no rule matched this prompt", "intent": "fallback"}


# --------------------------------------------------------------------------- #
# HTTP layer (stdlib only)
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "mock-llm/1.0"

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/health", "/healthz"):
            self._send(200, {"status": "ok", "service": "mock-llm"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") not in ("/chat", "/v1/chat/completions"):
            self._send(404, {"error": "not found", "hint": "POST /chat"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            request = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "invalid JSON body"})
            return

        messages = request.get("messages") or []
        content = json.dumps(generate(messages), ensure_ascii=False)
        self._send(
            200,
            {
                "id": f"chatcmpl-mock-{int(time.time() * 1000)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "mock-llm",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                ],
                "usage": {
                    "prompt_tokens": sum(len(str(m.get("content") or "").split()) for m in messages),
                    "completion_tokens": len(content.split()),
                    "total_tokens": 0,
                },
            },
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        print(f"[mock-llm] {self.address_string()} {format % args}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenAI-compatible deterministic mock LLM")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[mock-llm] listening on http://{args.host}:{args.port} (POST /chat, GET /health)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
