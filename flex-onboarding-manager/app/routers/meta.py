"""Endpoints de metadatos: catálogo de estados y resumen para el dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.enums import (
    ACCOUNT_CREATION_STATUSES,
    STATUS_ORDER,
    TERMINAL_STATUSES,
    ChecklistStatus,
    OnboardingStatus,
)

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/statuses")
def get_statuses() -> dict:
    """Devuelve el catálogo de estados de onboarding (orden de flujo + terminales)."""
    return {
        "flow": [s.value for s in STATUS_ORDER],
        "terminal": [s.value for s in TERMINAL_STATUSES],
        "all": [s.value for s in OnboardingStatus],
        "checklist_statuses": [s.value for s in ChecklistStatus],
        "account_creation_statuses": [s.value for s in ACCOUNT_CREATION_STATUSES],
    }


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)) -> dict:
    """Conteo de expedientes por estado (para el panel/dashboard)."""
    return {"by_status": crud.status_summary(db)}


@router.get("/zip-stats", response_model=schemas.ZipStatsList)
def get_zip_stats(db: Session = Depends(get_db)) -> schemas.ZipStatsList:
    """Métricas de conversión por ZIP code: total, aplicados, con respuesta y activos."""
    return schemas.ZipStatsList(zones=crud.zip_stats(db))


@router.get("/location-stats", response_model=schemas.LocationStats)
def get_location_stats(db: Session = Depends(get_db)) -> schemas.LocationStats:
    """Totales por ciudad y por ZIP code (con desglose ciudad → ZIP)."""
    return schemas.LocationStats(**crud.location_stats(db))


@router.get("/locations-by-status", response_model=schemas.LocationsByStatus)
def get_locations_by_status(
    status: OnboardingStatus = Query(..., description="Estado de onboarding a consultar"),
    db: Session = Depends(get_db),
) -> schemas.LocationsByStatus:
    """Regiones y localizaciones para un estado: dónde hay candidatos y dónde se puede crear cuenta Flex."""
    return schemas.LocationsByStatus(**crud.locations_by_status(db, status))


@router.get("/flex-eligibility", response_model=schemas.ZipFlexLookup)
def get_flex_eligibility_by_zip(
    zip: str = Query(..., min_length=3, max_length=20, description="ZIP code a consultar"),
    db: Session = Depends(get_db),
) -> schemas.ZipFlexLookup:
    """Consulta un ZIP en el catálogo Flex local. NO consulta Amazon."""
    return schemas.ZipFlexLookup(**crud.flex_eligibility_by_zip(db, zip))


@router.get("/us-states")
def get_us_states() -> dict:
    """Catálogo de estados US para filtros del panel (nombre + código)."""
    from app import flex_stations

    return {"states": flex_stations.list_us_states()}


@router.get("/station-index")
def get_station_index() -> dict:
    """Índice código de estación → estado US (agrupación de siembras por estado)."""
    from app import flex_stations

    return {"index": flex_stations.station_code_index()}


@router.get("/flex-stations", response_model=schemas.FlexStationSearchResult)
def search_flex_stations(
    state: str | None = Query(default=None, max_length=10, description="Estado US, ej. FL"),
    city: str | None = Query(default=None, max_length=120),
    zip: str | None = Query(default=None, max_length=20, alias="zip"),
) -> schemas.FlexStationSearchResult:
    """Estaciones Amazon Flex del catálogo monitor_saas filtradas por estado/ciudad/ZIP."""
    from app import flex_stations

    return schemas.FlexStationSearchResult(
        **flex_stations.search_flex_stations(state=state, city=city, zip_code=zip)
    )


@router.get("/appium-status")
def get_appium_status() -> dict:
    """Estado de Appium (región Flex en app Android)."""
    from app.config import get_settings
    from app.flex_apply.appium_region import appium_healthcheck

    settings = get_settings()
    health = appium_healthcheck()
    return {
        **health,
        "creation_enabled": settings.flex_creation_enabled,
        "vehicle_type": settings.flex_default_vehicle_type,
        "docs": "/docs — ver docs/flex_apply.md",
    }
