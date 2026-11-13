from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    bay: Mapped[str] = mapped_column(String(80))
    geometry: Mapped[dict] = mapped_column(JSON)
    offshore_from: Mapped[list] = mapped_column(JSON, default=list)
    ban: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_text: Mapped[str | None] = mapped_column(String(300), nullable=True)

    observations: Mapped[list[Observation]] = relationship(back_populates="zone")


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    thickness_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ice_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    onsite: Mapped[bool] = mapped_column(Boolean, default=False)
    hide_point: Mapped[bool] = mapped_column(Boolean, default=True)
    device_id: Mapped[str] = mapped_column(String(64), index=True)
    author_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    photo_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_hazard: Mapped[str] = mapped_column(String(10), default="none")
    ai_tags: Mapped[list] = mapped_column(JSON, default=list)
    ai_source: Mapped[str] = mapped_column(String(10), default="rules")
    # when the user saw it (offline queue) vs. when the server got it
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    zone: Mapped[Zone] = relationship(back_populates="observations")
    reactions: Mapped[list[Reaction]] = relationship(back_populates="observation", cascade="all, delete-orphan")

    @property
    def counts(self) -> dict[str, int]:
        c = {"confirm": 0, "changed": 0, "wrong": 0}
        for r in self.reactions:
            c[r.kind] = c.get(r.kind, 0) + 1
        return c


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("observation_id", "device_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(10))  # confirm | changed | wrong
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    observation: Mapped[Observation] = relationship(back_populates="reactions")
