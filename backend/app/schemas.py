from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ObsType = Literal["crack", "hole", "water", "thin", "floe", "clear"]
Method = Literal["Лунка", "Бур", "На глаз"]
IceType = Literal["Прозрачный", "Белый слоистый", "Снег сверху", "Вода сверху"]
ReactionKind = Literal["confirm", "changed", "wrong"]


class ObservationIn(BaseModel):
    type: ObsType
    zone_id: str | None = None
    thickness_cm: int | None = Field(default=None, ge=0, le=150)
    method: Method | None = None
    ice_type: IceType | None = None
    text: str = Field(default="", max_length=280)
    # finite numbers only: "1e309" (infinity) or NaN would crash MySQL, which cannot store them
    lat: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    lon: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    gps_accuracy_m: float | None = Field(default=None, ge=0, le=100_000, allow_inf_nan=False)
    mocked_location: bool = False
    anonymous: bool = True
    hide_point: bool = True
    observed_at: datetime | None = None  # set by the offline queue

    @field_validator("text")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class ReactionIn(BaseModel):
    kind: ReactionKind | None  # None removes my reaction
    lat: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    lon: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)


class ObservationOut(BaseModel):
    id: int
    zone_id: str
    zone_name: str
    type: ObsType
    type_label: str
    severity: str
    thickness_cm: int | None
    method: str | None
    ice_type: str | None
    text: str
    lat: float | None
    lon: float | None
    onsite: bool
    gps_accuracy_m: float | None
    author: str
    photo_url: str | None
    photo: "PhotoInfo | None" = None
    ai_hazard: str
    ai_tags: list[str]
    observed_at: datetime
    age_min: int
    freshness: Literal["fresh", "stale", "old"]
    counts: dict[str, int]
    my_reaction: str | None
    mine: bool
    excluded: bool
    moderation_status: Literal["ok", "pending", "hidden"] = "ok"
    moderation_note: str | None = None   # what the viewer should know, e.g. "текст на проверке"
    reports_count: int = 0               # moderators only
    my_report: bool = False


class PhotoInfo(BaseModel):
    faces_blurred: int
    plates_blurred: int
    privacy_processed: bool
    privacy_detector: str          # yolo | haar
    privacy_status: str            # NO_DETECTIONS | PROCESSED_REQUIRES_REVIEW
    looks_like_ice: bool | None
    material: dict[str, float]     # snow, white_ice, clear_ice, water, other
    texture: str | None
    crack_score: float | None
    signs: list[str]
    hazard: str
    source: str                    # cv | cv+model | cv+ollama | cv+model+ollama
    ai_checked: bool               # a vision language model looked at the photo


class StatusOut(BaseModel):
    level: Literal["danger", "risk", "clear", "nodata"]
    label: str
    advice: str
    reasons: list[str]
    fresh_count: int
    fresh_window_h: int
    last_observed_at: datetime | None
    conflict: bool
    offshore_wind: bool


ObservationOut.model_rebuild()


class ReportIn(BaseModel):
    reason: Literal["spam", "insult", "fake", "not_ice", "personal", "other"]
    comment: str = Field(default="", max_length=300)


class ModerationIn(BaseModel):
    action: Literal["approve", "hide", "delete"]
    note: str = Field(default="", max_length=300)
    ban_days: int | None = Field(default=None, ge=1, le=365)
