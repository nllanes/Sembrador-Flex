"""Modelos ORM del dominio: Candidate, ChecklistItem y TimelineEvent."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import ChecklistStatus, EventType, FlexJobStatus, OnboardingStatus

class Candidate(Base):
    """Expediente de onboarding de un conductor Amazon Flex."""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Email de Amazon Flex asignado al candidato (único).
    assigned_email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # ZIP code / código postal de la zona a la que aplica el conductor.
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    status: Mapped[OnboardingStatus] = mapped_column(
        SAEnum(OnboardingStatus, name="onboarding_status"),
        default=OnboardingStatus.NOT_STARTED,
        nullable=False,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Credencial del buzón de correo administrado (contraseña CIFRADA en reposo).
    # Nunca se guarda en texto plano; se cifra con Fernet (ver app/security.py).
    mailbox_password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Handoff: marca cuando el expediente está listo para vincularse en el otro sistema.
    handoff_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    handoff_done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Referencia externa una vez vinculado en el sistema de monitoreo (opcional).
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    checklist_items: Mapped[list[ChecklistItem]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        order_by="ChecklistItem.position",
    )
    timeline_events: Mapped[list[TimelineEvent]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        order_by="TimelineEvent.created_at.desc()",
    )

    @property
    def has_mailbox_credential(self) -> bool:
        """True si hay una contraseña de buzón guardada (cifrada)."""
        return self.mailbox_password_enc is not None


class ChecklistItem(Base):
    """Ítem del checklist de seguimiento de un expediente."""

    __tablename__ = "checklist_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )

    label: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[ChecklistStatus] = mapped_column(
        SAEnum(ChecklistStatus, name="checklist_status"),
        default=ChecklistStatus.PENDING,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    candidate: Mapped[Candidate] = relationship(back_populates="checklist_items")


class TimelineEvent(Base):
    """Evento de la línea de tiempo (auditoría) de un expediente."""

    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_type: Mapped[EventType] = mapped_column(
        SAEnum(EventType, name="event_type"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    # Estados de/hacia (solo relevantes en cambios de estado).
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    candidate: Mapped[Candidate] = relationship(back_populates="timeline_events")


class FlexRegion(Base):
    """Zona donde Amazon Flex acepta creación de cuentas (catálogo manual).

    Lo mantienes tú según disponibilidad real de Amazon en cada área.
    NO consulta Amazon automáticamente.
    """

    __tablename__ = "flex_regions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    zip_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    us_state: Mapped[str | None] = mapped_column(String(10), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FlexJob(Base):
    """Job asíncrono de Sembrar (cola en BD; worker separado o embebido)."""

    __tablename__ = "flex_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[FlexJobStatus] = mapped_column(
        SAEnum(FlexJobStatus, name="flex_job_status"),
        default=FlexJobStatus.QUEUED,
        nullable=False,
        index=True,
    )
    candidate_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    actor: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
