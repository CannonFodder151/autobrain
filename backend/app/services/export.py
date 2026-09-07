"""PDF and CSV export helpers for service history, build sheets, logbooks
and fuel, plus user-profile JSON export/import."""

import csv
import io
import zipfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _photo_names(photo_keys) -> list[str]:
    """Map MinIO keys to the short filenames used inside an export ZIP."""
    if not photo_keys:
        return []
    keys = photo_keys if isinstance(photo_keys, list) else []
    names = []
    for k in keys:
        fname = k.rsplit("/", 1)[-1]
        names.append(f"images/{fname}")
    return names


def _photo_csv(photo_keys) -> str:
    return "; ".join(_photo_names(photo_keys))


def export_zip(csv_bytes: bytes, images: dict[str, bytes]) -> bytes:
    """Bundle a CSV (with image references) and the referenced image files."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("export.csv", csv_bytes)
        for name, data in images.items():
            zf.writestr(f"images/{name}", data)
    return buf.getvalue()


def _items_text(r) -> str:
    if not getattr(r, "items", None):
        return ""
    parts = []
    for it in r.items:
        label = it.name
        if it.part_no:
            label += f" [{it.part_no}]"
        if it.quantity and it.quantity != 1:
            label += f" x{it.quantity}"
        parts.append(label)
    return "; ".join(parts)


def export_service_history_csv(records: list, label: str) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["AutoBrain Service History", label])
    writer.writerow([])
    writer.writerow(["Date", "Odometer (km)", "Type", "Workshop", "Cost", "Currency", "Items", "Notes", "Images"])
    for r in records:
        writer.writerow(
            [r.service_date, r.odometer_km, r.service_type, r.workshop or "",
             r.cost, r.currency, _items_text(r), (r.notes or ""), _photo_csv(r.photo_keys)]
        )
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


WHITE_STYLE = None


def _get_white_style():
    global WHITE_STYLE
    if WHITE_STYLE is None:
        base = getSampleStyleSheet()["BodyText"]
        WHITE_STYLE = base.clone("WhiteHeader")
        WHITE_STYLE.textColor = colors.white
        WHITE_STYLE.fontName = "Helvetica-Bold"
    return WHITE_STYLE


def export_service_history_pdf(records: list, label: str, rego: str = "") -> bytes:
    title = f"Service History — {label} — {rego}" if rego else f"Service History — {label}"
    return _pdf_table(
        title=title,
        header=["Date", "Odometer (km)", "Type", "Workshop", "Cost", "Items"],
        rows=[
            [str(r.service_date), str(r.odometer_km), r.service_type,
             r.workshop or "", f"{r.cost:,.2f} {r.currency}", _items_text(r)]
            for r in records
        ],
    )


def export_build_sheet_csv(mods: list, label: str) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["AutoBrain Build Sheet", label])
    writer.writerow([])
    writer.writerow(["Date", "Name", "Category", "Brand", "Cost", "Notes", "Images"])
    for m in mods:
        writer.writerow([m.install_date or "", m.name, m.category, m.brand or "",
                         m.cost, m.notes or "", _photo_csv(m.photo_keys)])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def export_build_sheet_pdf(mods: list, label: str, rego: str = "") -> bytes:
    title = f"Build Sheet — {label} — {rego}" if rego else f"Build Sheet — {label}"
    return _pdf_table(
        title=title,
        header=["Date", "Name", "Category", "Brand", "Cost"],
        rows=[
            [str(m.install_date or ""), m.name, m.category, m.brand or "", f"{m.cost:,.2f}"]
            for m in mods
        ],
    )


def _pdf_table(title: str, header: list[str], rows: list[list]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]

    def cell(text: str, *, bold: bool = False) -> Paragraph:
        safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        style = _get_white_style() if bold else styles["BodyText"]
        return Paragraph(safe, style)

    data = [[cell(h, bold=True) for h in header]] + [[cell(c) for c in row] for row in rows]
    table = Table(data, repeatRows=1, colWidths=None)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()


def export_logbook_csv(entries: list, fy: int) -> bytes:
    """ATO logbook CSV for an Australian financial year (ends 30 June)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([f"AutoBrain Logbook — FY{fy-1}/{str(fy)[2:]}"])
    writer.writerow(["Trip", "Start time", "End time", "Start odo", "End odo",
                     "Distance (km)", "Purpose", "Reason", "Start location", "End location"])
    for i, e in enumerate(entries, 1):
        writer.writerow([
            i,
            e.started_at.strftime("%Y-%m-%d %H:%M") if e.started_at else "",
            e.ended_at.strftime("%Y-%m-%d %H:%M") if e.ended_at else "",
            e.start_odometer_km or "", e.end_odometer_km or "",
            e.distance_km or "", e.purpose, e.reason or "",
            e.start_location or "", e.end_location or "",
        ])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def export_fuel_csv(logs: list, fy: int) -> bytes:
    """Fuel CSV for a financial year (fuel tax / reimbursement records)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([f"AutoBrain Fuel — FY{fy-1}/{str(fy)[2:]}"])
    writer.writerow(["Date", "Odometer (km)", "Litres", "Price/L", "Total cost",
                     "Full tank", "Distance (km)", "L/100km", "Notes", "Image"])
    for l in logs:
        writer.writerow([
            l.fill_date, l.odometer_km, l.litres, l.price_per_litre, l.total_cost,
            "yes" if l.is_full_tank else "no", l.distance_km or "",
            l.l_per_100km or "", l.notes or "",
            _photo_csv([l.receipt.file_key]) if l.receipt else "",
        ])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def export_user_profile(user: dict, vehicles: list) -> dict:
    """Serialize a full user profile (user + all vehicles + their data) as JSON."""
    return {"app": "autobrain", "version": 1, "user": user, "vehicles": vehicles}


def parse_user_profile(data: dict) -> tuple[dict, list]:
    """Split an exported profile back into (user dict, vehicles list)."""
    if not isinstance(data, dict) or data.get("app") != "autobrain":
        raise ValueError("Not an AutoBrain export file")
    return data.get("user", {}), data.get("vehicles", []) or []
