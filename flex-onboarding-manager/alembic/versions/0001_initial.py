"""Migración inicial: candidates, checklist_items, timeline_events.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


onboarding_status = sa.Enum(
    "not_started",
    "invited",
    "registration_started",
    "documents_pending",
    "documents_submitted",
    "background_check",
    "waitlisted",
    "approved_active",
    "rejected",
    "inactive",
    name="onboarding_status",
)

checklist_status = sa.Enum(
    "pending",
    "in_progress",
    "done",
    "blocked",
    "not_applicable",
    name="checklist_status",
)

event_type = sa.Enum(
    "created",
    "status_changed",
    "checklist_updated",
    "note_added",
    "handoff_ready",
    "handoff_done",
    "credential_set",
    "credential_revealed",
    "credential_cleared",
    name="event_type",
)


def upgrade() -> None:
    bind = op.get_bind()
    onboarding_status.create(bind, checkfirst=True)
    checklist_status.create(bind, checkfirst=True)
    event_type.create(bind, checkfirst=True)

    op.create_table(
        "candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("assigned_email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("zip_code", sa.String(length=20), nullable=True),
        sa.Column(
            "status",
            onboarding_status,
            nullable=False,
            server_default="not_started",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("mailbox_password_enc", sa.Text(), nullable=True),
        sa.Column("handoff_ready", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("handoff_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_candidates_assigned_email", "candidates", ["assigned_email"], unique=True)
    op.create_index("ix_candidates_status", "candidates", ["status"])
    op.create_index("ix_candidates_zip_code", "candidates", ["zip_code"])

    op.create_table(
        "checklist_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "status",
            checklist_status,
            nullable=False,
            server_default="pending",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_checklist_items_candidate_id", "checklist_items", ["candidate_id"])

    op.create_table(
        "timeline_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=True),
        sa.Column("actor", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_timeline_events_candidate_id", "timeline_events", ["candidate_id"])
    op.create_index("ix_timeline_events_created_at", "timeline_events", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_timeline_events_created_at", table_name="timeline_events")
    op.drop_index("ix_timeline_events_candidate_id", table_name="timeline_events")
    op.drop_table("timeline_events")

    op.drop_index("ix_checklist_items_candidate_id", table_name="checklist_items")
    op.drop_table("checklist_items")

    op.drop_index("ix_candidates_zip_code", table_name="candidates")
    op.drop_index("ix_candidates_status", table_name="candidates")
    op.drop_index("ix_candidates_assigned_email", table_name="candidates")
    op.drop_table("candidates")

    bind = op.get_bind()
    event_type.drop(bind, checkfirst=True)
    checklist_status.drop(bind, checkfirst=True)
    onboarding_status.drop(bind, checkfirst=True)
