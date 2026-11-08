# pdf
import re
from datetime import date, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from pydantic import BaseModel, ConfigDict, Field
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.state import DayPlan, StayOption, TransportOption, TripRequest

PINK = colors.HexColor("#c2185b")
SOFT = colors.HexColor("#fde7ef")
INK = colors.HexColor("#2b1621")
MUTED = colors.HexColor("#7a5a68")
LINE = colors.HexColor("#f3c6d6")


class PlanDoc(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    request: TripRequest
    summary: str = Field(default="", max_length=2000)
    outbound: TransportOption | None = None
    return_: TransportOption | None = Field(default=None, alias="return")
    stay: StayOption | None = None
    days: list[DayPlan] = Field(default_factory=list, max_length=15)
    breakdown: dict[str, int] = Field(default_factory=dict)
    total_cost: int = 0
    over_budget_by: int = 0
    notes: list[str] = Field(default_factory=list, max_length=50)


def rs(n: int) -> str:
    return f"Rs {n:,}"


def day_label(d: date) -> str:
    return d.strftime("%a %d %b")


def when(t: datetime) -> str:
    return t.strftime("%a %d %b, %H:%M")


def styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=10, leading=14, textColor=INK)
    return {
        "brand": ParagraphStyle("brand", parent=base, fontName="Helvetica-Bold", fontSize=11, textColor=PINK),
        "title": ParagraphStyle("title", parent=base, fontName="Helvetica-Bold", fontSize=22, leading=27),
        "sub": ParagraphStyle("sub", parent=base, textColor=MUTED),
        "h2": ParagraphStyle(
            "h2",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            spaceBefore=12,
            spaceAfter=6,
            textColor=PINK,
        ),
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8.5, leading=11, textColor=MUTED),
        "bold": ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold"),
    }


def table(rows: list[list], widths: list[float], header: bool = False) -> Table:
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), SOFT), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def build_pdf(doc: PlanDoc) -> bytes:
    st, req, out = styles(), doc.request, BytesIO()
    width = A4[0] - 36 * mm
    story = [
        Paragraph("SAFARNAMA", st["brand"]),
        Paragraph(escape(f"{req.origin} to {req.destination}"), st["title"]),
        Paragraph(
            f"{day_label(req.start_date)} to {day_label(req.end_date)}, {req.days} day{'s' if req.days > 1 else ''}, {req.travellers} traveller{'s' if req.travellers > 1 else ''}",
            st["sub"],
        ),
        Spacer(1, 8),
    ]
    if doc.summary:
        story.append(Paragraph(escape(doc.summary), st["body"]))
    status = (
        f"{rs(doc.over_budget_by)} over budget" if doc.over_budget_by else f"{rs(req.budget_inr - doc.total_cost)} left"
    )
    story += [Paragraph("Cost", st["h2"])]
    cost_rows = [
        ["Transport", "Stay", "Food", "Entry fees", "Total"],
        [rs(doc.breakdown.get(k, 0)) for k in ("transport", "stay", "food", "activities")] + [rs(doc.total_cost)],
    ]
    story += [
        table(cost_rows, [width / 5] * 5, header=True),
        Spacer(1, 4),
        Paragraph(f"Budget {rs(req.budget_inr)}, {status}", st["sub"]),
    ]
    travel = []
    for label, t in (("Getting there", doc.outbound), ("Coming back", doc.return_)):
        if t:
            travel.append(
                [
                    Paragraph(label, st["bold"]),
                    Paragraph(
                        escape(f"{t.mode.title()}, {t.provider}")
                        + f"<br/>Leaves {when(t.depart_at)}, arrives {when(t.arrive_at)}",
                        st["body"],
                    ),
                    rs(t.price_inr),
                ]
            )
    if doc.stay:
        s = doc.stay
        desk = "24 hour desk" if s.late_checkin else f"desk open until {s.checkin_until:%H:%M}"
        travel.append(
            [
                Paragraph("Staying at", st["bold"]),
                Paragraph(escape(f"{s.name}{', ' + s.area if s.area else ''}") + f"<br/>{desk}", st["body"]),
                f"{rs(s.price_per_night_inr)} a night",
            ]
        )
    if travel:
        story += [Paragraph("Travel and stay", st["h2"]), table(travel, [32 * mm, width - 62 * mm, 30 * mm])]
    story.append(Paragraph("Day by day", st["h2"]))
    for i, d in enumerate(doc.days, 1):
        rows = [
            [
                it.start if it.kind == "travel" or it.start == it.end else f"{it.start} to {it.end}",
                Paragraph(escape(it.title), st["bold"] if it.kind == "place" else st["body"]),
                rs(it.cost_inr) if it.kind == "place" and it.cost_inr else "",
            ]
            for it in d.items
        ]
        block = [Paragraph(f"Day {i}, {day_label(d.date)}", st["bold"]), Spacer(1, 2)]
        block.append(table(rows, [30 * mm, width - 55 * mm, 25 * mm]) if rows else Paragraph("Free day", st["sub"]))
        story.append(KeepTogether(block + [Spacer(1, 8)]))
    if doc.notes:
        story.append(Paragraph("Good to know", st["h2"]))
        story += [Paragraph(escape(f"- {n[:1].upper()}{n[1:]}"), st["body"]) for n in doc.notes]
    story += [
        Spacer(1, 14),
        Paragraph(
            "Planned by Safarnama's agents. Prices and timings come from sample data, check them before you book.",
            st["small"],
        ),
    ]
    SimpleDocTemplate(
        out,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Safarnama {req.origin} to {req.destination}",
        author="Safarnama",
    ).build(story)
    return out.getvalue()


def filename(doc: PlanDoc) -> str:
    r = doc.request
    name = f"safarnama-{r.origin}-{r.destination}-{r.start_date}".lower()
    return re.sub(r"[^a-z0-9-]+", "-", name).strip("-") + ".pdf"
