"""Configuration models and loader. Everything data-driven lives in YAML and is
validated here so a bad number fails at load time, never mid-flight.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

T = TypeVar("T", bound=BaseModel)

CONFIG_DIR = Path(__file__).parent / "config"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PodConfig(_Strict):
    """HANUMAN placeholder v0. Replaced by the OpenVSP aero table later."""
    name: str
    mass_kg: float = Field(gt=0)
    ld_ratio: float = Field(gt=0, description="deployed glide ratio L/D")
    thrust_n: float = Field(ge=0)
    endurance_s: float = Field(ge=0, description="powered endurance in seconds")
    cruise_speed_mps: float = Field(gt=0)
    stabilise_delay_s: float = Field(ge=0, description="handover to stable flight after separation")


class BoundingBox(_Strict):
    lat_min: float = Field(ge=-90, le=90)
    lat_max: float = Field(ge=-90, le=90)
    lon_min: float = Field(ge=-180, le=180)
    lon_max: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def _ordered(self) -> "BoundingBox":
        if self.lat_min >= self.lat_max or self.lon_min >= self.lon_max:
            raise ValueError("bounding box min must be < max")
        return self


class SectorConfig(_Strict):
    name: str
    country: str
    bbox: BoundingBox
    border_rule: str = Field(pattern="^hard$", description="only 'hard' is permitted")
    min_border_margin_m: float = Field(ge=0)
    advisor_rate_hz: float = Field(gt=0)


class WeightsConfig(_Strict):
    """Ranking weights. The friendly filter is a hard rule and has no weight here on purpose."""
    reachability_confidence: float = Field(ge=0)
    surface_quality: float = Field(ge=0)
    distance: float = Field(ge=0)
    threat_exposure: float = Field(ge=0)
    weather: float = Field(ge=0)
    medical_urgency: float = Field(ge=0)
    rescue_reachability: float = Field(ge=0)


def load_yaml(path: Path | str, model: type[T]) -> T:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return model.model_validate(raw)


def load_default(model: type[T], filename: str) -> T:
    return load_yaml(CONFIG_DIR / filename, model)
