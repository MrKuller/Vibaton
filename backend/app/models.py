"""Tables. Types are chosen to work the same on MySQL 8 / MariaDB and SQLite.

Datetimes are stored as naive UTC (MySQL DATETIME has no time zone); app code treats naive as UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(40))
    role: Mapped[str] = mapped_column(String(20), default="user")  # user | moderator | admin
    banned_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ban_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    # sha256 of the token; the token itself is only ever on the phone
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped[User] = relationship()


class Zone(Base):
    """One water cell of data/grid.geojson. Geometry, bans and wind sectors live in app/grid.py (memory);
    the table exists so observations can reference cells with a foreign key."""
    __tablename__ = "zones"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    bay: Mapped[str] = mapped_column(String(80))
    place_id: Mapped[str | None] = mapped_column(String(40), nullable=True)

    observations: Mapped[list[Observation]] = relationship(back_populates="zone")


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[str] = mapped_column(ForeignKey("zones.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
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
    anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    photo_path: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ai_hazard: Mapped[str] = mapped_column(String(10), default="none")  # from the text
    ai_tags: Mapped[list] = mapped_column(JSON, default=list)
    ai_source: Mapped[str] = mapped_column(String(10), default="rules")
    photo_hazard: Mapped[str] = mapped_column(String(10), default="none")  # from the photo
    # ok | pending (text and photo hidden, danger still counts) | hidden (not shown, not counted)
    moderation_status: Mapped[str] = mapped_column(String(10), default="ok", index=True)
    moderation_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # when the user saw it (offline queue) vs. when the server got it
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    zone: Mapped[Zone] = relationship(back_populates="observations")
    user: Mapped[User] = relationship()
    reactions: Mapped[list[Reaction]] = relationship(back_populates="observation", cascade="all, delete-orphan")
    photo_analysis: Mapped[PhotoAnalysis | None] = relationship(
        back_populates="observation", cascade="all, delete-orphan", uselist=False)
    reports: Mapped[list[Report]] = relationship(back_populates="observation", cascade="all, delete-orphan")

    @property
    def counts(self) -> dict[str, int]:
        c = {"confirm": 0, "changed": 0, "wrong": 0}
        for r in self.reactions:
            c[r.kind] = c.get(r.kind, 0) + 1
        return c


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("observation_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10))  # confirm | changed | wrong
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    observation: Mapped[Observation] = relationship(back_populates="reactions")


class PhotoAnalysis(Base):
    """Result of processing one uploaded photo (see vision.py and anonymizer.py)."""
    __tablename__ = "photo_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"), unique=True)
    # model 1: anonymization
    face_count: Mapped[int] = mapped_column(Integer, default=0)
    plate_count: Mapped[int] = mapped_column(Integer, default=0)
    privacy_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    privacy_detector: Mapped[str] = mapped_column(String(10), default="haar")  # yolo | haar
    privacy_detections: Mapped[list] = mapped_column(JSON, default=list)        # [{"kind","confidence"}]
    privacy_status: Mapped[str] = mapped_column(String(30), default="NO_DETECTIONS")
    # model 2: ice analysis
    material: Mapped[dict] = mapped_column(JSON, default=dict)                  # {"snow": .7, "water": .2, ...}
    texture: Mapped[str | None] = mapped_column(String(20), nullable=True)
    crack_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    looks_like_ice: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # None = not checked by AI
    detected_signs: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["трещина", "вода на льду"]
    hazard: Mapped[str] = mapped_column(String(10), default="none")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_source: Mapped[str] = mapped_column(String(30), default="cv")  # cv | cv+model | +ollama
    analysis_status: Mapped[str] = mapped_column(String(20), default="done")  # done | ai_unavailable
    phash: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)  # duplicate detection
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    observation: Mapped[Observation] = relationship(back_populates="photo_analysis")


class Report(Base):
    """A complaint about an observation. One per user per observation."""
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("observation_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str] = mapped_column(String(300), default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    observation: Mapped[Observation] = relationship(back_populates="reports")


class ModerationAction(Base):
    """Who did what: every moderator decision is logged."""
    __tablename__ = "moderation_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    moderator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    observation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # kept after deletion
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(20))  # approve | hide | delete | ban | unban | auto_review
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
