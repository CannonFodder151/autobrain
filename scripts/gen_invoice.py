import base64
import sys
from io import BytesIO

from reportlab.pdfgen import canvas

lines = [
    "SuperCheap Auto",
    "123 Main Street, Sydney",
    "",
    "INVOICE 2026-08-01",
    "",
    "Oil 10W-40    35.00",
    "Oil Filter    25.00",
    "Labour 1.0h   90.00",
    "",
    "Subtotal  150.00",
    "GST       15.00",
    "TOTAL    165.00",
]
b = BytesIO()
c = canvas.Canvas(b)
c.setFont("Helvetica", 12)
y = 760
for t in lines:
    c.drawString(72, y, t)
    y -= 24
c.save()
sys.stdout.write(base64.b64encode(b.getvalue()).decode())
