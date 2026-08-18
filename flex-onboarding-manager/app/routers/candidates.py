"""Endpoints REST para gestionar expedientes de candidatos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db
from app.enums import OnboardingStatus

router = APIRouter(prefix="/candidates", tags=["candidates"])


@router.get("/grouped", response_model=schemas.CandidateGroupedList)
def list_candidates_grouped(
    status_filter: OnboardingStatus | None = Query(default=None, alias="status"),
    city: str | None = Query(default=None),
    zip_code: str | None = Query(default=None, alias="zip"),
    search: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> schemas.CandidateGroupedList:
    """Expedientes agrupados por estación Flex (vista acordeón del panel)."""
    return crud.list_candidates_grouped(
        db,
        status=status_filter,
        city=city,
        zip_code=zip_code,
        search=search,
    )


@router.get("", response_model=schemas.CandidateList)
def list_candidates(
    status_filter: OnboardingStatus | None = Query(default=None, alias="status"),
    city: str | None = Query(default=None),
    zip_code: str | None = Query(default=None, alias="zip"),
    search: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> schemas.CandidateList:
    total, items = crud.list_candidates(
        db,
        status=status_filter,
        city=city,
        zip_code=zip_code,
        search=search,
        skip=skip,
        limit=limit,
    )
    return schemas.CandidateList(total=total, items=items)


@router.post("", response_model=schemas.CandidateDetail, status_code=status.HTTP_201_CREATED)
def create_candidate(
    data: schemas.CandidateCreate, db: Session = Depends(get_db)
) -> schemas.CandidateDetail:
    if crud.get_candidate_by_email(db, str(data.assigned_email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un expediente con ese email asignado.",
        )
    try:
        candidate = crud.create_candidate(db, data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un expediente con ese email asignado.",
        )
    return candidate


@router.post("/import", response_model=schemas.CandidateImportResult)
async def import_candidates_csv(
    file: UploadFile = File(...),
    seed_checklist: bool = Query(default=True),
    actor: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> schemas.CandidateImportResult:
    """Importa candidatos desde un archivo CSV.

    Columnas soportadas (cabecera flexible):
    full_name, assigned_email (o email), zip_code (o zip), phone, region, notes,
    mailbox_password (o password). Las filas con email duplicado se omiten.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sube un archivo .csv con cabecera.",
        )
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")
    return crud.import_candidates_from_csv(
        db, content, seed_checklist=seed_checklist, actor=actor
    )


@router.post("/batch/dispatch-flex", response_model=schemas.FlexJobEnqueueResult, status_code=202)
def batch_dispatch_flex(
    data: schemas.BatchFlexDispatch,
    db: Session = Depends(get_db),
) -> schemas.FlexJobEnqueueResult:
    """Encola Sembrar (async). Poll GET /api/jobs/{job_id} hasta completed/failed."""
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


@router.get("/{candidate_id}", response_model=schemas.CandidateDetail)
def get_candidate(candidate_id: int, db: Session = Depends(get_db)) -> schemas.CandidateDetail:
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    return candidate


@router.patch("/{candidate_id}", response_model=schemas.CandidateDetail)
def update_candidate(
    candidate_id: int, data: schemas.CandidateUpdate, db: Session = Depends(get_db)
) -> schemas.CandidateDetail:
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    try:
        return crud.update_candidate(db, candidate, data)
    except crud.SiembraCredentialsLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un expediente con ese email asignado.",
        )


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(candidate_id: int, db: Session = Depends(get_db)) -> None:
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    crud.delete_candidate(db, candidate)


@router.post("/{candidate_id}/status", response_model=schemas.CandidateDetail)
def change_status(
    candidate_id: int, change: schemas.StatusChange, db: Session = Depends(get_db)
) -> schemas.CandidateDetail:
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    return crud.change_status(db, candidate, change)


@router.post("/{candidate_id}/notes", response_model=schemas.TimelineEventOut, status_code=201)
def add_note(
    candidate_id: int, note: schemas.NoteCreate, db: Session = Depends(get_db)
) -> schemas.TimelineEventOut:
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    return crud.add_note(db, candidate, note)


@router.post("/{candidate_id}/handoff", response_model=schemas.CandidateDetail)
def mark_handoff(
    candidate_id: int, data: schemas.HandoffUpdate, db: Session = Depends(get_db)
) -> schemas.CandidateDetail:
    """Marca el expediente como handoff completado (vinculado al sistema de monitoreo).

    NOTA: esto NO integra nada automáticamente. Solo registra que el traspaso se
    hizo manualmente y guarda una referencia externa opcional.
    """
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    if not candidate.handoff_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El expediente aún no está listo para handoff (no está en approved_active).",
        )
    return crud.mark_handoff_done(db, candidate, data)


@router.put("/{candidate_id}/mailbox-credential", response_model=schemas.CandidateDetail)
def set_mailbox_credential(
    candidate_id: int, data: schemas.MailboxCredentialSet, db: Session = Depends(get_db)
) -> schemas.CandidateDetail:
    """Guarda (cifrada) la contraseña del buzón administrado del conductor.

    Uso legítimo: credencial de un buzón que TU organización administra para una
    persona real. Se cifra en reposo; nunca se devuelve en el detalle normal.
    """
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    try:
        return crud.set_mailbox_credential(db, candidate, data)
    except crud.SiembraCredentialsLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{candidate_id}/mailbox-credential", response_model=schemas.MailboxCredentialReveal)
def reveal_mailbox_credential(
    candidate_id: int, actor: str | None = Query(default=None), db: Session = Depends(get_db)
) -> schemas.MailboxCredentialReveal:
    """Revela (descifra) la contraseña bajo demanda. El acceso queda auditado."""
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    if not candidate.has_mailbox_credential:
        raise HTTPException(status_code=404, detail="Este expediente no tiene credencial guardada.")
    password = crud.reveal_mailbox_credential(db, candidate, actor=actor)
    if password is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No se pudo descifrar la credencial (CRED_KEY incorrecta o dato corrupto).",
        )
    return schemas.MailboxCredentialReveal(assigned_email=candidate.assigned_email, password=password)


@router.delete("/{candidate_id}/mailbox-credential", response_model=schemas.CandidateDetail)
def clear_mailbox_credential(
    candidate_id: int, actor: str | None = Query(default=None), db: Session = Depends(get_db)
) -> schemas.CandidateDetail:
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    return crud.clear_mailbox_credential(db, candidate, actor=actor)


@router.get("/{candidate_id}/timeline", response_model=list[schemas.TimelineEventOut])
def get_timeline(
    candidate_id: int, db: Session = Depends(get_db)
) -> list[schemas.TimelineEventOut]:
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    return crud.list_timeline(db, candidate_id)


# --------------------------------------------------------------------------- #
# Checklist anidado bajo el candidato
# --------------------------------------------------------------------------- #
@router.post(
    "/{candidate_id}/checklist",
    response_model=schemas.ChecklistItemOut,
    status_code=status.HTTP_201_CREATED,
)
def add_checklist_item(
    candidate_id: int,
    data: schemas.ChecklistItemCreate,
    db: Session = Depends(get_db),
) -> schemas.ChecklistItemOut:
    candidate = crud.get_candidate(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    return crud.add_checklist_item(db, candidate, data)
