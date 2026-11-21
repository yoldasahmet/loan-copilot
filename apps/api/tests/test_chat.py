import json

from sqlalchemy import select

from loancopilot.config import get_settings
from loancopilot.db import SessionLocal
from loancopilot.models import AiRun, ChatMessage
from tests.factories import new_case
from tests.test_retrieval import TEXTS, _add_chunks


def _events(response) -> list[tuple[str, object]]:  # noqa: ANN001
    out = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_chat_streams_tokens_then_sources_and_restores_placeholders(login, fake_llm) -> None:
    a = login("advisor")
    case_id = new_case(a, "Laumond Installatie B.V.")["id"]
    _add_chunks(case_id, TEXTS)
    fake_llm.queue_stream(["[COM", "PANY] employed 31 FTE on average [S1]."])
    response = a.post(f"/api/cases/{case_id}/chat", json={"message": "How many employees?"})
    assert response.status_code == 200
    events = _events(response)
    assert [e for e, _ in events][-2:] == ["sources", "done"]
    text = "".join(d["text"] for e, d in events if e == "token")
    assert text == "Laumond Installatie B.V. employed 31 FTE on average [S1]."
    sources = next(d for e, d in events if e == "sources")
    assert sources[0]["id"] == "S1" and sources[0]["page_from"] == 5
    sent = fake_llm.requests[-1]
    assert '<source id="S1"' in sent.user and "Laumond" not in sent.user
    with SessionLocal() as db:
        roles = [m.role for m in db.scalars(select(ChatMessage).order_by(ChatMessage.created_at))]
        assert roles == ["user", "assistant"]
        run = db.scalar(select(AiRun).where(AiRun.kind == "chat"))
        assert run.prompt_version == "chat-v1" and len(run.source_ids) == len(sources)
        assert "Laumond" in run.output_text  # stored after restoring placeholders
    history = a.get(f"/api/cases/{case_id}/chat").json()
    assert history[1]["sources"][0]["id"] == "S1"


def test_cant_find_without_documents_skips_the_llm(login, fake_llm) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    events = _events(a.post(f"/api/cases/{case_id}/chat", json={"message": "Any patents?"}))
    assert "".join(d["text"] for e, d in events if e == "token") == (
        "I can't find this in the case documents."
    )
    assert next(d for e, d in events if e == "sources") == []
    assert fake_llm.requests == []


def test_follow_up_question_is_rewritten_first(login, fake_llm) -> None:
    a = login("advisor")
    case_id = new_case(a)["id"]
    _add_chunks(case_id, TEXTS)
    fake_llm.queue_stream(["31 FTE [S1]."])
    a.post(f"/api/cases/{case_id}/chat", json={"message": "How many employees?"})
    fake_llm.queue("average number of employees 2024")
    fake_llm.queue_stream(["27 FTE [S1]."])
    a.post(f"/api/cases/{case_id}/chat", json={"message": "And the year before?"})
    rewrite = fake_llm.requests[1]
    assert "Latest question: And the year before?" in rewrite.user
    with SessionLocal() as db:
        kinds = [r.kind for r in db.scalars(select(AiRun).order_by(AiRun.created_at))]
    assert kinds == ["chat", "query_rewrite", "chat"]


def test_rate_limit_returns_429(login, fake_llm, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 1)
    a = login("advisor")
    case_id = new_case(a)["id"]
    _add_chunks(case_id, TEXTS)
    fake_llm.queue_stream(["ok [S1]."])
    assert a.post(f"/api/cases/{case_id}/chat", json={"message": "Employees?"}).status_code == 200
    second = a.post(f"/api/cases/{case_id}/chat", json={"message": "Revenue?"})
    assert second.status_code == 429 and "Rate limit" in second.json()["detail"]


def test_chat_on_another_advisors_case_is_404(login) -> None:
    a, b = login("advisor"), login("advisor")
    case_id = new_case(a)["id"]
    assert b.post(f"/api/cases/{case_id}/chat", json={"message": "hi"}).status_code == 404
    assert b.get(f"/api/cases/{case_id}/chat").status_code == 404
