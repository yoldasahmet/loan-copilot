from fastapi import APIRouter, FastAPI

from loancopilot.routes import admin, analysis, auth, cases, documents

app = FastAPI(
    title="SME Loan Copilot API",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    max_body_size=21 * 1024 * 1024,  # uploads are capped at 20 MB in security.check_upload
)

api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


for module in (auth, cases, documents, analysis, admin):
    api.include_router(module.router)

app.include_router(api)
