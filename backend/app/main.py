"""Vembanad Water Quality API — FastAPI backend over the pipeline products.

Read-only: serves cached GeoTIFF-derived overlays + precomputed stats JSON.
Heavy rendering happens once via `python -m app.services.overlays --build-all`
(run from backend/); requests only serve static files + small JSON.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .core import config
from .routers import compare, health, legend, overlays, seasons, windows


def create_app() -> FastAPI:
    app = FastAPI(title="Vembanad Water Quality API",
                  description="Satellite-derived water-quality proxies for Vembanad backwater",
                  version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS + ["*"],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api", tags=["health"])
    app.include_router(windows.router, prefix="/api", tags=["windows"])
    app.include_router(overlays.router, prefix="/api", tags=["overlays"])
    app.include_router(seasons.router, prefix="/api", tags=["seasons"])
    app.include_router(compare.router, prefix="/api", tags=["compare"])
    app.include_router(legend.router, prefix="/api", tags=["legend"])

    # Production: serve the built frontend (frontend/dist) if present
    dist = config.PROJECT_ROOT / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:
        @app.get("/")
        def _root():
            return {"service": "vembanad-water-quality-api",
                    "docs": "/docs", "health": "/api/health"}

    return app


app = create_app()
