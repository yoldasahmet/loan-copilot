import pytest

from loancopilot import llm
from loancopilot.config import get_settings
from loancopilot.llm import LlmError, Request

REQ = Request("system text", "user text", 1000, "medium", {"type": "object", "properties": {}})


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    s = get_settings()
    for field in ("anthropic_api_key", "openai_api_key", "openrouter_api_key"):
        monkeypatch.setattr(s, field, "")
    monkeypatch.setattr(s, "llm_provider", "auto")
    monkeypatch.setattr(s, "llm_model", "claude-opus-5-5")
    llm._openai_client.cache_clear()
    return s


def test_auto_picks_the_first_configured_key(settings, monkeypatch) -> None:  # noqa: ANN001
    assert llm.provider() == "anthropic"  # default (may use an `ant auth login` profile)
    monkeypatch.setattr(settings, "openrouter_api_key", "or-key")
    assert llm.provider() == "openrouter"
    monkeypatch.setattr(settings, "openai_api_key", "oa-key")
    assert llm.provider() == "openai"
    monkeypatch.setattr(settings, "anthropic_api_key", "an-key")
    assert llm.provider() == "anthropic"
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    assert llm.provider() == "openrouter"
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    with pytest.raises(LlmError, match="LLM_PROVIDER"):
        llm.provider()


def test_model_id_must_match_the_provider(settings, monkeypatch) -> None:  # noqa: ANN001
    with pytest.raises(LlmError, match="OpenAI model id"):
        llm.openai_kwargs(REQ, "openai")
    with pytest.raises(LlmError, match="provider/model"):
        llm.openai_kwargs(REQ, "openrouter")
    monkeypatch.setattr(settings, "llm_model", "vendor/some-model")
    assert llm.openai_kwargs(REQ, "openrouter")["model"] == "vendor/some-model"


def test_request_shapes(settings, monkeypatch) -> None:  # noqa: ANN001
    a = llm.anthropic_kwargs(REQ)
    assert a["system"] == "system text" and a["messages"] == [
        {"role": "user", "content": "user text"}
    ]
    assert a["output_config"]["format"]["type"] == "json_schema" and a["fallbacks"] == "default"
    monkeypatch.setattr(settings, "llm_model", "some-openai-model")
    o = llm.openai_kwargs(REQ, "openai")
    assert [m["role"] for m in o["messages"]] == ["system", "user"]
    assert o["max_completion_tokens"] == 1000
    assert o["response_format"]["json_schema"]["strict"] is True
    assert "response_format" not in llm.openai_kwargs(Request("s", "u", 10, "low", None), "openai")


def test_missing_key_gives_a_clear_error(settings, monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_model", "some-openai-model")
    with pytest.raises(LlmError, match="AI is not configured"):
        llm.complete(kind="chat", prompt=llm.load_prompt("extraction"), user_content="hi")
