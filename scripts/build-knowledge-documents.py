"""Build the version-controlled ServicePilot demo manuals as tagged source PDFs."""

from __future__ import annotations

import json
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "knowledge"
HEADING = re.compile(r"^(#{1,3})\s+(.+)$")


def register_fonts() -> tuple[str, str]:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    regular = next(path for path in candidates if path.exists())
    bold = next(path for path in bold_candidates if path.exists())
    pdfmetrics.registerFont(TTFont("ServicePilot", regular))
    pdfmetrics.registerFont(TTFont("ServicePilot-Bold", bold))
    return "ServicePilot", "ServicePilot-Bold"


def render(document: dict[str, str], regular: str, bold: str) -> None:
    source = CORPUS / document["source"]
    destination = CORPUS / document["pdf"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body", parent=styles["BodyText"], fontName=regular, fontSize=10.5,
        leading=15, textColor=colors.HexColor("#243447"), spaceAfter=4 * mm,
    )
    headings = {
        1: ParagraphStyle("H1", parent=styles["Title"], fontName=bold, fontSize=24,
                          leading=29, textColor=colors.HexColor("#0B57D0"), alignment=TA_CENTER,
                          spaceAfter=12 * mm),
        2: ParagraphStyle("H2", parent=styles["Heading2"], fontName=bold, fontSize=16,
                          leading=20, textColor=colors.HexColor("#163A5F"), spaceBefore=7 * mm,
                          spaceAfter=3 * mm),
        3: ParagraphStyle("H3", parent=styles["Heading3"], fontName=bold, fontSize=12,
                          leading=15, textColor=colors.HexColor("#295C88"), spaceBefore=4 * mm,
                          spaceAfter=2 * mm),
    }
    story = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        match = HEADING.match(line)
        if match:
            level = len(match.group(1))
            story.append(Paragraph(match.group(2), headings[level]))
            if level == 1:
                story.append(Spacer(1, 3 * mm))
        else:
            story.append(Paragraph(line.replace("·", "&middot;"), body))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular, 8)
        canvas.setFillColor(colors.HexColor("#66788A"))
        canvas.drawString(20 * mm, 12 * mm, f"{document['title']} · Version {document['version']}")
        canvas.drawRightString(190 * mm, 12 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(
        str(destination), pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=22 * mm,
        title=document["title"], author="ServicePilot Demo",
        subject="Fiktive technische Dokumentation für den ServicePilot-Demonstrator",
    )
    pdf.build(story, onFirstPage=footer, onLaterPages=footer)


def main() -> None:
    manifest = json.loads((CORPUS / "corpus.json").read_text(encoding="utf-8"))
    regular, bold = register_fonts()
    for document in manifest["documents"]:
        render(document, regular, bold)
        print(CORPUS / document["pdf"])


if __name__ == "__main__":
    main()
