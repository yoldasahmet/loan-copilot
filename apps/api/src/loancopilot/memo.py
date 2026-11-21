"""Loan memo: evidence as numbered sources, one drafting call, and a number verifier in code."""

import re
import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from loancopilot import llm
from loancopilot.analysis import format_ratio
from loancopilot.extraction import FIELDS
from loancopilot.ingest import document_label
from loancopilot.models import Analysis, Case, Company, Document, Financial, User
from loancopilot.retrieval import Hit, Scope, search
from loancopilot.security import case_pseudonymiser

MEMO_QUESTIONS = [
    "What does the business do and who are its customers?",
    "How did revenue and results develop and why?",
    "What are the main risks for the business?",
    "What is the purpose of the loan and the investment plan?",
]
MEMO_TOP_K = 8
SECTIONS = [
    "Summary", "Company", "Loan request", "Financial analysis", "Cash flow",
    "Risks and mitigants", "Similar cases", "Lender options", "Missing documents",
]  # fmt: skip


@dataclass
class Source:
    id: str
    type: str  # document | figure | metric | precedent | lender
    title: str
    text: str
    document_id: str | None = None
    page_from: int | None = None
    page_to: int | None = None


def _eur(value: float | None) -> str:
    return "n/a" if value is None else f"€{value:,.0f}"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


# ---------------------------------------------------------------- evidence texts (all from code)


def figure_text(fy: Financial) -> str:
    lines = [f"Financial figures {fy.year} (EUR):"]
    for field in FIELDS:
        value = getattr(fy, field)
        shown = _eur(float(value)) if value is not None else "n/a"
        lines.append(f"- {field.replace('_', ' ')}: {shown}")
    return "\n".join(lines)


def ratio_text(ratios: dict) -> str:
    lines = [f"Ratios {ratios.get('year')} computed in code:"]
    for item in ratios.get("items", []):
        line = f"- {item['label']}: {format_ratio(item['value'], item['kind'])} ({item['status']}"
        if item["threshold"] is not None:
            sign = "≥" if item["higher_is_better"] else "≤"
            line += f"; threshold {sign} {format_ratio(item['threshold'], item['kind'], 0)}"
        lines.append(line + ")")
    a = ratios.get("assumptions") or {}
    if a:
        lines.append(
            f"DSCR assumes the requested {_eur(a['loan_amount'])} over {a['term_months']} months "
            f"at {_pct(a['interest_rate'])}: new annual debt service "
            f"{_eur(a['new_annual_debt_service'])}, existing annual debt service "
            f"{_eur(a['existing_annual_debt_service'])}."
        )
    return "\n".join(lines)


def cashflow_text(cf: dict, flags: list[dict]) -> str:
    share = cf.get("top_customer_share")
    taxes = ", ".join(f"{q['quarter']} {_eur(q['amount'])}" for q in cf["tax_per_quarter"])
    red_flags = "; ".join(f"{f['title']}: {f['detail']}" for f in flags) or "none"
    return "\n".join([
        f"Cash flow {cf['period_start']} to {cf['period_end']} (bank transactions):",
        f"- Average monthly inflow: {_eur(cf['avg_monthly_inflow'])}",
        f"- Months with negative net cash flow: {cf['months_negative_net']}",
        f"- Days with a negative balance: {cf['negative_balance_days']}",
        f"- Largest customer share of inflow: {'n/a' if share is None else f'{share:.0%}'}",
        f"- Existing annual debt service: {_eur(cf['existing_annual_debt_service'])}",
        f"- Tax payments per quarter: {taxes}",
        f"Red flags: {red_flags}",
    ])  # fmt: skip


def precedent_text(s: dict) -> str:
    lines = [
        f"Similar case {s['ref']}: {s['sector_group']}, {s['legal_form']}, revenue "
        f"{_eur(s['revenue'])}, requested {_eur(s['loan_amount'])} for "
        f"{s['loan_purpose'].replace('_', ' ')} over {s['term_months']} months, applied "
        f"{s['applied_on']}. Similarity: {', '.join(s['reasons']) or 'profile'}."
    ]
    for d in s["decisions"]:
        if d["decision"] == "approved":
            rate = "" if d["interest_rate"] is None else f" at {_pct(d['interest_rate'])}"
            lines.append(f"- {d['lender']}: approved {_eur(d['amount_granted'])}{rate}")
        else:
            reason = d["decline_reason"] or "no reason given"
            lines.append(f"- {d['lender']}: {d['decision']} ({reason})")
    return "\n".join(lines)


