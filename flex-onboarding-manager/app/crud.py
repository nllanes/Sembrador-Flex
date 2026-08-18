"""Operaciones de acceso a datos y lógica de negocio del onboarding.

Toda mutación relevante (creación, cambio de estado, checklist, handoff) deja
un rastro en la línea de tiempo (TimelineEvent) para tener trazabilidad completa.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from collections import defaultdict
from collections.abc import Callable
from email.utils import parseaddr

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.enums import (
    ACCOUNT_CREATION_STATUSES,
    DEFAULT_CHECKLIST_TEMPLATE,
    FLEX_DISPATCH_ELIGIBLE,
    EventType,
    OnboardingStatus,
)

logger = logging.getLogger(__name__)


class SiembraCredentialsLockedError(ValueError):
    """La siembra ya fue enviada a creación Amazon; no se editan credenciales."""


def _ensure_siembra_credentials_editable(candidate: models.Candidate) -> None:
    if candidate.status not in FLEX_DISPATCH_ELIGIBLE:
        raise SiembraCredentialsLockedError(
            "Solo puedes editar email y contraseña antes de crear la cuenta en Amazon "
            f"(estado actual: {candidate.status.value})."
        )
def _log_event(
    db: Session,
    candidate: models.Candidate,
    event_type: EventType,
    message: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    actor: str | None = None,
) -> models.TimelineEvent:
    """Crea y persiste un evento en la línea de tiempo del expediente."""
    event = models.TimelineEvent(
        candidate_id=candidate.id,
        event_type=event_type,
        message=message,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
    )
    db.add(event)
    return event


# --------------------------------------------------------------------------- #
# Candidatos
# --------------------------------------------------------------------------- #
def get_candidate(db: Session, candidate_id: int) -> models.Candidate | None:
    return db.get(models.Candidate, candidate_id)


def get_candidate_by_email(db: Session, email: str) -> models.Candidate | None:
    stmt = select(models.Candidate).where(models.Candidate.assigned_email == email)
    return db.scalar(stmt)


def list_candidates(
    db: Session,
    *,
    status: OnboardingStatus | None = None,
    city: str | None = None,
    zip_code: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> tuple[int, list[models.Candidate]]:
    stmt = select(models.Candidate)
    count_stmt = select(func.count()).select_from(models.Candidate)

    if status is not None:
        stmt = stmt.where(models.Candidate.status == status)
        count_stmt = count_stmt.where(models.Candidate.status == status)

    if city:
        if city == "(Sin ciudad)":
            no_city = (models.Candidate.region.is_(None)) | (models.Candidate.region == "")
            stmt = stmt.where(no_city)
            count_stmt = count_stmt.where(no_city)
        else:
            stmt = stmt.where(models.Candidate.region == city)
            count_stmt = count_stmt.where(models.Candidate.region == city)

    if zip_code:
        if zip_code == "(Sin ZIP)":
            no_zip = (models.Candidate.zip_code.is_(None)) | (models.Candidate.zip_code == "")
            stmt = stmt.where(no_zip)
            count_stmt = count_stmt.where(no_zip)
        else:
            stmt = stmt.where(models.Candidate.zip_code == zip_code)
            count_stmt = count_stmt.where(models.Candidate.zip_code == zip_code)

    if search:
        like = f"%{search.lower()}%"
        condition = func.lower(models.Candidate.full_name).like(like) | func.lower(
            models.Candidate.assigned_email
        ).like(like)
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.scalar(count_stmt) or 0
    stmt = stmt.order_by(models.Candidate.created_at.desc()).offset(skip).limit(limit)
    items = list(db.scalars(stmt).all())
    return total, items


_STATION_FROM_NAME = re.compile(r"^([A-Z0-9]{2,12})\s·")
_STATION_FROM_NOTES = re.compile(r"Estación:\s*([A-Z0-9]{2,12})")
_UNASSIGNED_STATION = "__none__"


def resolve_station_code(candidate: models.Candidate) -> str | None:
    """Infiere código de estación desde full_name o notes (cuentas auto-generadas)."""
    if candidate.full_name:
        match = _STATION_FROM_NAME.match(candidate.full_name.strip())
        if match:
            return match.group(1)
    if candidate.notes:
        match = _STATION_FROM_NOTES.search(candidate.notes)
        if match:
            return match.group(1)
    return None


def _station_group_label(station_code: str, sample_full_name: str | None) -> str:
    if station_code == _UNASSIGNED_STATION:
        return "Sin estación asignada"
    if sample_full_name and " · " in sample_full_name:
        suffix = sample_full_name.split(" · ", 1)[1].strip()
        if suffix:
            return f"{station_code} · {suffix.split(' #')[0]}"
    return station_code


def list_candidates_grouped(
    db: Session,
    *,
    status: OnboardingStatus | None = None,
    city: str | None = None,
    zip_code: str | None = None,
    search: str | None = None,
    limit: int = 2000,
) -> schemas.CandidateGroupedList:
    """Agrupa expedientes por estación Flex con conteos y listas compactas."""
    total, items = list_candidates(
        db,
        status=status,
        city=city,
        zip_code=zip_code,
        search=search,
        skip=0,
        limit=limit,
    )

    buckets: dict[str, list[models.Candidate]] = defaultdict(list)
    labels: dict[str, str] = {}

    for candidate in items:
        code = resolve_station_code(candidate) or _UNASSIGNED_STATION
        buckets[code].append(candidate)
        if code not in labels:
            labels[code] = _station_group_label(code, candidate.full_name)

    groups: list[schemas.CandidateStationGroup] = []
    active_total = 0
    credential_total = 0

    for code, members in buckets.items():
        active = sum(1 for c in members if c.status == OnboardingStatus.APPROVED_ACTIVE)
        with_cred = sum(1 for c in members if c.has_mailbox_credential)
        active_total += active
        credential_total += with_cred
        groups.append(
            schemas.CandidateStationGroup(
                station_code=code,
                station_label=labels[code],
                total=len(members),
                active=active,
                with_credential=with_cred,
                items=members,
            )
        )

    groups.sort(
        key=lambda g: (
            g.station_code == _UNASSIGNED_STATION,
            -g.total,
            g.station_label.lower(),
        )
    )

    return schemas.CandidateGroupedList(
        grand_total=total,
        group_count=len(groups),
        active_total=active_total,
        credential_total=credential_total,
        groups=groups,
    )


_EMAIL_ADAPTER = TypeAdapter(EmailStr)

# Alias de columnas CSV -> campo interno.
_CSV_ALIASES: dict[str, str] = {
    "full_name": "full_name",
    "nombre": "full_name",
    "name": "full_name",
    "assigned_email": "assigned_email",
    "email": "assigned_email",
    "correo": "assigned_email",
    "zip_code": "zip_code",
    "zip": "zip_code",
    "zipcode": "zip_code",
    "phone": "phone",
    "telefono": "phone",
    "region": "region",
    "zona": "region",
    "notes": "notes",
    "notas": "notes",
    "mailbox_password": "mailbox_password",
    "password": "mailbox_password",
    "pass": "mailbox_password",
}


def _normalize_csv_row(raw: dict[str, str | None]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in raw.items():
        if key is None:
            continue
        field = _CSV_ALIASES.get(key.strip().lower())
        if field and value and value.strip():
            normalized[field] = value.strip()
    return normalized


def import_candidates_from_csv(
    db: Session,
    content: str,
    *,
    seed_checklist: bool = True,
    actor: str | None = None,
) -> schemas.CandidateImportResult:
    """Importa candidatos desde CSV (cabecera flexible, ver _CSV_ALIASES)."""
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return schemas.CandidateImportResult(
            created=0,
            skipped=0,
            errors=[schemas.CandidateImportError(line=1, reason="CSV vacío o sin cabecera.")],
        )

    created = skipped = 0
    created_ids: list[int] = []
    errors: list[schemas.CandidateImportError] = []

    for line_no, raw in enumerate(reader, start=2):
        row = _normalize_csv_row(raw)
        email_raw = row.get("assigned_email")
        full_name = row.get("full_name")

        if not full_name or not email_raw:
            errors.append(
                schemas.CandidateImportError(
                    line=line_no,
                    email=email_raw,
                    reason="Faltan columnas obligatorias: full_name y assigned_email (o email).",
                )
            )
            continue

        _, parsed_email = parseaddr(email_raw)
        email = parsed_email or email_raw
        try:
            _EMAIL_ADAPTER.validate_python(email)
        except ValidationError:
            errors.append(
                schemas.CandidateImportError(
                    line=line_no,
                    email=email_raw,
                    reason="Email inválido.",
                )
            )
            continue

        if get_candidate_by_email(db, email):
            skipped += 1
            continue

        data = schemas.CandidateCreate(
            full_name=full_name,
            assigned_email=email,
            phone=row.get("phone"),
            region=row.get("region"),
            zip_code=row.get("zip_code"),
            notes=row.get("notes"),
            seed_checklist=seed_checklist,
        )
        try:
            candidate = create_candidate(db, data)
        except Exception as exc:  # noqa: BLE001 — reportamos la fila, no abortamos el lote
            db.rollback()
            errors.append(
                schemas.CandidateImportError(
                    line=line_no,
                    email=email,
                    reason=str(exc),
                )
            )
            continue

        mailbox_password = row.get("mailbox_password")
        if mailbox_password:
            set_mailbox_credential(
                db,
                candidate,
                schemas.MailboxCredentialSet(password=mailbox_password, actor=actor),
            )

        created += 1
        created_ids.append(candidate.id)

    return schemas.CandidateImportResult(
        created=created,
        skipped=skipped,
        errors=errors,
        created_ids=created_ids,
    )


def create_candidate(db: Session, data: schemas.CandidateCreate) -> models.Candidate:
    candidate = models.Candidate(
        full_name=data.full_name,
        assigned_email=str(data.assigned_email),
        phone=data.phone,
        region=data.region,
        zip_code=data.zip_code,
        notes=data.notes,
        status=OnboardingStatus.NOT_STARTED,
    )
    db.add(candidate)
    db.flush()  # obtener el id

    if data.seed_checklist:
        for position, label in enumerate(DEFAULT_CHECKLIST_TEMPLATE):
            db.add(
                models.ChecklistItem(
                    candidate_id=candidate.id,
                    label=label,
                    position=position,
                )
            )

    _log_event(
        db,
        candidate,
        EventType.CREATED,
        message=f"Expediente creado para {candidate.full_name} ({candidate.assigned_email}).",
        to_status=candidate.status.value,
    )

    db.commit()
    db.refresh(candidate)
    return candidate


def update_candidate(
    db: Session, candidate: models.Candidate, data: schemas.CandidateUpdate
) -> models.Candidate:
    payload = data.model_dump(exclude_unset=True)
    if "assigned_email" in payload and payload["assigned_email"] is not None:
        payload["assigned_email"] = str(payload["assigned_email"])
        if payload["assigned_email"] != candidate.assigned_email:
            _ensure_siembra_credentials_editable(candidate)
            other = get_candidate_by_email(db, payload["assigned_email"])
            if other is not None and other.id != candidate.id:
                raise ValueError("Ya existe un expediente con ese email asignado.")
            old_email = candidate.assigned_email
            candidate.assigned_email = payload["assigned_email"]
            _log_event(
                db,
                candidate,
                EventType.NOTE_ADDED,
                message=(
                    f"Email de siembra actualizado: {old_email} → {candidate.assigned_email}."
                ),
            )
            payload.pop("assigned_email")
    for field, value in payload.items():
        setattr(candidate, field, value)
    db.commit()
    db.refresh(candidate)
    return candidate


def delete_candidate(db: Session, candidate: models.Candidate) -> None:
    db.delete(candidate)
    db.commit()


def change_status(
    db: Session, candidate: models.Candidate, change: schemas.StatusChange
) -> models.Candidate:
    old_status = candidate.status
    new_status = change.status

    if old_status == new_status:
        return candidate

    candidate.status = new_status

    # Automatizar la marca de handoff_ready cuando llega a approved_active.
    if new_status == OnboardingStatus.APPROVED_ACTIVE and not candidate.handoff_ready:
        candidate.handoff_ready = True
        _log_event(
            db,
            candidate,
            EventType.HANDOFF_READY,
            message="El expediente quedó listo para handoff (approved_active).",
            actor=change.actor,
        )

    message = change.message or (
        f"Estado cambiado de '{old_status.value}' a '{new_status.value}'."
    )
    _log_event(
        db,
        candidate,
        EventType.STATUS_CHANGED,
        message=message,
        from_status=old_status.value,
        to_status=new_status.value,
        actor=change.actor,
    )

    db.commit()
    db.refresh(candidate)
    return candidate


def batch_dispatch_flex(
    db: Session,
    *,
    candidate_ids: list[int],
    actor: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> schemas.BatchFlexDispatchResult:
    """Sembrar: cuenta Amazon + apply región/ZIP. Para antes de licencia/docs."""
    from app.enums import FLEX_DISPATCH_ELIGIBLE, FLEX_DISPATCH_TARGET, OnboardingStatus
    from app.flex_apply.service import FlexApplyStatus, attempt_flex_region_apply

    items: list[schemas.BatchFlexDispatchItem] = []
    skipped: list[schemas.BatchFlexDispatchSkip] = []
    seen: set[int] = set()

    def _progress(msg: str) -> None:
        if on_progress:
            try:
                on_progress(msg)
            except Exception:
                logger.exception("on_progress falló")

    for raw_id in candidate_ids:
        if raw_id in seen:
            continue
        seen.add(raw_id)

        candidate = get_candidate(db, raw_id)
        if candidate is None:
            skipped.append(
                schemas.BatchFlexDispatchSkip(id=raw_id, reason="Expediente no encontrado.")
            )
            continue

        email = candidate.assigned_email
        _progress(f"Sembrando {email}…")

        if candidate.status not in FLEX_DISPATCH_ELIGIBLE:
            reason = f"Ya enviado o en proceso ({candidate.status.value})."
            skipped.append(
                schemas.BatchFlexDispatchSkip(
                    id=candidate.id,
                    assigned_email=email,
                    reason=reason,
                )
            )
            _log_event(
                db,
                candidate,
                EventType.NOTE_ADDED,
                message=f"Sembrar omitido: {reason}",
                actor=actor,
            )
            db.commit()
            continue

        if not candidate.has_mailbox_credential:
            reason = "Sin credencial de buzón guardada."
            skipped.append(
                schemas.BatchFlexDispatchSkip(
                    id=candidate.id,
                    assigned_email=email,
                    reason=reason,
                )
            )
            _log_event(
                db,
                candidate,
                EventType.NOTE_ADDED,
                message=f"Sembrar falló: {reason}",
                actor=actor,
            )
            db.commit()
            continue

        password = security.decrypt_secret(candidate.mailbox_password_enc or "")
        if not password:
            reason = (
                "Contraseña ilegible: abre la siembra, vuelve a escribir "
                "la contraseña y pulsa Guardar."
            )
            skipped.append(
                schemas.BatchFlexDispatchSkip(
                    id=candidate.id,
                    assigned_email=email,
                    reason=reason,
                )
            )
            _log_event(
                db,
                candidate,
                EventType.NOTE_ADDED,
                message=f"Sembrar falló: {reason}",
                actor=actor,
            )
            db.commit()
            continue

        from app.flex_creation.service import validate_amazon_password

        weak = validate_amazon_password(password)
        if weak:
            reason = f"Paso 1 bloqueado: {weak}"
            skipped.append(
                schemas.BatchFlexDispatchSkip(
                    id=candidate.id,
                    assigned_email=email,
                    reason=reason,
                )
            )
            _log_event(
                db,
                candidate,
                EventType.NOTE_ADDED,
                message=f"Sembrar falló: {reason}",
                actor=actor,
            )
            db.commit()
            continue

        _progress(f"{email}: Paso 1 Amazon + ZIP/app…")
        logger.info("Sembrar start · id=%s email=%s zip=%s", candidate.id, email, candidate.zip_code)
        outcome = attempt_flex_region_apply(
            email=email,
            password=password,
            full_name=candidate.full_name,
            zip_code=candidate.zip_code,
        )
        logger.info(
            "Sembrar end · id=%s email=%s ok=%s status=%s msg=%s",
            candidate.id,
            email,
            outcome.ok,
            outcome.status.value,
            (outcome.message or "")[:400],
        )

        if not outcome.ok:
            skipped.append(
                schemas.BatchFlexDispatchSkip(
                    id=candidate.id,
                    assigned_email=email,
                    reason=outcome.message,
                    creation_message=outcome.message,
                    flex_outcome=outcome.status.value,
                )
            )
            _log_event(
                db,
                candidate,
                EventType.NOTE_ADDED,
                message=(
                    f"Sembrar falló [{outcome.status.value}]: {outcome.message}"
                ),
                actor=actor,
            )
            db.commit()
            continue

        old_status = candidate.status
        if outcome.status == FlexApplyStatus.NEEDS_VERIFICATION:
            new_status = OnboardingStatus.INVITED
        elif outcome.status == FlexApplyStatus.WAITLISTED:
            new_status = OnboardingStatus.WAITLISTED
        elif outcome.status == FlexApplyStatus.REGION_READY:
            # Región OK; docs los hace otra persona → documents_pending
            new_status = OnboardingStatus.DOCUMENTS_PENDING
        else:
            # identity_ok / needs_app: cuenta lista, región pendiente en app
            new_status = FLEX_DISPATCH_TARGET

        candidate.status = new_status
        zip_note = f" ZIP={outcome.zip_used}" if outcome.zip_used else ""
        event_msg = (
            f"Sembrado Flex [{outcome.status.value}]{zip_note}: {outcome.message} "
            f"({email})."
        )
        _log_event(
            db,
            candidate,
            EventType.STATUS_CHANGED,
            message=event_msg,
            from_status=old_status.value,
            to_status=new_status.value,
            actor=actor,
        )
        items.append(
            schemas.BatchFlexDispatchItem(
                id=candidate.id,
                assigned_email=email,
                previous_status=old_status.value,
                new_status=new_status.value,
                creation_message=outcome.message,
                flex_outcome=outcome.status.value,
                zip_used=outcome.zip_used,
            )
        )
        db.commit()
        db.refresh(candidate)

    return schemas.BatchFlexDispatchResult(
        dispatched=len(items),
        skipped=len(skipped),
        items=items,
        skipped_items=skipped,
    )


def add_note(
    db: Session, candidate: models.Candidate, note: schemas.NoteCreate
) -> models.TimelineEvent:
    event = _log_event(
        db,
        candidate,
        EventType.NOTE_ADDED,
        message=note.message,
        actor=note.actor,
    )
    db.commit()
    db.refresh(event)
    return event


def mark_handoff_done(
    db: Session, candidate: models.Candidate, data: schemas.HandoffUpdate
) -> models.Candidate:
    candidate.handoff_ready = True
    candidate.handoff_done = True
    candidate.external_ref = data.external_ref
    ref_txt = f" (ref externa: {data.external_ref})" if data.external_ref else ""
    _log_event(
        db,
        candidate,
        EventType.HANDOFF_DONE,
        message=f"Handoff completado: expediente vinculado al sistema de monitoreo{ref_txt}.",
        actor=data.actor,
    )
    db.commit()
    db.refresh(candidate)
    return candidate


# --------------------------------------------------------------------------- #
# Credencial de buzón (cifrada en reposo)
# --------------------------------------------------------------------------- #
def set_mailbox_credential(
    db: Session, candidate: models.Candidate, data: schemas.MailboxCredentialSet
) -> models.Candidate:
    _ensure_siembra_credentials_editable(candidate)
    candidate.mailbox_password_enc = security.encrypt_secret(data.password)
    _log_event(
        db,
        candidate,
        EventType.CREDENTIAL_SET,
        message=f"Credencial de buzón guardada (cifrada) para {candidate.assigned_email}.",
        actor=data.actor,
    )
    db.commit()
    db.refresh(candidate)
    return candidate


def reveal_mailbox_credential(
    db: Session, candidate: models.Candidate, actor: str | None = None
) -> str | None:
    """Descifra y devuelve la contraseña. Registra el acceso en el timeline."""
    if candidate.mailbox_password_enc is None:
        return None
    password = security.decrypt_secret(candidate.mailbox_password_enc)
    _log_event(
        db,
        candidate,
        EventType.CREDENTIAL_REVEALED,
        message=f"Credencial de buzón revelada para {candidate.assigned_email}.",
        actor=actor,
    )
    db.commit()
    return password


def clear_mailbox_credential(
    db: Session, candidate: models.Candidate, actor: str | None = None
) -> models.Candidate:
    candidate.mailbox_password_enc = None
    _log_event(
        db,
        candidate,
        EventType.CREDENTIAL_CLEARED,
        message=f"Credencial de buzón eliminada para {candidate.assigned_email}.",
        actor=actor,
    )
    db.commit()
    db.refresh(candidate)
    return candidate


# --------------------------------------------------------------------------- #
# Checklist
# --------------------------------------------------------------------------- #
def get_checklist_item(db: Session, item_id: int) -> models.ChecklistItem | None:
    return db.get(models.ChecklistItem, item_id)


def add_checklist_item(
    db: Session, candidate: models.Candidate, data: schemas.ChecklistItemCreate
) -> models.ChecklistItem:
    item = models.ChecklistItem(
        candidate_id=candidate.id,
        label=data.label,
        status=data.status,
        notes=data.notes,
        position=data.position,
    )
    db.add(item)
    _log_event(
        db,
        candidate,
        EventType.CHECKLIST_UPDATED,
        message=f"Ítem de checklist agregado: '{data.label}'.",
    )
    db.commit()
    db.refresh(item)
    return item


def update_checklist_item(
    db: Session, item: models.ChecklistItem, data: schemas.ChecklistItemUpdate
) -> models.ChecklistItem:
    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(item, field, value)

    candidate = db.get(models.Candidate, item.candidate_id)
    if candidate is not None:
        _log_event(
            db,
            candidate,
            EventType.CHECKLIST_UPDATED,
            message=f"Ítem de checklist actualizado: '{item.label}' → {item.status.value}.",
        )
    db.commit()
    db.refresh(item)
    return item


def delete_checklist_item(db: Session, item: models.ChecklistItem) -> None:
    db.delete(item)
    db.commit()


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
def list_timeline(db: Session, candidate_id: int) -> list[models.TimelineEvent]:
    stmt = (
        select(models.TimelineEvent)
        .where(models.TimelineEvent.candidate_id == candidate_id)
        .order_by(models.TimelineEvent.created_at.desc())
    )
    return list(db.scalars(stmt).all())


# --------------------------------------------------------------------------- #
# Métricas / dashboard
# --------------------------------------------------------------------------- #
def status_summary(db: Session) -> dict[str, int]:
    """Devuelve el conteo de expedientes agrupados por estado."""
    stmt = select(models.Candidate.status, func.count()).group_by(models.Candidate.status)
    result = {status.value: 0 for status in OnboardingStatus}
    for status, count in db.execute(stmt).all():
        key = status.value if hasattr(status, "value") else str(status)
        result[key] = count
    return result


# Estados que consideramos como "hubo respuesta" en el proceso de Amazon.
_RESPONDED_STATUSES = {
    OnboardingStatus.BACKGROUND_CHECK,
    OnboardingStatus.WAITLISTED,
    OnboardingStatus.APPROVED_ACTIVE,
    OnboardingStatus.REJECTED,
}


def zip_stats(db: Session) -> list[dict]:
    """Métricas de conversión por ZIP code / zona.

    Para cada ZIP: cuántos candidatos hay, cuántos iniciaron el proceso
    (aplicaron), cuántos tuvieron respuesta de Amazon, cuántos están activos,
    en lista de espera o rechazados. El proceso real lo ejecuta una persona;
    esto solo agrega los resultados que se van registrando.
    """
    stmt = select(models.Candidate).where(models.Candidate.zip_code.is_not(None))
    candidates = db.scalars(stmt).all()

    buckets: dict[str, dict] = {}
    for c in candidates:
        z = c.zip_code
        b = buckets.setdefault(
            z,
            {
                "zip_code": z,
                "total": 0,
                "applied": 0,
                "responded": 0,
                "active": 0,
                "rejected": 0,
                "waitlisted": 0,
            },
        )
        b["total"] += 1
        if c.status != OnboardingStatus.NOT_STARTED:
            b["applied"] += 1
        if c.status in _RESPONDED_STATUSES:
            b["responded"] += 1
        if c.status == OnboardingStatus.APPROVED_ACTIVE:
            b["active"] += 1
        if c.status == OnboardingStatus.REJECTED:
            b["rejected"] += 1
        if c.status == OnboardingStatus.WAITLISTED:
            b["waitlisted"] += 1

    return sorted(buckets.values(), key=lambda x: x["total"], reverse=True)


def _city_label(region: str | None) -> str:
    value = (region or "").strip()
    return value if value else "(Sin ciudad)"


def _zip_label(zip_code: str | None) -> str:
    value = (zip_code or "").strip()
    return value if value else "(Sin ZIP)"


def location_stats(db: Session) -> dict:
    """Totales por ciudad (region) y por ZIP code, con desglose ciudad → ZIP."""
    candidates = list(db.scalars(select(models.Candidate)).all())

    cities: dict[str, dict] = {}
    zip_totals: dict[str, int] = {}

    for c in candidates:
        city = _city_label(c.region)
        zip_code = _zip_label(c.zip_code)

        cb = cities.setdefault(city, {"city": city, "total": 0, "zip_codes": {}})
        cb["total"] += 1
        cb["zip_codes"][zip_code] = cb["zip_codes"].get(zip_code, 0) + 1

        zip_totals[zip_code] = zip_totals.get(zip_code, 0) + 1

    city_list = []
    for data in sorted(cities.values(), key=lambda x: x["total"], reverse=True):
        zips = [
            {"zip_code": z, "total": n}
            for z, n in sorted(data["zip_codes"].items(), key=lambda x: x[1], reverse=True)
        ]
        city_list.append({"city": data["city"], "total": data["total"], "zip_codes": zips})

    zip_list = [
        {"zip_code": z, "total": n}
        for z, n in sorted(zip_totals.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "grand_total": len(candidates),
        "cities": city_list,
        "zip_codes": zip_list,
    }


def _group_candidates_by_location(candidates: list[models.Candidate]) -> tuple[list[dict], list[dict]]:
    cities: dict[str, dict] = {}
    zip_totals: dict[str, int] = {}

    for c in candidates:
        city = _city_label(c.region)
        zip_code = _zip_label(c.zip_code)
        cb = cities.setdefault(city, {"city": city, "total": 0, "zip_codes": {}})
        cb["total"] += 1
        cb["zip_codes"][zip_code] = cb["zip_codes"].get(zip_code, 0) + 1
        zip_totals[zip_code] = zip_totals.get(zip_code, 0) + 1

    city_list = []
    for data in sorted(cities.values(), key=lambda x: x["total"], reverse=True):
        zips = [
            {"zip_code": z, "total": n}
            for z, n in sorted(data["zip_codes"].items(), key=lambda x: x[1], reverse=True)
        ]
        city_list.append({"city": data["city"], "total": data["total"], "zip_codes": zips})

    zip_list = [
        {"zip_code": z, "total": n}
        for z, n in sorted(zip_totals.items(), key=lambda x: x[1], reverse=True)
    ]
    return city_list, zip_list


def _candidate_matches_region(candidate: models.Candidate, region: models.FlexRegion) -> bool:
    if region.zip_code and region.zip_code.strip():
        return _zip_label(candidate.zip_code) == region.zip_code.strip()
    if region.city and region.city.strip():
        cand_city = (candidate.region or "").strip().lower()
        return cand_city == region.city.strip().lower()
    return False


def locations_by_status(db: Session, status: OnboardingStatus) -> dict:
    """Localizaciones de candidatos en un estado + regiones Flex elegibles para crear cuenta."""
    candidates = list(
        db.scalars(select(models.Candidate).where(models.Candidate.status == status)).all()
    )
    city_list, zip_list = _group_candidates_by_location(candidates)
    can_create = status in ACCOUNT_CREATION_STATUSES

    flex_regions = list(
        db.scalars(
            select(models.FlexRegion)
            .where(models.FlexRegion.active.is_(True))
            .order_by(models.FlexRegion.label)
        ).all()
    )

    eligible: list[dict] = []
    if can_create:
        for region in flex_regions:
            count = sum(1 for c in candidates if _candidate_matches_region(c, region))
            eligible.append(
                {
                    "id": region.id,
                    "label": region.label,
                    "city": region.city,
                    "zip_code": region.zip_code,
                    "us_state": region.us_state,
                    "candidates_in_status": count,
                    "can_create_account": True,
                }
            )
        message = None
    else:
        message = (
            f"El estado '{status.value}' no es de creación de cuenta. "
            "Consulta regiones en: not_started, invited, registration_started o documents_pending."
        )

    return {
        "status": status,
        "can_create_account": can_create,
        "total_candidates": len(candidates),
        "message": message,
        "cities": city_list,
        "zip_codes": zip_list,
        "eligible_regions": eligible,
    }


# --------------------------------------------------------------------------- #
# Catálogo de regiones Flex
# --------------------------------------------------------------------------- #
DEFAULT_FLEX_REGIONS: list[dict] = [
    {"label": "Miami — Downtown", "city": "Miami", "zip_code": "33101", "us_state": "FL"},
    {"label": "Miami — Brickell", "city": "Miami", "zip_code": "33131", "us_state": "FL"},
    {"label": "Miami — Hialeah", "city": "Miami", "zip_code": "33010", "us_state": "FL"},
    {"label": "Miami Gardens / Carol City", "city": "Miami Gardens", "zip_code": "33055", "us_state": "FL"},
    {"label": "Orlando — Centro", "city": "Orlando", "zip_code": "32801", "us_state": "FL"},
    {"label": "Tampa — Downtown", "city": "Tampa", "zip_code": "33602", "us_state": "FL"},
    {"label": "Fort Lauderdale", "city": "Fort Lauderdale", "zip_code": "33301", "us_state": "FL"},
]


def ensure_default_flex_regions(db: Session) -> int:
    """Añade regiones del catálogo base que aún no existan (por ZIP)."""
    added = 0
    for item in DEFAULT_FLEX_REGIONS:
        zip_code = item.get("zip_code")
        if zip_code:
            exists = db.scalar(
                select(models.FlexRegion.id).where(models.FlexRegion.zip_code == zip_code)
            )
            if exists:
                continue
        db.add(models.FlexRegion(**item))
        added += 1
    if added:
        db.commit()
    return added


def seed_flex_regions(db: Session) -> int:
    """Inserta regiones Flex de ejemplo si el catálogo está vacío."""
    existing = db.scalar(select(func.count()).select_from(models.FlexRegion)) or 0
    if existing:
        return ensure_default_flex_regions(db)
    for item in DEFAULT_FLEX_REGIONS:
        db.add(models.FlexRegion(**item))
    db.commit()
    return len(DEFAULT_FLEX_REGIONS)


def flex_eligibility_by_zip(db: Session, zip_code: str) -> dict:
    """Consulta un ZIP en el catálogo Flex local (NO llama a Amazon)."""
    zip_code = zip_code.strip()
    base_message = (
        "Este CRM no consulta la API de Amazon Flex. "
        "Solo busca en tu catálogo manual de zonas y en tus candidatos guardados."
    )

    if not zip_code:
        return {
            "zip_code": "",
            "uses_amazon_api": False,
            "message": base_message,
            "in_catalog": False,
            "can_create_account": False,
            "candidates_with_zip": 0,
            "matching_regions": [],
            "nearby_regions": [],
        }

    matching = list(
        db.scalars(
            select(models.FlexRegion)
            .where(models.FlexRegion.active.is_(True), models.FlexRegion.zip_code == zip_code)
            .order_by(models.FlexRegion.label)
        ).all()
    )

    nearby: list[models.FlexRegion] = []
    if not matching and len(zip_code) >= 3:
        prefix = zip_code[:3]
        nearby = list(
            db.scalars(
                select(models.FlexRegion)
                .where(
                    models.FlexRegion.active.is_(True),
                    models.FlexRegion.zip_code.like(f"{prefix}%"),
                    models.FlexRegion.zip_code != zip_code,
                )
                .order_by(models.FlexRegion.zip_code)
                .limit(8)
            ).all()
        )

    candidates_count = (
        db.scalar(
            select(func.count())
            .select_from(models.Candidate)
            .where(models.Candidate.zip_code == zip_code)
        )
        or 0
    )

    in_catalog = len(matching) > 0
    if in_catalog:
        detail = f"ZIP {zip_code} está en tu catálogo Flex ({len(matching)} zona(s))."
    elif nearby:
        detail = (
            f"ZIP {zip_code} no está en el catálogo, pero hay {len(nearby)} zona(s) "
            f"cercanas (mismo prefijo {zip_code[:3]})."
        )
    else:
        detail = f"ZIP {zip_code} no está en el catálogo Flex. Agrégalo con POST /api/flex-regions."

    return {
        "zip_code": zip_code,
        "uses_amazon_api": False,
        "message": f"{base_message} {detail}",
        "in_catalog": in_catalog,
        "can_create_account": in_catalog,
        "candidates_with_zip": candidates_count,
        "matching_regions": matching,
        "nearby_regions": nearby,
    }


def list_flex_regions(db: Session, *, active_only: bool = False) -> list[models.FlexRegion]:
    stmt = select(models.FlexRegion).order_by(models.FlexRegion.label)
    if active_only:
        stmt = stmt.where(models.FlexRegion.active.is_(True))
    return list(db.scalars(stmt).all())


def create_flex_region(db: Session, data: schemas.FlexRegionCreate) -> models.FlexRegion:
    region = models.FlexRegion(**data.model_dump())
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


# --------------------------------------------------------------------------- #
# Jobs asíncronos de Sembrar (cola en BD)
# --------------------------------------------------------------------------- #
def enqueue_flex_dispatch_job(
    db: Session,
    *,
    candidate_ids: list[int],
    actor: str | None = None,
) -> models.FlexJob:
    import uuid

    from app.enums import FlexJobStatus

    unique_ids = list(dict.fromkeys(candidate_ids))
    job = models.FlexJob(
        id=str(uuid.uuid4()),
        status=FlexJobStatus.QUEUED,
        candidate_ids=unique_ids,
        actor=actor,
        message=f"En cola · {len(unique_ids)} siembra(s)",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def get_flex_job(db: Session, job_id: str) -> models.FlexJob | None:
    return db.get(models.FlexJob, job_id)


def recover_interrupted_running_jobs(
    db: Session,
    *,
    requeue_younger_than_s: int = 180,
    fail_older_than_s: int = 20 * 60,
) -> tuple[int, int]:
    """Tras reinicio del worker (--reload): reencola jobs recientes, falla huérfanos viejos.

    Returns (requeued, failed).
    """
    from datetime import datetime, timedelta, timezone

    from app.enums import FlexJobStatus

    now = datetime.now(timezone.utc)
    young_cut = now - timedelta(seconds=max(30, requeue_younger_than_s))
    old_cut = now - timedelta(seconds=max(requeue_younger_than_s, fail_older_than_s))

    jobs = list(
        db.scalars(
            select(models.FlexJob).where(models.FlexJob.status == FlexJobStatus.RUNNING)
        ).all()
    )
    requeued = 0
    failed = 0
    for job in jobs:
        started = job.started_at or job.created_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        # Muy reciente o sin timestamp → reencolar (el hilo murió por reload)
        if started is None or started >= young_cut:
            job.status = FlexJobStatus.QUEUED
            job.started_at = None
            job.finished_at = None
            job.error = None
            job.message = "Reencolado tras reinicio del worker…"
            requeued += 1
            continue

        # Viejo → huérfano real
        if started <= old_cut:
            reason = (
                "Job huérfano: llevaba demasiado tiempo en RUNNING "
                "(probablemente el servidor se reinició a mitad)."
            )
            job.status = FlexJobStatus.FAILED
            job.error = reason
            job.message = "Falló el sembrado (job interrumpido)"
            job.finished_at = now
            failed += 1
            for cid in list(job.candidate_ids or []):
                cand = get_candidate(db, int(cid))
                if cand is None:
                    continue
                _log_event(
                    db,
                    cand,
                    EventType.NOTE_ADDED,
                    message=f"Sembrar falló (job {job.id[:8]}…): {reason}",
                    actor=job.actor,
                )
            continue

        # Zona media: también reencolar (mejor reintentar que quedar colgado)
        job.status = FlexJobStatus.QUEUED
        job.started_at = None
        job.finished_at = None
        job.error = None
        job.message = "Reencolado tras reinicio del worker…"
        requeued += 1

    if requeued or failed:
        db.commit()
    return requeued, failed


def fail_stale_running_jobs(
    db: Session,
    *,
    older_than_seconds: int = 0,
    reason: str = "Job interrumpido (reinicio del worker / servidor).",
) -> int:
    """Marca jobs RUNNING como FAILED.

    Preferir recover_interrupted_running_jobs en el worker embebido.
    Si older_than_seconds > 0, solo los más viejos que ese umbral.
    """
    from datetime import datetime, timedelta, timezone

    from app.enums import FlexJobStatus

    q = select(models.FlexJob).where(models.FlexJob.status == FlexJobStatus.RUNNING)
    jobs = list(db.scalars(q).all())
    if older_than_seconds > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
        filtered = []
        for j in jobs:
            started = j.started_at or j.created_at
            if started is None:
                filtered.append(j)
                continue
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if started <= cutoff:
                filtered.append(j)
        jobs = filtered
    now = datetime.now(timezone.utc)
    for job in jobs:
        job.status = FlexJobStatus.FAILED
        job.error = reason
        job.message = "Falló el sembrado (job interrumpido)"
        job.finished_at = now
        for cid in list(job.candidate_ids or []):
            cand = get_candidate(db, int(cid))
            if cand is None:
                continue
            _log_event(
                db,
                cand,
                EventType.NOTE_ADDED,
                message=f"Sembrar falló (job {job.id[:8]}…): {reason}",
                actor=job.actor,
            )
    if jobs:
        db.commit()
    return len(jobs)


def claim_next_flex_job(db: Session) -> models.FlexJob | None:
    """Toma el job queued más antiguo y lo marca running."""
    from datetime import datetime, timezone

    from app.enums import FlexJobStatus

    job = db.scalars(
        select(models.FlexJob)
        .where(models.FlexJob.status == FlexJobStatus.QUEUED)
        .order_by(models.FlexJob.created_at.asc())
        .limit(1)
    ).first()
    if job is None:
        return None
    job.status = FlexJobStatus.RUNNING
    job.started_at = datetime.now(timezone.utc)
    job.message = "Ejecutando sembrado (Amazon + región)…"
    db.commit()
    db.refresh(job)
    return job


def complete_flex_job(
    db: Session,
    job: models.FlexJob,
    *,
    result: schemas.BatchFlexDispatchResult | None = None,
    error: str | None = None,
) -> models.FlexJob:
    from datetime import datetime, timezone

    from app.enums import FlexJobStatus

    job.finished_at = datetime.now(timezone.utc)
    if error:
        job.status = FlexJobStatus.FAILED
        job.error = error
        job.message = "Falló el sembrado"
        job.result = None
    else:
        job.status = FlexJobStatus.COMPLETED
        job.error = None
        payload = result.model_dump() if result is not None else None
        job.result = payload
        if result is not None:
            job.message = (
                f"Listo · {result.dispatched} ok · {result.skipped} fallida(s)"
            )
            if result.skipped and result.skipped_items:
                first = result.skipped_items[0].reason or ""
                if first:
                    job.message += f" · {first[:180]}"
        else:
            job.message = "Completado"
    db.commit()
    db.refresh(job)
    return job


def flex_job_to_schema(job: models.FlexJob) -> schemas.FlexJobOut:
    result = None
    if job.result:
        result = schemas.BatchFlexDispatchResult.model_validate(job.result)
    return schemas.FlexJobOut(
        id=job.id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        candidate_ids=list(job.candidate_ids or []),
        actor=job.actor,
        message=job.message,
        error=job.error,
        result=result,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
