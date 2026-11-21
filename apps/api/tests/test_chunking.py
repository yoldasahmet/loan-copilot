from loancopilot.chunking import MAX_TOKENS, MIN_TOKENS, chunk_blocks, context_header, count_tokens
from loancopilot.ingest_pdf import Block

SENTENCE = "The company installs heating systems for housing associations in the region."


def para(n: int) -> str:
    return " ".join([SENTENCE] * n)


def test_tables_stay_whole_and_keep_merged_headers() -> None:
    table = "| | 2025 | 2024 |\n|---|---|---|\n| Total assets | 900 | 830 |"
    chunks = chunk_blocks([
        Block("header", "Balance sheet as at 31 December 2025", 3),
        Block("header", "Amounts in € thousands", 3),
        Block("table", table, 3),
    ])  # fmt: skip
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.kind == "table"
    assert chunk.section == "Balance sheet as at 31 December 2025 — Amounts in € thousands"
    assert (chunk.page_from, chunk.page_to) == (3, 3)
    assert chunk.text.endswith(table)
    assert "€ thousands" in chunk.text  # the unit travels with the table


def test_small_sections_are_packed_with_their_headings() -> None:
    blocks = [Block("header", "Notes to the financial statements", 5)]
    for title in ["Employees", "Tangible fixed assets", "Long-term liabilities", "Leases",
                  "Events after the balance sheet date"]:  # fmt: skip
        blocks += [Block("header", title, 5), Block("text", para(3), 5)]
    chunks = chunk_blocks(blocks)
    assert len(chunks) == 1
    assert chunks[0].kind == "text"
    assert "Employees" in chunks[0].section and "Leases" in chunks[0].section
    assert "Tangible fixed assets\nThe company" in chunks[0].text
    assert chunks[0].page_from == chunks[0].page_to == 5


def test_long_section_splits_on_paragraphs_with_overlap() -> None:
    paragraphs = [Block("text", f"Paragraph {i}. " + para(6), 2 + i // 6) for i in range(18)]
    chunks = chunk_blocks([Block("header", "Directors' report", 2), *paragraphs])
    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.section == "Directors' report"
        assert count_tokens(chunk.text) <= MAX_TOKENS
    # ~10% overlap: the next chunk opens with the closing sentences of the previous one
    opening = chunks[1].text.split("\n\n")[0]
    assert chunks[0].text.endswith(opening)
    assert 0 < count_tokens(opening) <= MAX_TOKENS * 0.1 + 20
    assert chunks[0].page_from == 2 and chunks[-1].page_to == 4


def test_overlap_carries_whole_short_paragraphs() -> None:
    paragraphs = [Block("text", f"Point {i}. {SENTENCE}", 2) for i in range(60)]
    chunks = chunk_blocks([Block("header", "Notes", 2), *paragraphs])
    assert len(chunks) >= 2
    last_of_first = chunks[0].text.split("\n\n")[-1]
    assert last_of_first in chunks[1].text.split("\n\n")


def test_page_ranges_and_minimum_size() -> None:
    chunks = chunk_blocks([
        Block("header", "Cover", 1),
        Block("text", "Testbouw B.V. Annual report 2025", 1),
        Block("header", "Directors' report", 2),
        Block("text", para(16), 2),
    ])  # fmt: skip
    assert len(chunks) == 1
    assert (chunks[0].page_from, chunks[0].page_to) == (1, 2)
    assert count_tokens(chunks[0].text) >= MIN_TOKENS


def test_context_header() -> None:
    header = context_header("Testbouw B.V.", "Annual report 2025", "Directors' report")
    assert (
        header
        == "Company: Testbouw B.V. | Document: Annual report 2025 | Section: Directors' report"
    )


def test_caption_text_above_table_joins_the_table_title() -> None:
    chunks = chunk_blocks([
        Block("header", "Profit and loss account 2025", 4),
        Block("text", "Amounts in EUR", 4),
        Block("table", "| | 2025 |\n|---|---|\n| Revenue | 3,400,000 |", 4),
    ])  # fmt: skip
    assert [c.kind for c in chunks] == ["table"]
    assert chunks[0].section == "Profit and loss account 2025 — Amounts in EUR"


def test_headers_on_an_earlier_page_do_not_leak_into_the_next_title() -> None:
    chunks = chunk_blocks([
        Block("header", "Testbouw B.V.", 1),
        Block("header", "Annual report 2025", 1),
        Block("header", "Directors' report", 2),
        Block("text", para(16), 2),
    ])  # fmt: skip
    assert [c.section for c in chunks] == ["Directors' report"]
