import uuid

from loancopilot.db import SessionLocal
from loancopilot.embeddings import embed, model_name
from loancopilot.models import Chunk, Document, User
from loancopilot.retrieval import Scope, keyword_query, rrf, search
from tests.factories import new_case

TEXTS = [
    "The average number of employees during 2025 was 31 FTE.",
    "Revenue rose by 12% driven by heat-pump retrofit projects for housing associations.",
    "Lease commitments for premises and vehicles amount to 212,000 euro.",
]


def _add_chunks(case_id: str, texts: list[str], document_id: uuid.UUID | None = None) -> None:
    with SessionLocal() as db:
        for text in texts:
            db.add(Chunk(case_id=case_id, document_id=document_id, kind="text", text=text,
                         context_header="Annual report 2025", page_from=5, page_to=5,
                         embedding=embed([text])[0], embedding_model=model_name()))  # fmt: skip
        db.commit()


def _user(client) -> User:  # noqa: ANN001
    with SessionLocal() as db:
        return db.get_one(User, uuid.UUID(client.get("/api/auth/me").json()["id"]))


def test_rrf_rewards_items_ranked_well_by_both() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = rrf([[a, b, c], [b, c]])
    assert [item for item, _ in fused] == [b, c, a]
    assert fused[0][1] == 1 / 62 + 1 / 61


def test_keyword_query_ors_the_words() -> None:
    assert keyword_query("How many staff, on average?") == "how or many or staff or on or average"


def test_hybrid_and_single_modes_find_the_right_chunk(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    _add_chunks(case_id, TEXTS)
    scope = Scope("case", user=_user(a), case_id=uuid.UUID(case_id))
    with SessionLocal() as db:
        for mode in ("dense", "keyword", "hybrid"):
            hits = search(db, "number of employees FTE", scope, k=2, mode=mode)
            assert "31 FTE" in hits[0].text, mode


def test_retrieval_never_returns_another_advisors_chunks(login) -> None:
    a, b = login("advisor"), login("advisor")
    case_a, case_b = new_case(a, "Alfa B.V.")["id"], new_case(b, "Beta B.V.")["id"]
    _add_chunks(case_a, TEXTS)
    _add_chunks(case_b, [f"Beta secret: {t}" for t in TEXTS])
    user_a = _user(a)
    with SessionLocal() as db:
        own = search(db, "employees lease revenue", Scope("case", user=user_a,
                     case_id=uuid.UUID(case_a)), k=10)  # fmt: skip
        assert own and all("Beta secret" not in h.text for h in own)
        # Asking for B's case as advisor A: the SQL access filter returns nothing.
        foreign = search(db, "employees lease revenue", Scope("case", user=user_a,
                         case_id=uuid.UUID(case_b)), k=10)  # fmt: skip
        assert foreign == []


def test_injection_flagged_documents_are_excluded_until_allowed(login) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    with SessionLocal() as db:
        doc = Document(case_id=case_id, kind="other", filename="contract.pdf", sha256="x" * 64,
                       mime="application/pdf", size_bytes=1, status="indexed",
                       injection_flag=True)  # fmt: skip
        db.add(doc)
        db.commit()
        doc_id = doc.id
    _add_chunks(case_id, ["Framework agreement with the largest client until June 2027."], doc_id)
    scope = Scope("case", user=_user(a), case_id=uuid.UUID(case_id))
    with SessionLocal() as db:
        assert search(db, "framework agreement largest client", scope) == []
        db.get_one(Document, doc_id).injection_allowed = True
        db.commit()
        assert len(search(db, "framework agreement largest client", scope)) == 1
