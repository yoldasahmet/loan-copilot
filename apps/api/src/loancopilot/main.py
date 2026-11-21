import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from loancopilot import embeddings, rerank
from loancopilot.config import get_settings
from loancopilot.routes import admin, analysis, auth, cases, chat, documents, matching


def _warm_models() -> None:
    """Load the local embedding and reranker models once, so the first request is not slow."""
    embeddings.embed(["warm-up"])
    if rerank.enabled():
        rerank.rerank("warm-up", ["x"], ["x"], 1)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if get_settings().embeddings_backend != "fake":
        threading.Thread(target=_warm_models, daemon=True).start()
    yield


app = FastAPI(
    title="SME Loan Copilot API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    max_body_size=21 * 1024 * 1024,  # uploads are capped at 20 MB in security.check_upload
)

api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (auth, cases, documents, analysis, chat, matching, admin):
    api.include_router(module.router)

app.include_router(api)
