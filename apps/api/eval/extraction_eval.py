"""Extraction: field-level accuracy (within 0.5%) on the extraction PDFs and the share of
reports that raised validation warnings.

The PDFs go through the real upload, ingestion and extraction code inside a temporary case,
which is erased afterwards through the normal delete path.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from eval.common import Result, admin, share
from loancopilot.extraction import FIELDS, extract_report
from loancopilot.ingest import ingest_document
from loancopilot.models import Case, Company, Document
from loancopilot.routes.cases import delete_case
from loancopilot.routes.documents import store_document

TOLERANCE = Decimal("0.005")


def correct(extracted: Decimal | None, truth: float | int) -> bool:
    if extracted is None:
        return False
    expected = Decimal(str(truth))
    return abs(extracted - expected) <= abs(expected) * TOLERANCE


def run(db: Session, folder: Path) -> Result:
    truth = json.loads((folder / "truth.json").read_text())
    user = admin(db)
    company = Company(name="Extraction evaluation", legal_form="bv")
    db.add(company)
    db.flush()
    case = Case(company_id=company.id, advisor_id=user.id, loan_amount=Decimal(100_000),
                loan_purpose="other", loan_term_months=12, applied_on=date.today())  # fmt: skip
    db.add(case)
    db.commit()
    reports = []
    try:
        for filename, expected in truth.items():
            doc, _ = store_document(db, upload_name=filename, data=(folder / filename).read_bytes(),
                                    kind="annual_report", year=expected["year"],
                                    case_id=case.id)  # fmt: skip
            ingest_document(doc.id)
            db.refresh(doc)
            if doc.status != "indexed":
                reports.append({"report": filename, "layout": expected["layout"],
                                "error": doc.error, "fields": {}, "warnings": []})  # fmt: skip
                continue
            row = extract_report(db, db.get_one(Document, doc.id))
            db.commit()
            fields = {f: correct(getattr(row, f), expected["figures"][f]) for f in FIELDS}
            reports.append({"report": filename, "layout": expected["layout"], "error": None,
                            "fields": fields, "warnings": row.warnings})  # fmt: skip
    finally:
        delete_case(case.id, db, user)
    checked = [r for r in reports if r["error"] is None]
    layouts = sorted({r["layout"] for r in reports})

    def accuracy(rows: list[dict]) -> float | None:
        values = [ok for r in rows for ok in r["fields"].values()]
        return share(sum(values), len(values))

    return {
        "reports": len(reports), "failed": len(reports) - len(checked),
        "field_accuracy": accuracy(checked),
        "by_layout": {layout: accuracy([r for r in checked if r["layout"] == layout])
                      for layout in layouts},
        "with_warnings": share(sum(bool(r["warnings"]) for r in checked), len(checked)),
        "rows": reports,
    }  # fmt: skip
