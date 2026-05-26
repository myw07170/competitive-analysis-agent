"""FastAPI entrypoint.

Usage:
    python main.py                  # uses .env settings
    uvicorn main:app --reload       # dev mode
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import analysis as analysis_api
from app.api import reports as reports_api
from app.api import traces as traces_api
from app.config import get_settings
from app.storage import get_store


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Competitive Analysis Agent API",
        version=__version__,
        description=(
            "Multi-agent competitive-product analysis API. Drives the Collector / "
            "Analyst / Writer / QC agents through a LangGraph DAG and streams "
            "per-agent trace events over SSE."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    app.include_router(analysis_api.router)
    app.include_router(reports_api.router)
    app.include_router(traces_api.router)

    @app.on_event("startup")
    async def _startup() -> None:
        await get_store().init()

    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "mock_mode": settings.use_mock_llm,
            "search_provider": settings.search_provider,
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("main:app", host=s.host, port=s.port, reload=False, log_level=s.log_level.lower())
