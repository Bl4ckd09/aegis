"""Deterministic business-rates relief engine — England 2026/27.

LLM BOUNDARY: This module computes all £ figures. The LLM never calls
assess() and never modifies these outputs. All numbers trace to gov.uk.

Sources:
  Multipliers:    gov.uk notification 2/2026
  SBRR:          gov.uk/apply-for-business-rate-relief/small-business-rate-relief
  Pub/live music: gov.uk publication 1/2026
  SSB 2026:      gov.uk SSB LA guidance 2026
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# 2026/27 multipliers — pence per £1 RV (notification 2/2026)
MULT_SB_NON_RHL  = 0.432   # small-business, not RHL use
MULT_SB_RHL      = 0.382   # small-business, RHL use  (RV < £51k)
MULT_STD_NON_RHL = 0.480   # standard, not RHL
MULT_STD_RHL     = 0.430   # standard, RHL use         (RV £51k–£499k)
MULT_HIGH        = 0.508   # high-value                (RV ≥ £500k)

# Retail/Hospitality/Leisure sectors → lower multiplier
RHL_SECTORS = {"retail", "cafe", "pub", "hospitality", "leisure"}

# Pub/live-music relief: ONLY these qualify for 15% extra
PUB_QUALIFYING = {"pub"}

# Explicitly excluded from pub/live-music relief (per gov.uk 1/2026)
PUB_EXCLUDED = {
    "cafe", "restaurant", "nightclub", "hotel", "guesthouse",
    "snack_bar", "sporting", "festival", "theatre", "cinema",
    "museum", "exhibition", "casino",
}

Sector = Literal["retail", "cafe", "pub", "hospitality", "office", "industrial", "leisure", "other"]


@dataclass
class Business:
    name: str
    rateable_value: float
    borough: str
    sector: Sector
    uarn: str = ""
    address: str = ""
    postcode: str = ""
    composite: bool = False


@dataclass
class ReliefFinding:
    headline: str
    annual_value: float       # £/yr this relief saves
    backdated_value: float    # £ lump (conservative 3-yr estimate from Apr 2023)
    confidence: Literal["high", "medium", "low"]
    rule: str
    action: str
    explanation: str
    source: str


def _multiplier(rv: float, sector: str) -> float:
    is_rhl = sector in RHL_SECTORS
    if rv >= 500_000:
        return MULT_HIGH
    elif rv >= 51_000:
        return MULT_STD_RHL if is_rhl else MULT_STD_NON_RHL
    else:
        return MULT_SB_RHL if is_rhl else MULT_SB_NON_RHL


def _gross_bill(rv: float, sector: str) -> float:
    return rv * _multiplier(rv, sector)


def _sbrr_pct(rv: float) -> float:
    """Return SBRR discount fraction (0.0–1.0). 1% per £30 over £12,000 taper."""
    if rv <= 12_000:
        return 1.0
    elif rv < 15_000:
        steps = (rv - 12_000) / 30.0
        return max(0.0, 1.0 - steps * 0.01)
    return 0.0


def assess(biz: Business) -> list[ReliefFinding]:
    """Return all applicable relief findings for a business. Never raises."""
    findings: list[ReliefFinding] = []
    rv = biz.rateable_value
    gross = _gross_bill(rv, biz.sector)

    # ── SBRR ────────────────────────────────────────────────────────────
    pct = _sbrr_pct(rv)
    if pct > 0.0:
        saving = gross * pct
        findings.append(ReliefFinding(
            headline=f"Small Business Rate Relief — {pct * 100:.0f}% off",
            annual_value=round(saving, 2),
            backdated_value=round(saving * 3, 2),
            confidence="high",
            rule="SBRR 2026/27",
            action=(
                "Apply to your billing authority (council) — it is NOT automatic. "
                "Ask them to backdate to April 2023 (start of current rating list). "
                "Some councils backdate further — always ask."
            ),
            explanation=(
                f"RV £{rv:,.0f} qualifies for {pct * 100:.0f}% SBRR on a "
                f"gross bill of £{gross:,.0f}/yr, saving £{saving:,.0f}/yr. "
                "Councils typically backdate to April 2023 (start of 2023 rating list) "
                "— 3 years of unclaimed relief shown here as a conservative estimate."
            ),
            source="https://www.gov.uk/apply-for-business-rate-relief/small-business-rate-relief",
        ))

    # ── 2026 revaluation challenge wedge ────────────────────────────────
    if 12_000 < rv <= 16_000:
        findings.append(ReliefFinding(
            headline="2026 Revaluation — possible challenge",
            annual_value=0.0,
            backdated_value=0.0,
            confidence="medium",
            rule="2026 Revaluation challenge wedge",
            action="Check via gov.uk/business-rates-valuation-account.",
            explanation=(
                f"RV £{rv:,.0f} is near the SBRR cliff (£12k/£15k). "
                "The April 2026 revaluation may have pushed you just over — "
                "a challenge could restore full or partial relief."
            ),
            source="https://www.gov.uk/business-rates-valuation-account",
        ))

    # ── Pub & live music relief ──────────────────────────────────────────
    if biz.sector in PUB_QUALIFYING and biz.sector not in PUB_EXCLUDED:
        pub_saving = gross * 0.15
        findings.append(ReliefFinding(
            headline="Pub & Live Music Venue Relief — 15% off",
            annual_value=round(pub_saving, 2),
            backdated_value=round(pub_saving, 2),  # 2026/27 only
            confidence="high",
            rule="Pub/live-music relief 2026/27 (gov.uk 1/2026)",
            action="Verify your bill — billing authority should apply automatically.",
            explanation=(
                f"Qualifying pub: 15% off gross bill (£{gross:,.0f}/yr → "
                f"saving £{pub_saving:,.0f}/yr for 2026/27)."
            ),
            source=(
                "https://www.gov.uk/government/publications/"
                "12026-pubs-and-live-music-venues-relief-2026-to-2027/"
                "12026-pubs-and-live-music-venues-relief-2026-to-2027"
            ),
        ))

    # ── City of London flag ──────────────────────────────────────────────
    if "city of london" in biz.borough.lower():
        findings.append(ReliefFinding(
            headline="City of London — special arrangements apply",
            annual_value=0.0,
            backdated_value=0.0,
            confidence="low",
            rule="City of London special arrangements",
            action="Contact the City of London Corporation for your relief position.",
            explanation=(
                "The City of London has separate billing authority arrangements. "
                "No national figure is asserted — verify locally."
            ),
            source="https://www.cityoflondon.gov.uk/business/business-rates",
        ))

    return findings
