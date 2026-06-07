"""Canonical test cases — every number verified against gov.uk rules."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.rules_relief import Business, assess


def _find(findings, keyword):
    return next((f for f in findings if keyword.lower() in f.headline.lower()), None)


def test_hackney_cafe_full_sbrr():
    """RV £11,500 café → 100% SBRR → £4,393/yr, ~£26k backdated."""
    biz = Business("Test Café", rateable_value=11_500, borough="Hackney", sector="cafe")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is not None, "SBRR finding missing"
    assert abs(sbrr.annual_value - 4393.0) < 1.0, f"Expected ~£4393, got £{sbrr.annual_value}"
    assert sbrr.backdated_value > 26_000, "Backdated should be ~£26k+"
    assert sbrr.confidence == "high"


def test_shop_just_over_cliff():
    """RV £15,800 shop → no SBRR, but revaluation challenge flag."""
    biz = Business("Test Shop", rateable_value=15_800, borough="Hackney", sector="retail")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is None, "Should be NO SBRR above £15,000"
    challenge = _find(findings, "revaluation")
    assert challenge is not None, "Should flag 2026 revaluation challenge"


def test_pub_fifteen_percent():
    """RV £42,000 pub → 15% pub/live-music relief."""
    biz = Business("Test Pub", rateable_value=42_000, borough="Hackney", sector="pub")
    findings = assess(biz)
    pub = _find(findings, "pub")
    assert pub is not None, "Pub relief missing"
    # gross = 42000 * 0.382 = 16044; 15% = 2406.60
    assert abs(pub.annual_value - 2406.60) < 2.0, f"Expected ~£2407, got £{pub.annual_value}"


def test_cafe_no_pub_relief():
    """RV £28,000 café → NO pub/live-music relief (cafés explicitly excluded)."""
    biz = Business("Test Café 2", rateable_value=28_000, borough="Hackney", sector="cafe")
    findings = assess(biz)
    pub = _find(findings, "pub")
    assert pub is None, "Café must NOT receive pub/live-music relief"


def test_sbrr_taper_13500():
    """RV £13,500 → 50% SBRR taper (gov.uk worked example).
    retail = RHL sector → multiplier 0.382 (small-business RHL).
    gross = 13500 * 0.382 = 5157; 50% saving = 2578.50
    """
    biz = Business("Test", rateable_value=13_500, borough="Hackney", sector="retail")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is not None
    assert abs(sbrr.annual_value - 2_578.50) < 2.0, f"Expected ~£2578.50, got £{sbrr.annual_value}"


def test_sbrr_taper_14000():
    """RV £14,000 → ~33% SBRR taper (gov.uk worked example).
    retail = RHL sector → multiplier 0.382.
    steps = (14000-12000)/30 = 66.67; pct = 33.33%
    gross = 14000 * 0.382 = 5348; saving = 5348 * 0.3333 = 1782.67
    """
    biz = Business("Test", rateable_value=14_000, borough="Hackney", sector="retail")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is not None
    assert abs(sbrr.annual_value - 1_782.67) < 2.0, f"Expected ~£1782.67, got £{sbrr.annual_value}"


def test_city_of_london_flag():
    """City of London → flag only, no £ figure asserted."""
    biz = Business("Test", rateable_value=10_000, borough="City of London", sector="retail")
    findings = assess(biz)
    city = _find(findings, "city of london")
    assert city is not None
    assert city.annual_value == 0.0, "City of London: never assert a £ figure"


def test_high_value_no_sbrr():
    """RV ≥ £500k → no SBRR, no crash."""
    biz = Business("Big Office", rateable_value=600_000, borough="Westminster", sector="office")
    findings = assess(biz)
    sbrr = _find(findings, "small business rate relief")
    assert sbrr is None
