"""Schemas Pydantic para validación y serialización de la API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.enums import ChecklistStatus, EventType, OnboardingStatus


# --------------------------------------------------------------------------- #
# Checklist
# --------------------------------------------------------------------------- #
class ChecklistItemBase(BaseModel):
    label: str = Field(..., max_length=255)
    status: ChecklistStatus = ChecklistStatus.PENDING
    notes: str | None = None
    position: int = 0


class ChecklistItemCreate(ChecklistItemBase):
    pass


class ChecklistItemUpdate(BaseModel):
    label: str | None = Field(default=None, max_length=255)
    status: ChecklistStatus | None = None
    notes: str | None = None
    position: int | None = None


class ChecklistItemOut(ChecklistItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    event_type: EventType
    message: str
    from_status: str | None = None
    to_status: str | None = None
    actor: str | None = None
    created_at: datetime


class NoteCreate(BaseModel):
    message: str = Field(..., min_length=1)
    actor: str | None = None


# --------------------------------------------------------------------------- #
# Candidate
# --------------------------------------------------------------------------- #
class CandidateBase(BaseModel):
    full_name: str = Field(..., max_length=200)
    assigned_email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=120)
    zip_code: str | None = Field(default=None, max_length=20)
    notes: str | None = None


class CandidateCreate(CandidateBase):
    # Si es True (por defecto) se genera el checklist estándar al crear.
    seed_checklist: bool = True


class CandidateUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    assigned_email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    region: str | None = Field(default=None, max_length=120)
    zip_code: str | None = Field(default=None, max_length=20)
    notes: str | None = None


class StatusChange(BaseModel):
    status: OnboardingStatus
    actor: str | None = None
    message: str | None = None


class HandoffUpdate(BaseModel):
    external_ref: str | None = Field(default=None, max_length=255)
    actor: str | None = None


class MailboxCredentialSet(BaseModel):
    """Establece/actualiza la contraseña del buzón (se guarda cifrada)."""

    password: str = Field(..., min_length=1)
    actor: str | None = None


class MailboxCredentialReveal(BaseModel):
    """Respuesta al revelar la credencial (descifrada bajo demanda)."""

    assigned_email: str
    password: str


class CandidateOut(CandidateBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OnboardingStatus
    handoff_ready: bool
    handoff_done: bool
    external_ref: str | None = None
    # Solo indica SI existe credencial; nunca expone el secreto en el listado/detalle.
    has_mailbox_credential: bool = False
    created_at: datetime
    updated_at: datetime


class CandidateDetail(CandidateOut):
    checklist_items: list[ChecklistItemOut] = []
    timeline_events: list[TimelineEventOut] = []


class CandidateList(BaseModel):
    total: int
    items: list[CandidateOut]


class CandidateStationGroup(BaseModel):
    """Expedientes agrupados por estación Flex (código + métricas)."""

    station_code: str
    station_label: str
    total: int
    active: int
    with_credential: int
    items: list[CandidateOut]


class CandidateGroupedList(BaseModel):
    grand_total: int
    group_count: int
    active_total: int
    credential_total: int
    groups: list[CandidateStationGroup]


class ZipStats(BaseModel):
    """Métricas de conversión agregadas por ZIP code / zona."""

    zip_code: str
    total: int          # candidatos registrados en ese ZIP
    applied: int        # ya salieron de not_started (proceso iniciado)
    responded: int      # llegaron al menos a background_check/waitlisted/approved
    active: int         # approved_active
    rejected: int
    waitlisted: int


class ZipStatsList(BaseModel):
    zones: list[ZipStats]


class ZipCount(BaseModel):
    """Conteo simple de candidatos en un ZIP (dentro de una ciudad)."""

    zip_code: str
    total: int


class CityStats(BaseModel):
    """Totales por ciudad con desglose de ZIP codes."""

    city: str
    total: int
    zip_codes: list[ZipCount]


class LocationStats(BaseModel):
    """Resumen geográfico: por ciudad y por ZIP code."""

    grand_total: int
    cities: list[CityStats]
    zip_codes: list[ZipCount]


class FlexEligibleLocation(BaseModel):
    """Región del catálogo Flex con conteo de candidatos en el estado consultado."""

    id: int
    label: str
    city: str | None = None
    zip_code: str | None = None
    us_state: str | None = None
    candidates_in_status: int
    can_create_account: bool = True


class LocationsByStatus(BaseModel):
    """Localizaciones relevantes para un estado de onboarding."""

    status: OnboardingStatus
    can_create_account: bool
    total_candidates: int
    message: str | None = None
    cities: list[CityStats]
    zip_codes: list[ZipCount]
    eligible_regions: list[FlexEligibleLocation]


class FlexRegionBase(BaseModel):
    label: str = Field(..., max_length=200)
    city: str | None = Field(default=None, max_length=120)
    zip_code: str | None = Field(default=None, max_length=20)
    us_state: str | None = Field(default=None, max_length=10)
    active: bool = True
    notes: str | None = None


class FlexRegionCreate(FlexRegionBase):
    pass


class FlexRegionOut(FlexRegionBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class ZipFlexLookup(BaseModel):
    """Resultado de consultar un ZIP contra el catálogo Flex (NO es API de Amazon)."""

    zip_code: str
    uses_amazon_api: bool = False
    message: str
    in_catalog: bool
    can_create_account: bool
    candidates_with_zip: int
    matching_regions: list[FlexRegionOut]
    nearby_regions: list[FlexRegionOut]


class FlexStationOut(BaseModel):
    code: str
    name: str
    city: str
    state: str | None = None
    lat: float
    lng: float
    distance_km: float | None = None


class FlexStationSearchResult(BaseModel):
    query: dict[str, str | None]
    geocoded: dict | None = None
    radius_km: float
    source: str
    uses_amazon_api: bool = False
    message: str
    total: int
    stations: list[FlexStationOut]


class CandidateImportError(BaseModel):
    line: int
    email: str | None = None
    reason: str


class CandidateImportResult(BaseModel):
    created: int
    skipped: int
    errors: list[CandidateImportError]
    created_ids: list[int] = []


class BatchFlexDispatch(BaseModel):
    """Envía siembras pendientes a creación Amazon Flex (actualiza estado en el CRM)."""

    candidate_ids: list[int] = Field(..., min_length=1)
    actor: str | None = None


class BatchFlexDispatchItem(BaseModel):
    id: int
    assigned_email: str
    previous_status: str
    new_status: str
    creation_message: str | None = None
    flex_outcome: str | None = None
    zip_used: str | None = None


class BatchFlexDispatchSkip(BaseModel):
    id: int
    assigned_email: str | None = None
    reason: str
    creation_message: str | None = None
    flex_outcome: str | None = None


class BatchFlexDispatchResult(BaseModel):
    dispatched: int
    skipped: int
    items: list[BatchFlexDispatchItem]
    skipped_items: list[BatchFlexDispatchSkip]


class FlexJobEnqueue(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=1)
    actor: str | None = None


class FlexJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    candidate_ids: list[int]
    actor: str | None = None
    message: str | None = None
    error: str | None = None
    result: BatchFlexDispatchResult | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class FlexJobEnqueueResult(BaseModel):
    job_id: str
    status: str
    candidate_count: int
    message: str
    poll_url: str
