"""Endpoints del catálogo de regiones donde Flex acepta cuentas."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/flex-regions", tags=["flex-regions"])


@router.get("", response_model=list[schemas.FlexRegionOut])
def list_regions(
    active_only: bool = False,
    db: Session = Depends(get_db),
) -> list[schemas.FlexRegionOut]:
    return crud.list_flex_regions(db, active_only=active_only)


@router.post("", response_model=schemas.FlexRegionOut, status_code=status.HTTP_201_CREATED)
def create_region(
    data: schemas.FlexRegionCreate,
    db: Session = Depends(get_db),
) -> schemas.FlexRegionOut:
    return crud.create_flex_region(db, data)
