"""Bank statements → transactions. CAMT.053 (any version) via xml.etree, and CSV."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET


@dataclass
class ParsedTransaction:
    booked_on: date
    amount: Decimal  # + in, − out
    counterparty_name: str | None
    counterparty_iban: str | None
    description: str | None
    balance_after: Decimal | None


class StatementError(ValueError):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el: ET.Element | None, *path: str) -> ET.Element | None:
    """Namespace-agnostic child lookup along a path of local tag names."""
    for name in path:
        if el is None:
            return None
        el = next((c for c in el if _local(c.tag) == name), None)
    return el


def _text(el: ET.Element | None, *path: str) -> str | None:
    found = _find(el, *path)
    return found.text.strip() if found is not None and found.text else None


def _descendant_text(el: ET.Element | None, name: str) -> str | None:
    if el is None:
        return None
    for child in el.iter():
        if _local(child.tag) == name and child.text and child.text.strip():
            return child.text.strip()
    return None


def _signed(el: ET.Element) -> Decimal:
    amount = Decimal(_text(el, "Amt") or "0")
    return amount if _text(el, "CdtDbtInd") == "CRDT" else -amount


def parse_camt053(data: bytes) -> list[ParsedTransaction]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise StatementError(f"Invalid XML: {exc}") from exc
    statements = [el for el in root.iter() if _local(el.tag) == "Stmt"]
    if not statements:
        raise StatementError("No CAMT.053 statements (Stmt) found in the XML file.")
    out: list[ParsedTransaction] = []
    for stmt in statements:
        opening = next(
            (b for b in stmt if _local(b.tag) == "Bal"
             and _descendant_text(_find(b, "Tp"), "Cd") in ("OPBD", "PRCD")),
            None,
        )  # fmt: skip
        balance = _signed(opening) if opening is not None else None
        for entry in (e for e in stmt if _local(e.tag) == "Ntry"):
            amount = _signed(entry)
            booked = _text(entry, "BookgDt", "Dt") or (_text(entry, "BookgDt", "DtTm") or "")[:10]
            details = _find(entry, "NtryDtls", "TxDtls")
            role = "Dbtr" if amount >= 0 else "Cdtr"
            parties = _find(details, "RltdPties")
            name = _descendant_text(_find(parties, role), "Nm")
            iban = _descendant_text(_find(parties, f"{role}Acct"), "IBAN")
            remittance = _find(details, "RmtInf")
            ustrd = [c.text.strip() for c in remittance if c.text] if remittance is not None else []
            description = " ".join(ustrd) or _text(entry, "AddtlNtryInf")
            if balance is not None:
                balance += amount
            out.append(ParsedTransaction(date.fromisoformat(booked), amount, name, iban,
                                         description, balance))  # fmt: skip
    return out


def parse_amount(value: str) -> Decimal:
    """Accepts 1234.56, -1234.56, 1.234,56, 1,234.56 and (1,234.56)."""
    v = value.strip().replace("€", "").replace(" ", "")
    negative = v.startswith("(") and v.endswith(")")
    v = v.strip("()")
    if "," in v and "." in v:
        comma_decimal = v.rfind(",") > v.rfind(".")
        v = v.replace(".", "").replace(",", ".") if comma_decimal else v.replace(",", "")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        amount = Decimal(v)
    except InvalidOperation as exc:
        raise StatementError(f"Unreadable amount: {value!r}") from exc
    return -amount if negative else amount


def _parse_date(value: str) -> date:
    v = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    raise StatementError(f"Unreadable date: {value!r}")


CSV_COLUMNS = ["date", "amount", "counterparty_name", "counterparty_iban", "description"]


def parse_csv(data: bytes) -> list[ParsedTransaction]:
    text = data.decode("utf-8-sig")
    delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    header = [re.sub(r"\s+", "_", (h or "").strip().lower()) for h in reader.fieldnames or []]
    missing = [c for c in CSV_COLUMNS if c not in header]
    if missing:
        raise StatementError(f"CSV is missing columns: {', '.join(missing)}")
    reader.fieldnames = header
    out = []
    for row in reader:
        if not (row.get("date") or "").strip():
            continue
        balance = (row.get("balance") or "").strip()
        out.append(ParsedTransaction(
            booked_on=_parse_date(row["date"]),
            amount=parse_amount(row["amount"]),
            counterparty_name=(row["counterparty_name"] or "").strip() or None,
            counterparty_iban=(row["counterparty_iban"] or "").replace(" ", "") or None,
            description=(row["description"] or "").strip() or None,
            balance_after=parse_amount(balance) if balance else None,
        ))  # fmt: skip
    return out
