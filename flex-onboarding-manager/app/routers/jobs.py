"""API de jobs asíncronos de Sembrar (cola cloud-ready)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/flex-dispatch", response_model=schemas.FlexJobEnqueueResult, status_code=202)
def enqueue_flex_dispatch(
    data: schemas.FlexJobEnqueue,
    db: Session = Depends(get_db),
) -> schemas.FlexJobEnqueueResult:
    """Encola Sembrar. El worker procesa el job; haz poll en GET /jobs/{id}."""
    job = crud.enqueue_flex_dispatch_job(
        db, candidate_ids=data.candidate_ids, actor=data.actor
    )
    return schemas.FlexJobEnqueueResult(
        job_id=job.id,
        status=job.status.value,
        candidate_count=len(job.candidate_ids or []),
        message=job.message or "En cola",
        poll_url=f"/api/jobs/{job.id}",
    )


@router.get("/{job_id}", response_model=schemas.FlexJobOut)
def get_job(job_id: str, db: Session = Depends(get_db)) -> schemas.FlexJobOut:
    job = crud.get_flex_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado.")
    return crud.flex_job_to_schema(job)
