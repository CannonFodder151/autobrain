"""PDF and CSV export helpers for service history and build sheets."""

import csv
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def export_service_history_csv(records: list, label: str) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["AutoBrain Service History", label])
    writer.writerow([])
    writer.writerow(["Date", "Odometer (km)", "Type", "Workshop", "Cost", "Currency", "Notes"])
    for r in records:
        writer.writerow([r.service_date, r.odometer_km, r.service_type, r.workshop or "", r.cost, r.currency, (r.notes or "")])
    return buf.getvalue().encode("utf-8")


def export_service_history_pdf(records: list, label: str) -> bytes:
    return _pdf_table(
        title=f"Service History — {label}",
        header=["Date", "Odometer (km)", "Type", "Workshop", "Cost"],
        rows=[
            [str(r.service_date), str(r.odometer_km), r.service_type, r.workshop or "", f"{r.cost:,.2f} {r.currency}"]
            for r in records
        ],
    )


def export_build_sheet_csv(mods: list, label: str) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["AutoBrain Build Sheet", label])
    writer.writerow([])
    writer.writerow(["Date", "Name", "Category", "Brand", "Cost", "Notes"])
    for m in mods:
        writer.writerow([m.install_date or "", m.name, m.category, m.brand or "", m.cost, m.notes or ""])
    return buf.getvalue().encode("utf-8")


def export_build_sheet_pdf(mods: list, label: str) -> bytes:
    return _pdf_table(
        title=f"Build Sheet — {label}",
        header=["Date", "Name", "Category", "Brand", "Cost"],
        rows=[
            [str(m.install_date or ""), m.name, m.category, m.brand or "", f"{m.cost:,.2f}"]
            for m in mods
        ],
    )


def _pdf_table(title: str, header: list[str], rows: list[list]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    data = [header] + rows
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()
