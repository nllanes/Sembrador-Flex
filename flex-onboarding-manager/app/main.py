"""Punto de entrada de la aplicación FastAPI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.config import get_settings
from app.routers import candidates, checklist, flex_regions, meta

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """En desarrollo con SQLite, crea tablas y datos de ejemplo si no existen."""
    if settings.database_url.startswith("sqlite"):
        from app.database import Base, SessionLocal, engine
        from app import models  # noqa: F401

        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        try:
            from app import crud

            crud.seed_flex_regions(db)
        finally:
            db.close()
    from app.worker_embedded import start_embedded_worker

    start_embedded_worker()
    yield


app = FastAPI(
    title=settings.app_title,
    version=__version__,
    lifespan=lifespan,
    description=(
        "CRM de expedientes de onboarding para conductores Amazon Flex. "
        "Sembrar encola jobs async (cuenta Amazon + región); docs personales aparte."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas de la API bajo el prefijo configurado (por defecto /api).
from app.routers import jobs  # noqa: E402

app.include_router(candidates.router, prefix=settings.api_prefix)
app.include_router(checklist.router, prefix=settings.api_prefix)
app.include_router(flex_regions.router, prefix=settings.api_prefix)
app.include_router(meta.router, prefix=settings.api_prefix)
app.include_router(jobs.router, prefix=settings.api_prefix)


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


# --------------------------------------------------------------------------- #
# Panel web estático
# --------------------------------------------------------------------------- #
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(str(STATIC_DIR / "index.html"))
