#!/usr/bin/env python3
"""Run the 3 simulated WhatsApp conversations against the Demo 04 workflow.

Each conversation is sent turn by turn to the n8n webhook
(POST /webhook/whatsapp-dental/hook). The webhook is stateless, so every turn
re-sends the accumulated history, exactly like a production adapter would replay
a session from its store.

Output: samples/whatsapp_conversations.json
"""
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.environ.get("WA_HOOK", "http://127.0.0.1:5678/webhook/whatsapp-dental/hook")
OUT = os.path.join(ROOT, "samples", "whatsapp_conversations.json")

CONVERSATIONS = [
    {
        "id": "c1-precios-agenda",
        "title": "Consulta de precios + agendar hora",
        "sender": "56911110001",
        "turns": [
            "Hola, cuánto cuesta una limpieza dental?",
            "y el blanqueamiento? cuánto sale",
            "perfecto, quiero agendar para el sábado en la mañana",
        ],
    },
    {
        "id": "c2-ubicacion-pagos",
        "title": "Cómo llegar + previsión y convenios",
        "sender": "56911110002",
        "turns": [
            "hola, dónde quedan? voy en metro",
            "atienden isapre?",
            "y por la empresa de mi trabajo hay algún descuento?",
        ],
    },
    {
        "id": "c3-urgencia-handoff",
        "title": "Urgencia fuera de horario (deriva a humano)",
        "sender": "56911110003",
        "turns": [
            "hola, es de noche y me duele muchísimo una muela, pueden atenderme ahora?",
        ],
    },
]


def call(messages, sender):
    payload = json.dumps({"from": sender, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(HOOK, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    results = []
    for convo in CONVERSATIONS:
        history = []
        exch = []
        for user_text in convo["turns"]:
            history.append({"role": "user", "content": user_text})
            out = call(history, convo["sender"])
            reply = out.get("reply", "")
            history.append({"role": "assistant", "content": reply})
            exch.append({
                "user": user_text,
                "assistant": reply,
                "sources": out.get("sources", []),
                "handoff": out.get("handoff", False),
                "handoff_reason": out.get("handoff_reason", ""),
                "sentiment": out.get("sentiment", ""),
            })
            print(f"[{convo['id']}] {user_text[:40]:42s} -> {reply[:70]}")
        results.append({**convo, "exchanges": exch})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("\nwrote", OUT)


if __name__ == "__main__":
    main()
