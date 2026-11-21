"""Upload checks and pseudonymisation of personal data before LLM calls."""

import re
import uuid
from collections.abc import Iterable, Iterator
from pathlib import PurePath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MIME = {"pdf": "application/pdf", "xml": "application/xml", "csv": "text/csv"}


class UploadRejected(ValueError):
    pass


def _looks_like_csv(data: bytes) -> bool:
    try:
        text = data[:4096].decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    first = text.splitlines()[0] if text else ""
    return "\x00" not in text and ("," in first or ";" in first)


def check_upload(filename: str, data: bytes) -> str:
    """Validate extension, size and magic bytes. Returns the normalised extension."""
    ext = PurePath(filename).suffix.lower().lstrip(".")
    if ext not in MIME:
        raise UploadRejected("Only PDF, XML and CSV files are allowed.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("Files may be at most 20 MB.")
    if not data:
        raise UploadRejected("The file is empty.")
    head = data[:64].lstrip(b"\xef\xbb\xbf \t\r\n")
    valid = {
        "pdf": data.startswith(b"%PDF-"),
        "xml": head.startswith(b"<?xml") or head.startswith(b"<"),
        "csv": not head.startswith((b"%PDF", b"<")) and _looks_like_csv(data),
    }[ext]
    if not valid:
        raise UploadRejected(f"The file content does not match the .{ext} extension.")
    return ext


# ---------------------------------------------------------------- pseudonymisation

IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,7}(?:\s?[A-Z0-9]{1,3})?\b")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE_RE = re.compile(r"(?<![\w€])(?:\+31|0031|0)[\s-]?(?:\d[\s-]?){8,9}\b")
LEGAL_SUFFIX_RE = re.compile(r"\s+(?:B\.?V\.?|V\.?O\.?F\.?|N\.?V\.?)$", re.IGNORECASE)
PLACEHOLDER_MAX = 20  # longest placeholder, e.g. [COUNTERPARTY_20]


class Pseudonymiser:
    """Replaces names, IBANs, emails and phone numbers with placeholders before an LLM call,
    and restores them in the response (also across streamed chunks)."""

    def __init__(self, company: str | None = None, people: Iterable[str] = (),
                 counterparties: Iterable[str] = ()) -> None:  # fmt: skip
        self.originals: dict[str, str] = {}  # placeholder -> original
        self._names: list[tuple[re.Pattern[str], str]] = []
        if company:
            self.originals["[COMPANY]"] = company
            for variant in {company, LEGAL_SUFFIX_RE.sub("", company)}:
                self._add_name(variant, "[COMPANY]")
        for i, person in enumerate(dict.fromkeys(p for p in people if p), start=1):
            self.originals[f"[PERSON_{i}]"] = person
            self._add_name(person, f"[PERSON_{i}]")
        for i, name in enumerate(dict.fromkeys(c for c in counterparties if c), start=1):
            if name == company:
                continue
            self.originals[f"[COUNTERPARTY_{i}]"] = name
            self._add_name(name, f"[COUNTERPARTY_{i}]")
        self._names.sort(key=lambda pair: -len(pair[0].pattern))
        self._counters: dict[str, int] = {}
        self._seen: dict[str, str] = {}  # original value -> placeholder (IBAN/email/phone)

    def _add_name(self, name: str, placeholder: str) -> None:
        if len(name.strip()) >= 3:
            self._names.append((re.compile(re.escape(name.strip()), re.IGNORECASE), placeholder))

    def _pattern_placeholder(self, kind: str, value: str) -> str:
        key = re.sub(r"\s", "", value)
        if key not in self._seen:
            self._counters[kind] = self._counters.get(kind, 0) + 1
            placeholder = f"[{kind}_{self._counters[kind]}]"
            self._seen[key] = placeholder
            self.originals[placeholder] = value
        return self._seen[key]

    def mask(self, text: str) -> str:
        text = IBAN_RE.sub(lambda m: self._pattern_placeholder("IBAN", m.group()), text)
        text = EMAIL_RE.sub(lambda m: self._pattern_placeholder("EMAIL", m.group()), text)
        text = PHONE_RE.sub(lambda m: self._pattern_placeholder("PHONE", m.group()), text)
        for pattern, placeholder in self._names:
            text = pattern.sub(placeholder, text)
        return text

    def unmask(self, text: str) -> str:
        return re.sub(r"\[[A-Z]+(?:_\d+)?\]", lambda m: self.originals.get(m.group(), m.group()),
                      text)  # fmt: skip

    def unmask_stream(self, chunks: Iterable[str]) -> Iterator[str]:
        """Restore placeholders in a token stream, holding back a possibly split placeholder."""
        buffer = ""
        for chunk in chunks:
            buffer += chunk
            cut = buffer.rfind("[")
            if cut != -1 and "]" not in buffer[cut:] and len(buffer) - cut <= PLACEHOLDER_MAX:
                ready, buffer = buffer[:cut], buffer[cut:]
            else:
                ready, buffer = buffer, ""
            if ready:
                yield self.unmask(ready)
        if buffer:
            yield self.unmask(buffer)


def case_pseudonymiser(db: "Session", case_id: uuid.UUID) -> Pseudonymiser:
    """Company, contact person and the 20 largest counterparties of a case."""
    from sqlalchemy import func, select

    from loancopilot.models import Case, Company, Transaction

    case = db.get_one(Case, case_id)
    company = db.get_one(Company, case.company_id)
    volume = func.sum(func.abs(Transaction.amount))
    top = db.scalars(
        select(Transaction.counterparty_name)
        .where(Transaction.case_id == case_id, Transaction.counterparty_name.is_not(None))
        .group_by(Transaction.counterparty_name)
        .order_by(volume.desc())
        .limit(20)
    )
    return Pseudonymiser(company.name, [company.contact_name or ""], list(top))


# ---------------------------------------------------------------- prompt-injection scan

INJECTION_PATTERNS = [
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier) instructions",
    r"disregard (?:all |any )?(?:the )?(?:previous|prior|above) (?:instructions|rules)",
    r"system prompt",
    r"you are now",
    r"act as (?:an? )?(?:ai|assistant|credit committee)",
    r"new instructions?:",
    r"do not (?:tell|mention|reveal)",
    r"recommend (?:the )?approval",
    r"<\s*/?\s*(?:system|instructions?)\s*>",
]
_INJECTION = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def injection_matches(text: str) -> list[str]:
    """Phrases that look like instructions to an AI (the document is flagged, not altered)."""
    found = []
    for pattern in _INJECTION:
        match = pattern.search(text)
        if match:
            found.append(match.group(0))
    return found
