"""Pydantic models / data contracts for Aegis."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class Camera(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    image_url: Optional[str] = None
    view: Optional[str] = None
    available: bool = True


class Disruption(BaseModel):
    id: str
    severity: Optional[str] = None
    category: Optional[str] = None
    sub_category: Optional[str] = None
    status: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    comments: Optional[str] = None
    start_at: Optional[str] = None        # ISO8601
    updated_at: Optional[str] = None      # ISO8601 — used as "official_logged_at"


class Incident(BaseModel):
    """One non-clear VL detection, optionally cross-referenced to an official disruption."""
    camera_id: str
    common_name: str
    lat: float
    lon: float
    category: str
    confidence: float
    description: str
    image_thumb_url: Optional[str] = None
    detected_at: str                      # ISO8601 (UTC)

    # cross-reference (filled by the disruptions matcher)
    matched_disruption_id: Optional[str] = None
    official_logged_at: Optional[str] = None
    lead_time_seconds: Optional[float] = None