def lender_text(item: dict) -> str:
    states = {True: "passed", False: "failed", None: "unknown"}
    checks = "; ".join(
        f"{c['check']} {states[c['passed']]} ({c['value']}, {c['requirement']})"
        for c in item["checks"]
    )
    p = item["precedents"]
    text = (
        f"Lender {item['name']} ({item['product_type'].replace('_', ' ')}), typical rate "
        f"{_pct(item['typical_rate_min'])}–{_pct(item['typical_rate_max'])}. Hard checks: "
        f"{checks}. Approved {p['approved']} of {p['decided']} similar cases."
    )
    return text + (f" Fit summary: {item['summary']}" if item.get("summary") else "")


def gather_evidence(db: Session, case: Case, similar: list[dict],
                    lenders: dict | None) -> list[Source]:  # fmt: skip
    """All evidence for the memo, numbered S1..Sn in a stable order."""
    sources: list[Source] = []

    def add(kind: str, title: str, text: str, hit: Hit | None = None) -> None:
        sources.append(Source(f"S{len(sources) + 1}", kind, title, text))
        if hit is not None and hit.document_id:
            sources[-1].document_id = str(hit.document_id)
            sources[-1].page_from, sources[-1].page_to = hit.page_from, hit.page_to

    documents = db.scalars(select(Document).where(Document.case_id == case.id))
    labels = {d.id: document_label(d) for d in documents}
    # The agent acts for the case's advisor, so retrieval keeps the normal access filter.
    advisor = db.get_one(User, case.advisor_id)
    scope = Scope("case", user=advisor, case_id=case.id)
    seen: set[uuid.UUID] = set()
    for question in MEMO_QUESTIONS:
        for hit in search(db, question, scope, k=MEMO_TOP_K):
            if hit.chunk_id in seen or hit.kind == "analysis" or hit.document_id is None:
                continue
            seen.add(hit.chunk_id)
            add("document", f"{labels.get(hit.document_id, 'Document')}, p. {hit.page_from}",
                hit.text, hit)  # fmt: skip

    financials = select(Financial).where(Financial.case_id == case.id).order_by(Financial.year)
    for fy in db.scalars(financials):
        add("figure", f"Financial figures {fy.year}", figure_text(fy))
    analysis = db.get(Analysis, case.id)
    if analysis and analysis.ratios:
        add("metric", "Ratios", ratio_text(analysis.ratios))
    if analysis and analysis.cashflow:
        add(
            "metric",
            "Cash flow and red flags",
            cashflow_text(analysis.cashflow, analysis.red_flags),
        )
    if analysis:
        missing = [f"{m['document']} ({m['reason']})" for m in analysis.missing_documents
                   if not m["present"]]  # fmt: skip
        add("metric", "Missing documents", "Missing documents: " + ("; ".join(missing) or "none"))
    company = db.get_one(Company, case.company_id)
    purpose = case.loan_purpose.replace("_", " ")
    request = (
        f"Loan request: {_eur(float(case.loan_amount))} for {purpose} over "
        f"{case.loan_term_months} months. Company founded in {company.founded_year}, "
        f"{company.employees} employees, legal form {company.legal_form}. {case.notes or ''}"
    )
    add("metric", "Loan request", request)
    for s in similar:
        add("precedent", f"Similar case {s['ref']}", precedent_text(s))
    for item in (lenders or {}).get("lenders", []):
        add("lender", f"Lender {item['name']}", lender_text(item))
    return sources


def source_refs(sources: list[Source]) -> list[dict]:
    return [asdict(s) for s in sources]


def format_evidence(sources: list[Source]) -> str:
    blocks = [f'<source id="{s.id}" type="{s.type}" title="{s.title}">\n{s.text}\n</source>'
              for s in sources]  # fmt: skip
    return "\n\n".join(blocks)


