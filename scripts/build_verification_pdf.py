"""Render the officer fact-check questionnaire to PDF.

Usage:
    python scripts/build_verification_pdf.py questionnaire.json out.pdf

The JSON shape is the one produced by the facts-audit workflow:
    {title, intro, sections: [{heading, why, items: [{id, question,
     currently_shown, answer_type, choices?, table_columns?, table_rows?}]}]}

Answer areas are drawn per ``answer_type`` so the PDF can be printed and
filled by hand, or annotated in any PDF viewer.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BLACK = colors.HexColor("#000000")
GOLD = colors.HexColor("#FFCD00")
INK = colors.HexColor("#111111")
GREY = colors.HexColor("#6B6B6B")
LINE = colors.HexColor("#BFBFBF")
PALE = colors.HexColor("#F5F3EE")

PAGE_W, PAGE_H = letter
MARGIN = 0.85 * inch
CONTENT_W = PAGE_W - 2 * MARGIN


def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


STYLES = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=26, leading=30, textColor=BLACK, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=12.5, leading=17, textColor=GREY),
    "intro": ParagraphStyle("intro", fontName="Helvetica", fontSize=10.5, leading=15, textColor=INK),
    "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=BLACK, spaceBefore=4, spaceAfter=2),
    "why": ParagraphStyle("why", fontName="Helvetica-Oblique", fontSize=9.5, leading=13, textColor=GREY, spaceAfter=8),
    "qid": ParagraphStyle("qid", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=BLACK),
    "q": ParagraphStyle("q", fontName="Helvetica-Bold", fontSize=10.5, leading=14.5, textColor=INK),
    "shown_label": ParagraphStyle("shown_label", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=GREY),
    "shown": ParagraphStyle("shown", fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK),
    "choice": ParagraphStyle("choice", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, leading=11, textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=BLACK),
    "foot": ParagraphStyle("foot", fontName="Helvetica", fontSize=8, leading=10, textColor=GREY),
}


class Rule(Flowable):
    """A horizontal rule; thick+gold for the title, hairline elsewhere."""

    def __init__(self, width=CONTENT_W, thickness=0.5, color=LINE, space=4):
        super().__init__()
        self.width, self.thickness, self.color, self.space = width, thickness, color, space

    def wrap(self, *_):
        return self.width, self.thickness + self.space * 2

    def draw(self):
        self.canv.setStrokeColor(self.color)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, self.space, self.width, self.space)


class AnswerLines(Flowable):
    """Ruled write-in lines."""

    def __init__(self, n=1, width=CONTENT_W, gap=17):
        super().__init__()
        self.n, self.width, self.gap = n, width, gap

    def wrap(self, *_):
        return self.width, self.n * self.gap + 4

    def draw(self):
        self.canv.setStrokeColor(LINE)
        self.canv.setLineWidth(0.5)
        for i in range(self.n):
            y = 4 + i * self.gap
            self.canv.line(0, y, self.width, y)


class Checkbox(Flowable):
    def __init__(self, size=9):
        super().__init__()
        self.size = size

    def wrap(self, *_):
        return self.size + 6, self.size

    def draw(self):
        self.canv.setStrokeColor(INK)
        self.canv.setLineWidth(0.7)
        self.canv.rect(0, -1.5, self.size, self.size, stroke=1, fill=0)


def choice_row(label: str, with_line=False):
    """A checkbox beside a label, optionally followed by a write-in line."""
    cells = [[Checkbox(), Paragraph(esc(label), STYLES["choice"])]]
    widths = [16, CONTENT_W - 16]
    if with_line:
        cells = [[Checkbox(), Paragraph(esc(label), STYLES["choice"]), AnswerLines(1, width=CONTENT_W - 16 - 140)]]
        widths = [16, 124, CONTENT_W - 16 - 124]
    t = Table(cells, colWidths=widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t


def shown_block(text: str):
    if not (text or "").strip():
        return []
    inner = Table(
        [[Paragraph("CURRENTLY SHOWN", STYLES["shown_label"])], [Paragraph(esc(text), STYLES["shown"])]],
        colWidths=[CONTENT_W - 12],
    )
    inner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (0, 0), 5),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 1), (0, 1), 1),
        ("BOTTOMPADDING", (0, 1), (0, 1), 6),
        ("LINEBEFORE", (0, 0), (0, -1), 2, GOLD),
    ]))
    return [Spacer(1, 3), inner, Spacer(1, 4)]


def table_question(item):
    cols = list(item.get("table_columns") or [])
    rows = list(item.get("table_rows") or [])
    if not cols:
        return [AnswerLines(3)]
    # Give the officer somewhere to mark and correct each row, unless the
    # editor already built those columns in.
    lowered = [c.lower() for c in cols]
    has_yn = any("y/n" in c or c.startswith("correct?") or "still on" in c for c in lowered)
    has_fix = any(c.startswith("correction") for c in lowered)
    if not has_yn:
        cols = cols + ["Correct?"]
        rows = [list(r) + [""] for r in rows]
    if not has_fix:
        cols = cols + ["Correction"]
        rows = [list(r) + [""] for r in rows]
    rows = [list(r)[:len(cols)] + [""] * max(0, len(cols) - len(r)) for r in rows]
    # A few blank rows for additions.
    rows = rows + [[""] * len(cols) for _ in range(3)]

    n = len(cols)
    def fixed_w(c):
        cl = c.lower()
        if "y/n" in cl or cl.startswith("correct?") or "still on" in cl:
            return 50
        if cl.startswith("correction"):
            return 96
        return None
    flex_cols = [c for c in cols if fixed_w(c) is None]
    flex_w = (CONTENT_W - sum(fixed_w(c) or 0 for c in cols)) / max(1, len(flex_cols))
    widths = [fixed_w(c) or flex_w for c in cols]

    data = [[Paragraph(esc(c), STYLES["cellh"]) for c in cols]]
    for r in rows:
        cells = []
        for c, v in zip(cols, r):
            if fixed_w(c) == 50:
                yn = Table([[Checkbox(8), Paragraph("Y", STYLES["cell"]), Checkbox(8), Paragraph("N", STYLES["cell"])]],
                           colWidths=[11, 9, 11, 9])
                yn.setStyle(TableStyle([
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                cells.append(yn)
            else:
                cells.append(Paragraph(esc(str(v)), STYLES["cell"]))
        data.append(cells)

    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, BLACK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, 0), (-1, 0), PALE),
    ]))
    return [Spacer(1, 4), t]


def answer_area(item):
    kind = item.get("answer_type", "short")
    if kind == "yes-no":
        return [Spacer(1, 3), choice_row("Yes"), choice_row("No. Note or correction:", with_line=True)]
    if kind == "choice":
        out = [Spacer(1, 3)]
        choices = list(item.get("choices") or [])
        other = [c for c in choices if c.strip().lower().startswith("other")]
        for c in choices:
            if c in other:
                continue
            out.append(choice_row(c))
        out.append(choice_row("Other:", with_line=True))
        return out
    if kind == "long":
        return [Spacer(1, 3), AnswerLines(3)]
    if kind == "table":
        return table_question(item)
    return [Spacer(1, 3), AnswerLines(1)]


def item_block(item):
    head = Table(
        [[Paragraph(esc(item.get("id", "")), STYLES["qid"]), Paragraph(esc(item.get("question", "")), STYLES["q"])]],
        colWidths=[34, CONTENT_W - 34],
    )
    head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    parts = [head] + shown_block(item.get("currently_shown", "")) + answer_area(item) + [Spacer(1, 12)]
    # Tables can be tall; let them split. Everything else stays together.
    if item.get("answer_type") == "table":
        return parts
    return [KeepTogether(parts)]


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(MARGIN, 0.55 * inch, "ASME at the University of Iowa  |  website fact check")
    canvas.drawRightString(PAGE_W - MARGIN, 0.55 * inch, f"Page {doc.page}")
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(2)
    canvas.line(MARGIN, PAGE_H - 0.5 * inch, MARGIN + 42, PAGE_H - 0.5 * inch)
    canvas.restoreState()


def build(q: dict, out: Path, prepared_on: str | None = None):
    doc = SimpleDocTemplate(
        str(out),
        pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=0.9 * inch, bottomMargin=0.9 * inch,
        title=q.get("title", "Website fact check"),
        author="ASME at Iowa web team",
    )
    story = []
    story.append(Paragraph(esc(q.get("title", "Website fact check")), STYLES["title"]))
    story.append(Paragraph("For the President and Vice President, ASME at the University of Iowa", STYLES["subtitle"]))
    story.append(Paragraph(f"Prepared {prepared_on or date.today().strftime('%B %d, %Y')}", STYLES["subtitle"]))
    story.append(Rule(thickness=2, color=GOLD, space=8))
    story.append(Paragraph(esc(q.get("intro", "")), STYLES["intro"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "How to answer: tick a box, write on the line, or cross out and correct anything shown in the shaded "
        "boxes. Every shaded box is text that is on the website right now, or is about to be. Leave an item "
        "blank if you do not know; we will chase it separately.",
        STYLES["intro"],
    ))
    story.append(Spacer(1, 10))

    # Contents
    sections = q.get("sections") or []
    toc = [[Paragraph(esc(s.get("heading", "")), STYLES["cell"]), Paragraph(str(len(s.get("items") or [])) + " items", STYLES["cell"])] for s in sections]
    if toc:
        t = Table(toc, colWidths=[CONTENT_W - 70, 70])
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        story.append(Paragraph("Sections", STYLES["h"]))
        story.append(t)
    story.append(PageBreak())

    for s in sections:
        story.append(Paragraph(esc(s.get("heading", "")), STYLES["h"]))
        story.append(Rule(thickness=0.8, color=BLACK, space=2))
        if s.get("why"):
            story.append(Paragraph(esc(s["why"]), STYLES["why"]))
        for item in s.get("items") or []:
            story.extend(item_block(item))
        story.append(Spacer(1, 10))

    story.append(Rule(thickness=0.8, color=BLACK, space=2))
    story.append(Paragraph("Anything else the website gets wrong, or should say and does not:", STYLES["q"]))
    story.append(AnswerLines(6))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Signed off by:", STYLES["q"]))
    story.append(AnswerLines(2))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    data = json.loads(src.read_text(encoding="utf-8"))
    prepared = sys.argv[3] if len(sys.argv) > 3 else None
    build(data, dst, prepared)
    print(f"wrote {dst} ({dst.stat().st_size // 1024} KB)")
