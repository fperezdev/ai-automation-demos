#!/usr/bin/env python3
"""Render WhatsApp-style captures of the 3 test conversations.

Reads samples/whatsapp_conversations.json (produced by scripts/run_whatsapp_tests.py)
and renders one PNG per conversation, styled like a WhatsApp chat, plus a combined
overview sheet. The retrieved knowledge-base sources are shown as a small caption
under each agent reply, so the RAG step is visible in the evidence.

Requires: playwright (chromium).
Output: theaccelerator/asistente-whatsapp/capturas/
"""
import json
import os

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples", "whatsapp_conversations.json")
OUT = os.path.join(ROOT, "..", "theaccelerator", "asistente-whatsapp", "capturas")

CLINIC = "Clínica Dental Sonrisa Ñuñoa"
TIMES = {
    "c1-precios-agenda": ["10:14", "10:15", "10:16"],
    "c2-ubicacion-pagos": ["16:02", "16:02", "16:03"],
    "c3-urgencia-handoff": ["23:41"],
}

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background: #d1d7db; }
.phone { width: 420px; background: #efeae2; }
.topbar { background: #008069; color: #fff; display: flex; align-items: center; gap: 10px; padding: 12px 14px; }
.avatar { width: 40px; height: 40px; border-radius: 50%; background: #25d366; display: flex; align-items: center; justify-content: center; font-size: 20px; }
.who { line-height: 1.15; }
.who .name { font-size: 16px; font-weight: 600; }
.who .status { font-size: 12px; opacity: .85; }
.chat { padding: 16px 12px 20px; display: flex; flex-direction: column; gap: 8px; min-height: 260px;
        background-image: radial-gradient(rgba(0,0,0,.035) 1px, transparent 1px); background-size: 18px 18px; }
.badge { align-self: center; background: #fff8d6; color: #6b5c1e; font-size: 11px; padding: 4px 10px;
         border-radius: 7px; box-shadow: 0 1px 1px rgba(0,0,0,.1); }
.row { display: flex; }
.row.out { justify-content: flex-end; }
.bubble { max-width: 82%; border-radius: 10px; padding: 7px 10px 6px; font-size: 14.5px; line-height: 1.4;
          color: #111b21; box-shadow: 0 1px 1px rgba(0,0,0,.12); position: relative; }
.bubble.in { background: #fff; border-top-left-radius: 2px; }
.bubble.out { background: #d9fdd3; border-top-right-radius: 2px; }
.meta { display: block; text-align: right; font-size: 11px; color: #667781; margin-top: 2px; }
.tick { color: #53bdeb; }
.src { margin-top: 5px; font-size: 10.5px; color: #5b7a5b; border-top: 1px dashed #cde3cd; padding-top: 4px; }
.foot { background: #f0f2f5; color: #667781; font-size: 10.5px; padding: 8px 14px; }
.handoff { background: #fff3cd; color: #8a6d3b; font-size: 11px; padding: 5px 10px; border-radius: 7px; align-self: center; }
.sheet { display: flex; gap: 22px; padding: 28px; background: #e9edef; }
"""


def bubble(role, text, time, sources=None, handoff=False):
    cls = "out" if role == "user" else "in"
    ticks = '<span class="tick">✓✓</span>' if role == "user" else ""
    src = ""
    if role == "assistant" and sources:
        src = '<div class="src">🔎 RAG · base de conocimiento: ' + " · ".join(sources) + "</div>"
    return (
        f'<div class="row {cls}"><div class="bubble {cls}">{text}'
        f'<span class="meta">{time} {ticks}</span>{src}</div></div>'
    )


def phone(convo, times):
    rows = ['<div class="badge">Demo · n8n + WhatsApp Cloud API + RAG</div>']
    for i, ex in enumerate(convo["exchanges"]):
        t = times[i] if i < len(times) else ""
        rows.append(bubble("user", ex["user"], t))
        rows.append(bubble("assistant", ex["assistant"], t, ex.get("sources"), ex.get("handoff")))
        if ex.get("handoff"):
            rows.append('<div class="handoff">⚠️ Handoff → derivado a una persona del equipo: '
                        + (ex.get("handoff_reason") or "requiere atención humana") + "</div>")
    return (
        '<div class="phone">'
        '<div class="topbar"><div class="avatar">🦷</div>'
        f'<div class="who"><div class="name">{CLINIC}</div>'
        '<div class="status">en línea</div></div></div>'
        f'<div class="chat">{"".join(rows)}</div>'
        f'<div class="foot">{convo["title"]}</div></div>'
    )


def build_html(convos, combined):
    body = "".join(phone(c, TIMES.get(c["id"], [])) for c in convos)
    wrap_cls = "sheet" if combined else "sheet"
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body><div class='{wrap_cls}'>{body}</div></body></html>"


def main():
    with open(SAMPLES, encoding="utf-8") as f:
        convos = json.load(f)
    os.makedirs(OUT, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for c in convos:
            page = browser.new_page(viewport={"width": 420, "height": 700}, device_scale_factor=2)
            page.set_content(build_html([c], combined=False))
            path = os.path.join(OUT, f"{c['id']}.png")
            page.locator(".phone").screenshot(path=path)
            page.close()
            print("wrote", path)
        # combined sheet
        page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=2)
        page.set_content(build_html(convos, combined=True))
        path = os.path.join(OUT, "todas-las-conversaciones.png")
        page.locator(".sheet").screenshot(path=path)
        page.close()
        print("wrote", path)
        browser.close()


if __name__ == "__main__":
    main()
