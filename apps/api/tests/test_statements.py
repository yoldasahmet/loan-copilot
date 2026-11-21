from datetime import date
from decimal import Decimal

import pytest

from loancopilot.ingest_statements import StatementError, parse_amount, parse_camt053, parse_csv

CAMT_V08 = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.08">
  <BkToCstmrStmt>
    <Stmt>
      <Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">1000.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><Dt><Dt>2026-01-01</Dt></Dt></Bal>
      <Ntry>
        <Amt Ccy="EUR">250.50</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2026-01-05</Dt></BookgDt>
        <NtryDtls><TxDtls>
          <RltdPties><Dbtr><Pty><Nm>Klant Een B.V.</Nm></Pty></Dbtr>
            <DbtrAcct><Id><IBAN>NL91DEMO0417164300</IBAN></Id></DbtrAcct></RltdPties>
          <RmtInf><Ustrd>Payment invoice INV-1</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>
      <Ntry>
        <Amt Ccy="EUR">1500.00</Amt><CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2026-01-28</Dt></BookgDt>
        <NtryDtls><TxDtls>
          <RltdPties><Cdtr><Pty><Nm>Belastingdienst</Nm></Pty></Cdtr></RltdPties>
          <RmtInf><Ustrd>Payroll tax January 2026</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
    <Stmt>
      <Bal><Tp><CdOrPrtry><Cd>OPBD</Cd></CdOrPrtry></Tp>
        <Amt Ccy="EUR">249.50</Amt><CdtDbtInd>DBIT</CdtDbtInd><Dt><Dt>2026-02-01</Dt></Dt></Bal>
      <Ntry>
        <Amt Ccy="EUR">49.50</Amt><CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><DtTm>2026-02-27T10:00:00</DtTm></BookgDt>
        <AddtlNtryInf>Account and payment fees</AddtlNtryInf>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>"""

# Older camt.053.001.02 style: party name directly under Dbtr, no Pty wrapper.
CAMT_V02 = b"""<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt><Stmt>
  <Ntry><Amt Ccy="EUR">10.00</Amt><CdtDbtInd>CRDT</CdtDbtInd><BookgDt><Dt>2025-12-01</Dt></BookgDt>
    <NtryDtls><TxDtls><RltdPties><Dbtr><Nm>Old Format B.V.</Nm></Dbtr></RltdPties>
    </TxDtls></NtryDtls>
  </Ntry>
</Stmt></BkToCstmrStmt></Document>"""


def test_camt053_signs_parties_and_running_balance() -> None:
    tx = parse_camt053(CAMT_V08)
    assert [t.amount for t in tx] == [Decimal("250.50"), Decimal("-1500.00"), Decimal("-49.50")]
    assert tx[0].counterparty_name == "Klant Een B.V."
    assert tx[0].counterparty_iban == "NL91DEMO0417164300"
    assert tx[0].description == "Payment invoice INV-1"
    assert tx[1].counterparty_name == "Belastingdienst" and tx[1].counterparty_iban is None
    assert [t.balance_after for t in tx] == [
        Decimal("1250.50"),
        Decimal("-249.50"),
        Decimal("-299.00"),
    ]
    assert tx[2].booked_on == date(2026, 2, 27)
    assert tx[2].description == "Account and payment fees"


def test_camt053_older_version_without_balances() -> None:
    [t] = parse_camt053(CAMT_V02)
    assert t.counterparty_name == "Old Format B.V." and t.balance_after is None


def test_camt053_rejects_non_statement_xml() -> None:
    with pytest.raises(StatementError):
        parse_camt053(b"<?xml version='1.0'?><Invoice/>")
    with pytest.raises(StatementError):
        parse_camt053(b"<not-closed>")


def test_csv_with_comma_delimiter_and_optional_balance() -> None:
    data = (
        b"date,amount,counterparty_name,counterparty_iban,description,balance\n"
        b"2026-01-05,250.50,Klant Een B.V.,NL91 DEMO 0417 1643 00,Invoice 1,1250.50\n"
        b"2026-01-28,-1500.00,Belastingdienst,,Payroll tax,\n"
    )
    tx = parse_csv(data)
    assert tx[0].counterparty_iban == "NL91DEMO0417164300"
    assert tx[0].balance_after == Decimal("1250.50")
    assert tx[1].amount == Decimal("-1500.00") and tx[1].balance_after is None
    assert tx[1].counterparty_iban is None


def test_csv_semicolon_dutch_formats() -> None:
    data = (
        "﻿Date;Amount;Counterparty name;Counterparty IBAN;Description\n"
        "05-01-2026;1.234,56;Klant;;Factuur\n"
        "06-01-2026;-99,95;Leverancier;;Inkoop\n"
    ).encode()
    tx = parse_csv(data)
    assert [t.amount for t in tx] == [Decimal("1234.56"), Decimal("-99.95")]
    assert tx[0].booked_on == date(2026, 1, 5)


def test_csv_missing_columns() -> None:
    with pytest.raises(StatementError, match="missing columns"):
        parse_csv(b"date,amount\n2026-01-01,1\n")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1234.56", "1234.56"),
        ("-1,234.56", "-1234.56"),
        ("1.234,56", "1234.56"),
        ("(12,345.00)", "-12345.00"),
        ("€ 99,50", "99.50"),
    ],  # fmt: skip
)
def test_parse_amount(raw: str, expected: str) -> None:
    assert parse_amount(raw) == Decimal(expected)
