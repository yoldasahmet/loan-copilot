from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://loancopilot:loancopilot@localhost:5433/loancopilot"
    data_dir: Path = REPO_ROOT / ".data"
    session_secret: str = "change-me"
    llm_provider: str = "auto"  # auto | anthropic | openai | openrouter
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    llm_model: str = "claude-opus-5-5"
    llm_price_input_per_mtok: float = 4.0
    llm_price_output_per_mtok: float = 20.0
    embeddings_backend: str = "local"
    embedding_model: str = "BAAI/bge-m3"
    rerank: str = "on"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    assumed_interest_rate: float = 0.08
    rate_limit_per_minute: int = 30
    phoenix_collector_endpoint: str = ""

    @field_validator("data_dir")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        # Relative paths in .env are relative to the repo root, not the process cwd.
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
