"""Blocks → chunks: tables stay whole, text sections are packed to 200–700 tokens."""

import re
from dataclasses import dataclass

from loancopilot.ingest_pdf import Block

MIN_TOKENS = 200
MAX_TOKENS = 700
OVERLAP = 0.1


@dataclass
class ChunkDraft:
    kind: str  # text | table
    section: str
    page_from: int
    page_to: int
    text: str


@dataclass
class _Section:
    title: str
    paragraphs: list[tuple[str, int]]  # (text, page)


@dataclass
class _Table:
    title: str
    markdown: str
    page: int


def count_tokens(text: str) -> int:
    """Cheap approximation (~1.3 tokens per word); exact counts are not needed for sizing."""
    return round(len(text.split()) * 1.3)


CAPTION_WORDS = 12  # a short line right above a table ("Amounts in € thousands") is its caption


def _sections(blocks: list[Block]) -> list[_Section | _Table]:
    """Group text under headers. Headers that follow each other on one page merge
    ("Balance sheet — Amounts in € thousands"); a short caption line joins the next table."""
    out: list[_Section | _Table] = []
    title, header_page = "", None
    current: _Section | None = None
    for block in blocks:
        if block.kind == "header":
            title = f"{title} — {block.text}" if header_page == block.page else block.text
            header_page, current = block.page, None
            continue
        header_page = None
        if block.kind == "table":
            table_title = title
            caption = current.paragraphs if current else []
            words = len(" ".join(p for p, _ in caption).split())
            same_page = all(page == block.page for _, page in caption)
            if current is not None and words <= CAPTION_WORDS and same_page:
                out.pop()
                table_title = " — ".join([title, *(p for p, _ in caption)]).strip(" —")
            out.append(_Table(table_title, block.text, block.page))
            current = None
            continue
        if current is None:
            current = _Section(title, [])
            out.append(current)
        current.paragraphs.append((block.text, block.page))
    return out


def _split(section: _Section) -> list[ChunkDraft]:
    """Split one long section on paragraph boundaries with ~10% overlap."""
    drafts: list[ChunkDraft] = []
    window: list[tuple[str, int]] = []
    for para in section.paragraphs:
        if window and count_tokens(" ".join(p for p, _ in window + [para])) > MAX_TOKENS:
            drafts.append(_draft(section.title, window))
            window = _overlap(window)
        window.append(para)
    if window:
        drafts.append(_draft(section.title, window))
    return drafts


def _overlap(window: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Carry ~10% of MAX_TOKENS into the next chunk: whole trailing paragraphs if they fit,
    otherwise the trailing sentences of the last paragraph."""
    budget = MAX_TOKENS * OVERLAP
    carry: list[tuple[str, int]] = []
    for p in reversed(window):
        if count_tokens(" ".join(x for x, _ in [p, *carry])) > budget:
            break
        carry.insert(0, p)
    if carry:
        return carry
    last, page = window[-1]
    sentences = re.split(r"(?<=[.!?])\s+", last)
    tail: list[str] = []
    for sentence in reversed(sentences):
        if tail and count_tokens(" ".join([sentence, *tail])) > budget:
            break
        tail.insert(0, sentence)
    return [(" ".join(tail), page)]


def _draft(title: str, paragraphs: list[tuple[str, int]]) -> ChunkDraft:
    pages = [page for _, page in paragraphs]
    return ChunkDraft("text", title, min(pages), max(pages), "\n\n".join(p for p, _ in paragraphs))


def chunk_blocks(blocks: list[Block]) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    pending: list[_Section] = []  # small sections packed together until MIN_TOKENS

    def size(sections: list[_Section]) -> int:
        return sum(count_tokens(" ".join(p for p, _ in s.paragraphs)) for s in sections)

    def flush() -> None:
        if not pending:
            return
        if len(pending) == 1:
            chunks.extend(_split(pending[0]))
        else:  # keep sub-headings inside the text so structure survives packing
            paragraphs = [
                (f"{s.title}\n{p}" if i == 0 and s.title else p, page)
                for s in pending
                for i, (p, page) in enumerate(s.paragraphs)
            ]
            titles = [s.title for s in pending if s.title]
            chunks.extend(_split(_Section(" · ".join(dict.fromkeys(titles)), paragraphs)))
        pending.clear()

    for item in _sections(blocks):
        if isinstance(item, _Table):  # tables are always their own chunk, title kept in the text
            flush()
            text = f"{item.title}\n\n{item.markdown}" if item.title else item.markdown
            chunks.append(ChunkDraft("table", item.title, item.page, item.page, text))
            continue
        if pending and size(pending) + size([item]) > MAX_TOKENS:
            flush()
        pending.append(item)
        if size(pending) >= MIN_TOKENS:
            flush()
    flush()
    return chunks


def context_header(company: str | None, document_label: str, section: str) -> str:
    parts = [f"Company: {company}"] if company else []
    parts.append(f"Document: {document_label}")
    if section:
        parts.append(f"Section: {section}")
    return " | ".join(parts)