def draft(db: Session, case: Case, sources: list[Source], unverified: list[str],
          review_note: str | None) -> str:  # fmt: skip
    """One LLM call writes the memo; feedback from the verifier or the advisor is appended."""
    content = format_evidence(sources)
    revisions = []
    if unverified:
        listed = ", ".join(unverified)
        revisions.append(
            f"The previous draft contained numbers that are not in the sources: "
            f"{listed}. Remove them or use the exact source values."
        )
    if review_note:
        revisions.append(f"The advisor requested these changes: {review_note}")
    if revisions:
        content += "\n\nRevision instructions:\n" + "\n".join(f"- {r}" for r in revisions)
    result = llm.complete(
        kind="memo", prompt=llm.load_prompt("memo"), user_content=content, case_id=case.id,
        source_ids=[s.id for s in sources], pii=case_pseudonymiser(db, case.id),
        max_tokens=16000, effort="low",
    )  # fmt: skip
    return result.text.strip()


# ---------------------------------------------------------------- number verification

NUMBER_RE = re.compile(
    r"(?P<eur>€\s?)?(?P<num>-?\d{1,3}(?:[,.]\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)"
    r"\s?(?P<suffix>%|x\b|×|k\b|K\b|m\b|M\b|million\b|mln\b|bn\b|billion\b|thousand\b)?"
)
SCALE = {"k": 1e3, "K": 1e3, "thousand": 1e3, "m": 1e6, "M": 1e6, "million": 1e6,
         "mln": 1e6, "bn": 1e9, "billion": 1e9}  # fmt: skip


@dataclass
class Number:
    text: str
    value: float
    step: float  # display precision (same scale): the rounding tolerance is half a step
    kind: str  # money | percent | multiple | plain


def parse_number(match: re.Match) -> Number:
    raw, suffix, eur = match.group("num"), match.group("suffix"), match.group("eur")
    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        digits = raw.replace(",", "")
    elif re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+", raw):  # 1.234.567
        digits = raw.replace(".", "")
    else:
        digits = raw
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    scale = SCALE.get(suffix or "", 1.0)
    if suffix == "%":
        kind = "percent"
    elif suffix in ("x", "×"):
        kind = "multiple"
    else:
        kind = "money" if eur or suffix in SCALE else "plain"
    return Number(match.group(0).strip(), float(digits) * scale, 10**-decimals * scale, kind)


def extract_numbers(text: str) -> list[Number]:
    """Numbers to verify in memo text: not years, citation ids, list markers or small counts."""
    text = re.sub(r"\[S\d+\]", " ", text)
    text = re.sub(r"^\s*(?:#+|\d+\.)\s", " ", text, flags=re.M)
    out = []
    for match in NUMBER_RE.finditer(text):
        n = parse_number(match)
        before = text[max(0, match.start() - 1) : match.start()]
        glued = before.isalnum() or before in "-–/"  # inside a word, a range or a date
        if glued and not match.group("eur"):
            continue
        is_integer = float(n.value).is_integer()
        if n.kind == "plain" and is_integer and (1900 <= n.value <= 2100 or abs(n.value) <= 10):
            continue
        out.append(n)
    return out


def known_values(sources: list[Source]) -> list[float]:
    """Every number that appears in the evidence, scaled (€3.4 million → 3,400,000)."""
    return [parse_number(m).value for s in sources for m in NUMBER_RE.finditer(s.text)]


def verify_numbers(memo_md: str, sources: list[Source]) -> dict:
    """A memo number passes when the evidence holds it exactly or within display rounding (±1%)."""
    known = known_values(sources)
    numbers, unverified = [], []
    for n in extract_numbers(memo_md):
        tolerance = max(abs(n.value) * 0.01, n.step / 2)
        ok = any(abs(abs(n.value) - abs(k)) <= tolerance for k in known)
        numbers.append({"text": n.text, "value": n.value, "verified": ok})
        if not ok:
            unverified.append(n.text)
    unique = list(dict.fromkeys(unverified))
    return {"total": len(numbers), "verified": len(numbers) - len(unverified),
            "unverified": unique, "numbers": numbers}  # fmt: skip


def missing_sections(memo_md: str) -> list[str]:
    headings = {h.strip().lower() for h in re.findall(r"^##\s+(.+)$", memo_md, flags=re.M)}
    return [s for s in SECTIONS if s.lower() not in headings]
