"""Grant eligibility engine — deterministic rules against known UK/London programs.

Inputs:  sector, sic_codes, borough, rateable_value, company_age_years, company_type
Outputs: list of GrantMatch with eligibility verdict + action

Sources: findagrant.gov.uk, GOV.UK, GLA, British Business Bank, Innovate UK.
All eligibility criteria are from published program documentation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Eligibility = Literal["eligible", "likely", "check", "ineligible"]


@dataclass
class GrantMatch:
    name: str
    funder: str
    value: str
    eligibility: Eligibility
    match_reasons: list[str]
    blockers: list[str]
    action: str
    url: str
    deadline: str = "Rolling"


# ── SIC code helpers ─────────────────────────────────────────────────────────

def _sic_in(sic_codes: list[str], *prefixes: str) -> bool:
    for code in sic_codes:
        num = code.split()[0].strip() if code else ""
        if any(num.startswith(p) for p in prefixes):
            return True
    return False

def _is_tech(sic_codes: list[str]) -> bool:
    return _sic_in(sic_codes, "62", "63", "26", "27", "72")

def _is_creative(sic_codes: list[str]) -> bool:
    return _sic_in(sic_codes, "59", "60", "90", "91", "74")

def _is_manufacturing(sic_codes: list[str]) -> bool:
    return _sic_in(sic_codes, "10", "11", "13", "14", "15", "16", "17", "18",
                   "20", "21", "22", "23", "24", "25", "26", "27", "28", "29",
                   "30", "31", "32", "33")

def _is_food_drink(sic_codes: list[str]) -> bool:
    return _sic_in(sic_codes, "561", "562", "563", "101", "102", "103", "104",
                   "105", "106", "107", "108", "110")

def _is_professional(sic_codes: list[str]) -> bool:
    return _sic_in(sic_codes, "69", "70", "71", "73", "74", "75")

def _is_east_london(borough: str) -> bool:
    east = {"hackney", "tower hamlets", "newham", "waltham forest",
            "barking and dagenham", "redbridge", "havering"}
    return borough.lower() in east

def _is_outer_london(borough: str) -> bool:
    outer = {"barnet", "bexley", "bromley", "croydon", "ealing", "enfield",
             "harrow", "havering", "hillingdon", "hounslow", "kingston upon thames",
             "merton", "redbridge", "richmond upon thames", "sutton", "waltham forest",
             "barking and dagenham"}
    return borough.lower() in outer


def match_grants(
    sector: str,
    sic_codes: list[str] | None = None,
    borough: str = "",
    rateable_value: float = 0.0,
    company_age_years: float | None = None,
    company_type: str = "",
) -> list[dict]:
    """Return grant matches sorted by eligibility: eligible → likely → check."""
    sic_codes = sic_codes or []
    age = company_age_years
    results: list[GrantMatch] = []

    # ── 1. Start Up Loan ─────────────────────────────────────────────────────
    m1_reasons, m1_blockers = [], []
    if age is not None and age <= 3:
        m1_reasons.append(f"Business is {age:.0f} year(s) old — within 3-year window")
    elif age is not None and age > 3:
        m1_blockers.append(f"Business is {age:.0f} years old — typically for businesses trading < 3 years")
    else:
        m1_reasons.append("Eligibility depends on trading age — confirm with British Business Bank")

    results.append(GrantMatch(
        name="Start Up Loan",
        funder="British Business Bank (gov-backed)",
        value="£500–£25,000 at 6% fixed, + 12 months free mentoring",
        eligibility="eligible" if (age is not None and age <= 3) else ("check" if age is None else "ineligible"),
        match_reasons=m1_reasons,
        blockers=m1_blockers,
        action="Apply at startuploans.co.uk — decision in ~4 weeks",
        url="https://www.startuploans.co.uk/",
        deadline="Rolling",
    ))

    # ── 2. UK Shared Prosperity Fund (UKSPF) ─────────────────────────────────
    m2_reasons = ["Delivered via London boroughs — most London SMEs eligible"]
    m2_blockers = []
    m2_elig = "likely"
    if _is_outer_london(borough):
        m2_reasons.append(f"{borough} is a priority area for UKSPF funding")
        m2_elig = "eligible"
    if rateable_value > 0 and rateable_value < 51_000:
        m2_reasons.append(f"RV £{rateable_value:,.0f} — SME scale confirms eligibility")

    results.append(GrantMatch(
        name="UK Shared Prosperity Fund — Business Support",
        funder="HM Government via London Borough Councils",
        value="Up to £25,000 (varies by borough)",
        eligibility=m2_elig,
        match_reasons=m2_reasons,
        blockers=m2_blockers,
        action=f"Contact {borough or 'your'} Council economic development team",
        url="https://www.gov.uk/government/publications/uk-shared-prosperity-fund-prospectus",
        deadline="Rolling (borough-dependent)",
    ))

    # ── 3. London Growth Hub ─────────────────────────────────────────────────
    results.append(GrantMatch(
        name="London Growth Hub — Free Business Advice + Grant Referral",
        funder="GLA / Mayor of London",
        value="Free diagnostics + matched grant referral (up to £100k+)",
        eligibility="eligible",
        match_reasons=["All London SMEs with < 250 employees qualify",
                       "Advisers will identify additional grants you can apply for"],
        blockers=[],
        action="Register at londongrowthub.co.uk — free, no commitment",
        url="https://www.londongrowthub.co.uk/",
        deadline="Rolling",
    ))

    # ── 4. Innovate UK Smart Grants ──────────────────────────────────────────
    ik_reasons, ik_blockers = [], []
    ik_elig = "check"
    if _is_tech(sic_codes):
        ik_reasons.append(f"SIC codes suggest tech/digital business — strong fit")
        ik_elig = "likely"
    elif _is_manufacturing(sic_codes):
        ik_reasons.append("Manufacturing sector — eligible for product innovation funding")
        ik_elig = "likely"
    else:
        ik_reasons.append("Open to any sector with genuine R&D innovation element")
        ik_blockers.append("Must demonstrate innovation beyond existing technology")

    results.append(GrantMatch(
        name="Innovate UK Smart Grants",
        funder="UK Research & Innovation (UKRI)",
        value="£25,000–£500,000 (25%–100% match funded)",
        eligibility=ik_elig,
        match_reasons=ik_reasons,
        blockers=ik_blockers,
        action="Check open rounds at apply-for-innovation-funding.service.gov.uk",
        url="https://apply-for-innovation-funding.service.gov.uk/",
        deadline="Competitive rounds (quarterly)",
    ))

    # ── 5. R&D Tax Credits ───────────────────────────────────────────────────
    rd_reasons, rd_blockers = [], []
    rd_elig = "check"
    if _is_tech(sic_codes) or _is_manufacturing(sic_codes):
        rd_reasons.append("Sector typically undertakes qualifying R&D activities")
        rd_elig = "likely"
    rd_reasons.append("Applies if you spend money developing new products, processes, or software")
    rd_blockers.append("Must be a limited company paying Corporation Tax")

    if company_type.lower() not in ("ltd", "plc", "limited") and company_type:
        rd_blockers.append(f"Company type '{company_type}' may not qualify — needs to be Ltd/PLC")
        rd_elig = "check"

    results.append(GrantMatch(
        name="R&D Tax Credits (HMRC)",
        funder="HMRC",
        value="Up to 33p per £1 spent on R&D (SME scheme)",
        eligibility=rd_elig,
        match_reasons=rd_reasons,
        blockers=rd_blockers,
        action="Claim via Corporation Tax return — specialist accountant recommended",
        url="https://www.gov.uk/guidance/corporation-tax-research-and-development-rd-relief",
        deadline="2 years after end of accounting period",
    ))

    # ── 6. GLA Good Growth Fund ──────────────────────────────────────────────
    gg_reasons, gg_blockers = [], []
    gg_elig = "check"
    if _is_creative(sic_codes):
        gg_reasons.append("Creative/cultural sector is a priority for Good Growth Fund")
        gg_elig = "likely"
    if _is_east_london(borough):
        gg_reasons.append(f"{borough} is an East London priority area")
        gg_elig = "likely" if gg_elig == "check" else "eligible"
    if sector in ("leisure", "hospitality"):
        gg_reasons.append("Hospitality and leisure with community benefit may qualify")
    gg_blockers.append("Requires demonstrable community/cultural benefit — not purely commercial")

    results.append(GrantMatch(
        name="GLA Good Growth Fund",
        funder="Greater London Authority (Mayor of London)",
        value="£100,000–£2,000,000",
        eligibility=gg_elig,
        match_reasons=gg_reasons if gg_reasons else ["Check current round criteria"],
        blockers=gg_blockers,
        action="Check open rounds at london.gov.uk",
        url="https://www.london.gov.uk/programmes-strategies/arts-culture/funding",
        deadline="Competitive — check for open rounds",
    ))

    # ── 7. Hospitality / F&B Energy Efficiency ───────────────────────────────
    if sector in ("cafe", "pub", "hospitality") or _is_food_drink(sic_codes):
        results.append(GrantMatch(
            name="Hospitality Sector Energy Efficiency Grant",
            funder="London boroughs + DESNZ",
            value="Up to £5,000 (varies by borough)",
            eligibility="likely",
            match_reasons=[
                f"Sector ({sector}) is explicitly targeted",
                "High energy use in food prep/refrigeration makes this valuable",
            ],
            blockers=["Borough-specific — availability varies"],
            action="Contact your borough council sustainability/economic development team",
            url="https://www.find-government-grants.service.gov.uk/",
            deadline="Rolling (borough-dependent)",
        ))

    # ── 8. East London Business Place ───────────────────────────────────────
    if _is_east_london(borough):
        results.append(GrantMatch(
            name="East London Business Place (ELBP) Grant",
            funder="ELBP / GLA",
            value="Up to £10,000",
            eligibility="eligible",
            match_reasons=[
                f"{borough} is within ELBP's priority area",
                "Direct grant + free mentoring for local SMEs",
            ],
            blockers=[],
            action="Apply directly at elbp.co.uk",
            url="https://elbp.co.uk/",
            deadline="Rolling",
        ))

    # ── 9. Creative Enterprise Programme ─────────────────────────────────────
    if _is_creative(sic_codes) or sector in ("leisure",):
        results.append(GrantMatch(
            name="Creative Enterprise Programme (Arts Council / GLA)",
            funder="Arts Council England + GLA",
            value="£2,500–£15,000 + free business support",
            eligibility="likely",
            match_reasons=["Creative sector SIC codes detected"],
            blockers=["Must have cultural/creative mission — not purely commercial"],
            action="Check artscouncil.org.uk for open rounds",
            url="https://www.artscouncil.org.uk/funding",
            deadline="Competitive rounds",
        ))

    # ── 10. Net Zero / Decarbonisation ───────────────────────────────────────
    results.append(GrantMatch(
        name="Energy Bills Discount + Net Zero Business Support",
        funder="DESNZ / local energy hubs",
        value="Free energy audit + up to £5,000 for efficiency works",
        eligibility="check",
        match_reasons=["Available to all London SMEs — check local energy hub"],
        blockers=["Varies significantly by borough and scheme availability"],
        action="Check your borough's climate action team or businessclimatesupport.co.uk",
        url="https://www.businessclimatesupport.co.uk/",
        deadline="Rolling",
    ))

    # ── Sort: eligible → likely → check → ineligible ─────────────────────────
    order = {"eligible": 0, "likely": 1, "check": 2, "ineligible": 3}
    results.sort(key=lambda g: order[g.eligibility])

    return [
        {
            "name":          g.name,
            "funder":        g.funder,
            "value":         g.value,
            "eligibility":   g.eligibility,
            "match_reasons": g.match_reasons,
            "blockers":      g.blockers,
            "action":        g.action,
            "url":           g.url,
            "deadline":      g.deadline,
        }
        for g in results
        if g.eligibility != "ineligible"
    ]
