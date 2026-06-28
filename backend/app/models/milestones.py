"""Property milestones (Phase 15b) — DDL owned by alembic/0015.

A milestone is a per-property project event (e.g. "Foundation", "Handover") that
developers (the ``owner`` role) author and investors read on the property-detail
page. It is the single real source that replaces (a) the fully-hardcoded
``PropertyTimeline`` mock and (b) the ``content.timeline`` JSONB blob the
sample/advanced construction pages used to read.

* ``value_index`` is the NAV step (100 = entry). NULL for regular milestones;
  populated for construction-model milestones (preserves surfaces C/D).
* The property's overall construction % is NOT stored here — it is COMPUTED from
  these rows on read (see ``milestone_service.construction_progress_from_rows``),
  so there is no hand-maintained scalar that can drift.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, MilestoneStatus

_NOW = func.now()

# Reference the existing PG enum by name; alembic/0015 owns the DDL (never created here).
_milestone_status = ENUM(
    MilestoneStatus,
    name="milestone_status",
    create_type=False,
    values_callable=lambda obj: [e.value for e in obj],
)


class PropertyMilestone(Base):
    __tablename__ = "property_milestones"
    __table_args__ = (
        CheckConstraint(
            "progress_pct IS NULL OR (progress_pct >= 0 AND progress_pct <= 100)",
            name="property_milestones_progress_pct_check",
        ),
        Index("property_milestones_property_sort_idx", "property_id", "sort_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MilestoneStatus] = mapped_column(
        _milestone_status, nullable=False, server_default="planned"
    )
    progress_pct: Mapped[int | None] = mapped_column(Integer)
    value_index: Mapped[int | None] = mapped_column(Integer)
    target_date: Mapped[datetime.date | None] = mapped_column(Date)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=_NOW
    )
