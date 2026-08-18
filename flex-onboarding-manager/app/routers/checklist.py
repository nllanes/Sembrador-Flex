"""Endpoints REST para ítems de checklist individuales."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/checklist-items", tags=["checklist"])


@router.patch("/{item_id}", response_model=schemas.ChecklistItemOut)
def update_item(
    item_id: int, data: schemas.ChecklistItemUpdate, db: Session = Depends(get_db)
) -> schemas.ChecklistItemOut:
    item = crud.get_checklist_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Ítem de checklist no encontrado.")
    return crud.update_checklist_item(db, item, data)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_db)) -> None:
    item = crud.get_checklist_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Ítem de checklist no encontrado.")
    crud.delete_checklist_item(db, item)
