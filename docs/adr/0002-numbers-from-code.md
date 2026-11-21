# 0002 Numbers computed in code; the LLM extracts and writes prose only

**Status:** accepted

## Context
LLMs are good at reading documents and writing text, and unreliable at arithmetic. A loan memo with a wrong DSCR is worse than no memo.

## Decision
- The LLM extracts raw figures from annual reports as JSON with the page each value came from. Code checks that the number appears on that page and that the balance sheet and P&L add up.
- All ratios, cash-flow metrics and totals are calculated in Python.
- After the LLM drafts the memo, code extracts every number from the text and checks it against the known values. Unverified numbers trigger a redraft (up to two) and are highlighted for the advisor.

## Consequences
- Every number in the UI can be traced to code or to a source page.
- Extraction mistakes surface as warnings instead of silently changing ratios, and advisors can correct figures inline.
