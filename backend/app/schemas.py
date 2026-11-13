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
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    gps_accuracy_m: float | None = Field(default=None, ge=0)
    mocked_location: bool = False
    anonymous: bool = True
    author_name: str | None = Field(default=None, max_length=40)
    hide_point: bool = True
    observed_at: datetime | None = None  # set by the offline queue

    @field_validator("text")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()


class ReactionIn(BaseModel):
    kind: ReactionKind | None  # None removes my reaction
    lat: float | None = None
    lon: float | None = None


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
    ai_hazard: str
    ai_tags: list[str]
    observed_at: datetime
    age_min: int
    freshness: Literal["fresh", "stale", "old"]
    counts: dict[str, int]
    my_reaction: str | None
    mine: bool
    excluded: bool


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
