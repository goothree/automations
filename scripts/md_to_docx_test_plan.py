#!/usr/bin/env python3
"""Convert IDA-5376 test plan markdown to Word (.docx)."""

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt, RGBColor


def add_hyperlink(paragraph, text, url):
    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    run_elem = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    r_pr.append(color)
    r_pr.append(underline)
    run_elem.append(r_pr)
    text_elem = OxmlElement("w:t")
    text_elem.text = text
    run_elem.append(text_elem)
    hyperlink.append(run_elem)
    paragraph._p.append(hyperlink)


def add_formatted_text(paragraph, text, style=None):
    """Add text with **bold**, `code`, and [links](url)."""
    if style:
        paragraph.style = style
    pattern = re.compile(
        r"(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))"
    )
    pos = 0
    for match in pattern.finditer(text):
        if match.start() > pos:
            paragraph.add_run(text[pos : match.start()])
        chunk = match.group(0)
        if chunk.startswith("**"):
            run = paragraph.add_run(chunk[2:-2])
            run.bold = True
        elif chunk.startswith("`"):
            run = paragraph.add_run(chunk[1:-1])
            run.font.name = "Courier New"
            run.font.size = Pt(10)
        elif chunk.startswith("["):
            link_match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", chunk)
            if link_match:
                add_hyperlink(paragraph, link_match.group(1), link_match.group(2))
        pos = match.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def parse_table_rows(lines, start_idx):
    rows = []
    i = start_idx
    while i < len(lines) and lines[i].strip().startswith("|"):
        row = [cell.strip() for cell in lines[i].strip().strip("|").split("|")]
        rows.append(row)
        i += 1
    return rows, i


def is_separator_row(row):
    return all(re.match(r"^:?-+:?$", cell.strip()) for cell in row if cell.strip())


def add_table(doc, rows):
    if not rows:
        return
    data_rows = [r for r in rows if not is_separator_row(r)]
    if not data_rows:
        return
    cols = max(len(r) for r in data_rows)
    table = doc.add_table(rows=len(data_rows), cols=cols)
    table.style = "Table Grid"
    for r_idx, row in enumerate(data_rows):
        for c_idx in range(cols):
            cell_text = row[c_idx] if c_idx < len(row) else ""
            cell = table.rows[r_idx].cells[c_idx]
            cell.text = ""
            p = cell.paragraphs[0]
            add_formatted_text(p, cell_text)
            if r_idx == 0:
                for run in p.runs:
                    run.bold = True


def convert_md_to_docx(md_path: Path, docx_path: Path):
    lines = md_path.read_text(encoding="utf-8").splitlines()
    doc = Document()

    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    i = 0
    in_list = None  # 'ul' or 'ol'
    list_counter = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped == "---":
            doc.add_paragraph()
            i += 1
            continue

        if stripped.startswith("|"):
            if in_list:
                in_list = None
            rows, i = parse_table_rows(lines, i)
            add_table(doc, rows)
            continue

        if stripped.startswith("### "):
            in_list = None
            doc.add_heading(stripped[4:], level=3)
            i += 1
            continue

        if stripped.startswith("## "):
            in_list = None
            doc.add_heading(stripped[3:], level=2)
            i += 1
            continue

        if stripped.startswith("# "):
            in_list = None
            doc.add_heading(stripped[2:], level=1)
            i += 1
            continue

        ol_match = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if ol_match:
            in_list = "ol"
            p = doc.add_paragraph(style="List Number")
            add_formatted_text(p, ol_match.group(2))
            i += 1
            while i < len(lines):
                sub = lines[i]
                sub_stripped = sub.strip()
                if sub_stripped.startswith("- "):
                    sub_p = doc.add_paragraph(style="List Bullet 2")
                    add_formatted_text(sub_p, sub_stripped[2:])
                    i += 1
                elif sub_stripped == "":
                    i += 1
                    break
                elif re.match(r"^\d+\.", sub_stripped) or sub_stripped.startswith("#"):
                    break
                else:
                    break
            continue

        if stripped.startswith("- "):
            in_list = "ul"
            p = doc.add_paragraph(style="List Bullet")
            add_formatted_text(p, stripped[2:])
            i += 1
            continue

        if stripped == "":
            in_list = None
            i += 1
            continue

        in_list = None
        p = doc.add_paragraph()
        add_formatted_text(p, stripped)
        i += 1

    docx_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(docx_path))
    print(f"Wrote {docx_path}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    md = root / "reports" / "IDA-5376_test_plan.md"
    out = root / "reports" / "IDA-5376_test_plan.docx"
    if len(sys.argv) > 1:
        md = Path(sys.argv[1])
    if len(sys.argv) > 2:
        out = Path(sys.argv[2])
    elif len(sys.argv) > 1:
        out = md.with_suffix(".docx")
    convert_md_to_docx(md, out)
