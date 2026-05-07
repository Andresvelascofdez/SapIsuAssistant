from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "TECHNICAL_IP_DOSSIER.md"
OUTPUT = ROOT / "TECHNICAL_IP_DOSSIER.pdf"


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DossierTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DossierSubtitle",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#4b5563"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DossierH1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=21,
            textColor=colors.HexColor("#111827"),
            spaceBefore=6,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DossierH2",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#1f2937"),
            spaceBefore=9,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DossierBody",
            parent=styles["BodyText"],
            alignment=TA_LEFT,
            fontSize=9.4,
            leading=13.2,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DossierBullet",
            parent=styles["BodyText"],
            fontSize=9.2,
            leading=12.5,
            leftIndent=7,
            firstLineIndent=0,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DossierCode",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=7.2,
            leading=8.8,
            borderColor=colors.HexColor("#d1d5db"),
            borderWidth=0.5,
            borderPadding=6,
            backColor=colors.HexColor("#f9fafb"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DossierFooter",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#6b7280"),
        )
    )
    return styles


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("`", "")
    )


def _flush_paragraph(paragraph_lines: list[str], story: list, styles) -> None:
    if not paragraph_lines:
        return
    text = " ".join(line.strip() for line in paragraph_lines).strip()
    if text:
        story.append(Paragraph(_escape(text), styles["DossierBody"]))
    paragraph_lines.clear()


def _flush_bullets(bullets: list[str], story: list, styles) -> None:
    if not bullets:
        return
    story.append(
        ListFlowable(
            [
                ListItem(
                    Paragraph(_escape(item), styles["DossierBullet"]),
                    leftIndent=9,
                )
                for item in bullets
            ],
            bulletType="bullet",
            start="circle",
            leftIndent=15,
            bulletFontSize=6,
        )
    )
    story.append(Spacer(1, 2 * mm))
    bullets.clear()


def build_story(markdown: str) -> list:
    styles = _styles()
    story: list = []
    paragraph_lines: list[str] = []
    bullets: list[str] = []
    code_lines: list[str] = []
    in_code = False
    first_h1 = True

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.strip().startswith("```"):
            _flush_paragraph(paragraph_lines, story, styles)
            _flush_bullets(bullets, story, styles)
            if in_code:
                story.append(Preformatted("\n".join(code_lines), styles["DossierCode"]))
                code_lines.clear()
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if line.strip() == "<!-- pagebreak -->":
            _flush_paragraph(paragraph_lines, story, styles)
            _flush_bullets(bullets, story, styles)
            story.append(PageBreak())
            continue

        if not line.strip():
            _flush_paragraph(paragraph_lines, story, styles)
            _flush_bullets(bullets, story, styles)
            continue

        if line.startswith("# "):
            _flush_paragraph(paragraph_lines, story, styles)
            _flush_bullets(bullets, story, styles)
            text = line[2:].strip()
            if first_h1:
                story.append(Spacer(1, 38 * mm))
                story.append(Paragraph(_escape(text), styles["DossierTitle"]))
                first_h1 = False
            else:
                story.append(Paragraph(_escape(text), styles["DossierH1"]))
            continue

        if line.startswith("## "):
            _flush_paragraph(paragraph_lines, story, styles)
            _flush_bullets(bullets, story, styles)
            story.append(Paragraph(_escape(line[3:].strip()), styles["DossierH2"]))
            continue

        if line.startswith("- "):
            _flush_paragraph(paragraph_lines, story, styles)
            bullets.append(line[2:].strip())
            continue

        if first_h1 is False and len(story) <= 4 and not line.startswith("#"):
            story.append(Paragraph(_escape(line), styles["DossierSubtitle"]))
            continue

        paragraph_lines.append(line)

    _flush_paragraph(paragraph_lines, story, styles)
    _flush_bullets(bullets, story, styles)
    if in_code and code_lines:
        story.append(Preformatted("\n".join(code_lines), styles["DossierCode"]))
    return story


def _footer(canvas, doc) -> None:
    canvas.saveState()
    width, _height = A4
    canvas.setStrokeColor(colors.HexColor("#e5e7eb"))
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawCentredString(
        width / 2,
        9 * mm,
        f"SAP IS-U Assistant - Technical IP Dossier - Page {doc.page}",
    )
    canvas.restoreState()


def generate() -> Path:
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=19 * mm,
        title="SAP IS-U Assistant Technical IP Dossier",
        author="SAP IS-U Assistant",
        subject="Technical IP Dossier",
    )
    story = build_story(SOURCE.read_text(encoding="utf-8"))
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return OUTPUT


if __name__ == "__main__":
    print(generate())
