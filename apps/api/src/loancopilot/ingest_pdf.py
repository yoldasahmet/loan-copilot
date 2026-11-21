"""Docling → a flat list of blocks (headers, paragraphs, markdown tables) with page numbers."""

import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import ListItem, SectionHeaderItem, TableItem, TextItem

SCANNED_PDF_ERROR = "Scanned PDFs are not supported."
_lock = threading.Lock()  # one conversion at a time keeps CPU and memory predictable


@dataclass
class Block:
    kind: Literal["header", "text", "table"]
    text: str
    page: int


@dataclass
class ParsedPdf:
    blocks: list[Block]
    page_count: int


class ParseError(Exception):
    pass


@lru_cache
def _converter() -> DocumentConverter:
    options = PdfPipelineOptions(do_ocr=False)  # digital PDFs only
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def parse_pdf(path: Path) -> ParsedPdf:
    with _lock:
        doc = _converter().convert(path).document
    blocks: list[Block] = []
    for item, _level in doc.iterate_items():
        page = item.prov[0].page_no if item.prov else 1
        if isinstance(item, TableItem):
            blocks.append(Block("table", item.export_to_markdown(doc=doc), page))
        elif isinstance(item, SectionHeaderItem):
            blocks.append(Block("header", item.text.strip(), page))
        elif isinstance(item, ListItem):
            blocks.append(Block("text", f"- {item.text.strip()}", page))
        elif isinstance(item, TextItem) and item.text.strip():
            blocks.append(Block("text", item.text.strip(), page))
    if sum(len(b.text) for b in blocks if b.kind != "header") < 40:
        raise ParseError(SCANNED_PDF_ERROR)
    return ParsedPdf(blocks=blocks, page_count=len(doc.pages))
