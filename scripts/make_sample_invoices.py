#!/usr/bin/env python3
"""Generate sample invoice PDFs for the doc-automation demo.

Usage: python scripts/make_sample_invoices.py
Output: samples/invoice_*.pdf
"""
import os
import sys

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")

INVOICES = [
    {
        "file": "invoice_001.pdf",
        "vendor": "Acme Supplies Inc.",
        "address": "1200 Market Street, San Francisco, CA",
        "number": "INV-2026-0142",
        "date": "2026-09-14",
        "currency": "USD",
        "items": [
            ("Widget A - industrial grade", 12, 25.00),
            ("Priority support plan (1 month)", 1, 199.00),
        ],
        "tax_rate": 0.08,
        "total_override": None,
    },
    {
        "file": "invoice_002.pdf",
        "vendor": "Servicios Andinos SpA",
        "address": "Av. Providencia 1234, Santiago, Chile",
        "number": "F-2026-0871",
        "date": "2026-09-20",
        "currency": "USD",
        "items": [
            ("Desarrollo backend (horas)", 10, 80.00),
            ("Hosting mensual", 1, 120.00),
        ],
        "tax_rate": 0.19,
        "total_override": None,
    },
    {
        "file": "invoice_003.pdf",
        "vendor": "Brightline LLC",
        "address": "44 Main Ave, Austin, TX",
        "number": "INV-2026-0203",
        "date": "2026-09-25",
        "currency": "USD",
        "items": [
            ("Process consulting (hours)", 6, 150.00),
            ("Travel reimbursement", 1, 210.00),
        ],
        "tax_rate": 0.05,
        "total_override": 1200.00,  # deliberate mismatch: correct total is 1165.50
    },
]


def build_invoice(spec):
    path = os.path.join(OUT_DIR, spec["file"])
    subtotal = round(sum(qty * price for _, qty, price in spec["items"]), 2)
    tax = round(subtotal * spec["tax_rate"], 2)
    total = spec["total_override"] if spec["total_override"] is not None else round(subtotal + tax, 2)

    c = canvas.Canvas(path, pagesize=LETTER)
    width, height = LETTER
    y = height - 3 * cm

    c.setFont("Helvetica-Bold", 20)
    c.drawString(2.5 * cm, y, "INVOICE")
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(width - 2.5 * cm, y, spec["vendor"])
    y -= 0.6 * cm
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 2.5 * cm, y, spec["address"])
    y -= 1.2 * cm

    c.setFont("Helvetica", 10)
    c.drawString(2.5 * cm, y, f"Invoice number: {spec['number']}")
    c.drawString(2.5 * cm + 9 * cm, y, f"Date: {spec['date']}")
    c.drawString(2.5 * cm + 14 * cm, y, f"Currency: {spec['currency']}")
    y -= 1.0 * cm

    c.setFont("Helvetica-Bold", 10)
    c.drawString(2.5 * cm, y, "Description")
    c.drawString(12.0 * cm, y, "Qty")
    c.drawString(14.0 * cm, y, "Unit price")
    c.drawRightString(width - 2.5 * cm, y, "Amount")
    y -= 0.45 * cm
    c.line(2.5 * cm, y, width - 2.5 * cm, y)
    y -= 0.55 * cm

    c.setFont("Helvetica", 10)
    for desc, qty, price in spec["items"]:
        c.drawString(2.5 * cm, y, desc)
        c.drawString(12.0 * cm, y, str(qty))
        c.drawString(14.0 * cm, y, f"{price:.2f}")
        c.drawRightString(width - 2.5 * cm, y, f"{qty * price:.2f}")
        y -= 0.55 * cm

    y -= 0.3 * cm
    c.line(12.0 * cm, y + 0.3 * cm, width - 2.5 * cm, y + 0.3 * cm)

    for label, value in (
        ("Subtotal", subtotal),
        (f"Tax ({spec['tax_rate'] * 100:.0f}%)", tax),
    ):
        c.drawString(12.0 * cm, y, label)
        c.drawRightString(width - 2.5 * cm, y, f"{value:.2f}")
        y -= 0.55 * cm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(12.0 * cm, y, "TOTAL")
    c.drawRightString(width - 2.5 * cm, y, f"{total:.2f} {spec['currency']}")

    c.setFont("Helvetica-Oblique", 8)
    c.drawString(2.5 * cm, 2 * cm, "Payment due within 30 days. Thank you for your business.")

    c.showPage()
    c.save()
    return path, subtotal, tax, total


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for spec in INVOICES:
        path, subtotal, tax, total = build_invoice(spec)
        print(f"{path}  subtotal={subtotal:.2f} tax={tax:.2f} total={total:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
