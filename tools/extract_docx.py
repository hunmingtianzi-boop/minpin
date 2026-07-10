from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def iter_blocks(document: DocumentObject) -> Iterable[Paragraph | Table]:
    """Yield paragraphs and tables in their original document order."""
    for child in document.element.body.iterchildren():
        if child.tag == f"{{{W_NS}}}p":
            yield Paragraph(child, document)
        elif child.tag == f"{{{W_NS}}}tbl":
            yield Table(child, document)


def paragraph_record(paragraph: Paragraph, index: int) -> dict[str, Any]:
    p_pr = paragraph._p.pPr
    num_id = None
    num_level = None
    if p_pr is not None and p_pr.numPr is not None:
        if p_pr.numPr.numId is not None:
            num_id = p_pr.numPr.numId.val
        if p_pr.numPr.ilvl is not None:
            num_level = p_pr.numPr.ilvl.val

    hyperlinks = []
    for link in paragraph._p.xpath(".//w:hyperlink"):
        text = "".join(link.xpath(".//w:t/text()"))
        rel_id = link.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        anchor = link.get(f"{{{W_NS}}}anchor")
        hyperlinks.append({"text": text, "rel_id": rel_id, "anchor": anchor})

    return {
        "id": f"P{index:04d}",
        "type": "paragraph",
        "style": paragraph.style.name if paragraph.style else None,
        "text": paragraph.text,
        "numbering": {"num_id": num_id, "level": num_level} if num_id is not None else None,
        "hyperlinks": hyperlinks,
    }


def table_record(table: Table, index: int) -> dict[str, Any]:
    rows: list[list[dict[str, Any]]] = []
    for row in table.rows:
        row_data = []
        for cell in row.cells:
            paragraphs = []
            for paragraph in cell.paragraphs:
                paragraphs.append(
                    {
                        "style": paragraph.style.name if paragraph.style else None,
                        "text": paragraph.text,
                    }
                )
            row_data.append(
                {
                    "text": "\n".join(p["text"] for p in paragraphs if p["text"]),
                    "paragraphs": paragraphs,
                }
            )
        rows.append(row_data)
    return {
        "id": f"T{index:03d}",
        "type": "table",
        "style": table.style.name if table.style else None,
        "rows": rows,
    }


def extract(source: Path) -> dict[str, Any]:
    doc = Document(source)
    blocks: list[dict[str, Any]] = []
    paragraph_index = 0
    table_index = 0
    for block in iter_blocks(doc):
        if isinstance(block, Paragraph):
            paragraph_index += 1
            blocks.append(paragraph_record(block, paragraph_index))
        else:
            table_index += 1
            blocks.append(table_record(block, table_index))

    core = doc.core_properties
    inline_shapes = len(doc.inline_shapes)
    rels = doc.part.rels
    image_count = sum(1 for rel in rels.values() if "image" in rel.reltype)
    return {
        "source": str(source.resolve()),
        "metadata": {
            "title": core.title,
            "subject": core.subject,
            "author": core.author,
            "last_modified_by": core.last_modified_by,
            "created": core.created.isoformat() if core.created else None,
            "modified": core.modified.isoformat() if core.modified else None,
            "paragraph_count": paragraph_index,
            "table_count": table_index,
            "inline_shape_count": inline_shapes,
            "image_relationship_count": image_count,
        },
        "blocks": blocks,
    }


def escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def to_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# {Path(data['source']).stem}",
        "",
        f"- 源文件：`{data['source']}`",
        f"- 段落：{data['metadata']['paragraph_count']}",
        f"- 表格：{data['metadata']['table_count']}",
        f"- 图片关系：{data['metadata']['image_relationship_count']}",
        "",
    ]
    for block in data["blocks"]:
        if block["type"] == "paragraph":
            text = block["text"].strip()
            if not text:
                continue
            style = block["style"] or "Normal"
            lines.append(f"[{block['id']}] [{style}] {text}")
            lines.append("")
            continue

        rows = block["rows"]
        width = max((len(row) for row in rows), default=0)
        lines.append(f"[{block['id']}] [TABLE style={block['style'] or 'None'}]")
        lines.append("")
        if width:
            for row_index, row in enumerate(rows, start=1):
                values = [escape_cell(cell["text"]) for cell in row]
                values.extend([""] * (width - len(values)))
                lines.append(f"[{block['id']}-R{row_index:02d}] | " + " | ".join(values) + " |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract DOCX paragraphs and tables with stable evidence IDs.")
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for source in args.sources:
        data = extract(source)
        stem = source.stem
        (args.output_dir / f"{stem}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (args.output_dir / f"{stem}.md").write_text(to_markdown(data), encoding="utf-8")
        print(f"extracted: {source} -> {args.output_dir / (stem + '.md')}")


if __name__ == "__main__":
    main()
