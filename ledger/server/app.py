"""STELLA web server — Flask UI for the money engine."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from agent.pipeline import run, run_by_name

app = Flask(__name__)

CH_KEY = os.environ.get("COMPANIES_HOUSE_KEY", "")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/lookup", methods=["POST"])
def lookup():
    data = request.json or {}
    query = (data.get("query") or "").strip()
    sector_override = (data.get("sector") or "").strip() or None

    if not query:
        return jsonify({"error": "Please enter a postcode or business name"}), 400

    # Detect postcode vs name
    import re
    is_postcode = bool(re.match(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}$", query, re.I))

    if is_postcode:
        result = run(query.upper())
    else:
        if not CH_KEY:
            return jsonify({"error": "Business name lookup requires COMPANIES_HOUSE_KEY — use a postcode instead"}), 400
        result = run_by_name(query, api_key=CH_KEY)

    # Apply sector override to first business if requested
    if sector_override and result.get("businesses"):
        from engines.rules_relief import Business, assess, _gross_bill
        from dataclasses import asdict
        b = result["businesses"][0]
        rv = b["rateable_value"]
        biz = Business(
            name=b["name"], rateable_value=rv, borough=b["borough"],
            sector=sector_override, uarn=b["uarn"], address=b["address"], postcode=b["postcode"]
        )
        findings = assess(biz)
        total = sum(f.annual_value for f in findings)
        back  = sum(f.backdated_value for f in findings)
        confs = [f.confidence for f in findings]
        highest = "high" if "high" in confs else ("medium" if "medium" in confs else ("low" if confs else "none"))
        b["sector"] = sector_override
        b["gross_annual_bill"] = round(_gross_bill(rv, sector_override), 2)
        b["findings"] = [asdict(f) for f in findings]
        b["totals"] = {"total_annual_savings": round(total, 2),
                       "total_backdated": round(back, 2), "highest_confidence": highest}

    return jsonify(result)


def _name_score(query: str, result: str) -> int:
    """Score how well a CH company name matches the user's query (0-100)."""
    q, r = query.lower().strip(), result.lower().strip()
    if q == r:                          return 100
    if q in r or r.startswith(q):      return 85
    tokens = q.split()
    matched = sum(1 for t in tokens if t in r and len(t) > 2)
    return int(matched / max(len(tokens), 1) * 70)


def _name_to_sector(name: str) -> str | None:
    """Infer sector from business name when SIC codes are absent."""
    n = name.lower()
    cafe_words  = ("coffee","cafe","café","espresso","bistro","restaurant","kitchen",
                   "bakery","deli","diner","pizz","sushi","noodle","taco","burrito","kebab")
    pub_words   = ("pub","bar","inn","tavern","brewery","tap room","ale house")
    hotel_words = ("hotel","hostel","guest house","b&b","bed and breakfast","lodge","motel")
    leisure_words=("gym","fitness","yoga","pilates","sport","dance","studio","leisure","spa","clinic")
    retail_words= ("shop","store","boutique","market","gallery","jewel","fashion","florist")
    if any(w in n for w in cafe_words):   return "cafe"
    if any(w in n for w in pub_words):    return "pub"
    if any(w in n for w in hotel_words):  return "hospitality"
    if any(w in n for w in leisure_words):return "leisure"
    if any(w in n for w in retail_words): return "retail"
    return None


def _sic_to_sector(sic_codes: list[str]) -> str | None:
    """Derive VOA sector from Companies House SIC codes."""
    for code in sic_codes:
        num = code.split()[0].strip()
        if num.startswith(("561", "562")):       return "cafe"      # restaurants, cafes, takeaway
        if num.startswith(("563",)):             return "pub"       # bars/pubs
        if num.startswith(("55",)):              return "hospitality"
        if num.startswith(("47",)):              return "retail"
        if num.startswith(("46",)):              return "retail"    # wholesale → proxy retail
        if num.startswith(("931", "932", "933")): return "leisure"  # sports/recreation
        if num.startswith(("90", "91")):         return "leisure"   # arts/entertainment
        if num.startswith(("10", "11", "12", "13", "14", "15", "16",
                            "17", "18", "20", "21", "22", "23", "24",
                            "25", "26", "27", "28", "29", "30", "31",
                            "32", "33")):        return "industrial"
    return None


def _apply_sector_override(prop: dict, sector: str) -> dict:
    from engines.rules_relief import Business, assess, _gross_bill
    from dataclasses import asdict
    rv = prop["rateable_value"]
    biz_obj = Business(
        name=prop["name"], rateable_value=rv, borough=prop["borough"],
        sector=sector, uarn=prop["uarn"], address=prop["address"], postcode=prop["postcode"]
    )
    findings = assess(biz_obj)
    total = sum(f.annual_value for f in findings)
    back  = sum(f.backdated_value for f in findings)
    confs = [f.confidence for f in findings]
    highest = "high" if "high" in confs else ("medium" if "medium" in confs else "none")
    prop = dict(prop)
    prop["sector"] = sector
    prop["gross_annual_bill"] = round(_gross_bill(rv, sector), 2)
    prop["findings"] = [asdict(f) for f in findings]
    prop["totals"] = {"total_annual_savings": round(total, 2),
                      "total_backdated": round(back, 2), "highest_confidence": highest}
    return prop


@app.route("/api/biz-profile", methods=["POST"])
def biz_profile():
    """My Business: name + postcode → verify company → match VOA property → analysis + grants."""
    import re
    from datetime import date

    data          = request.json or {}
    biz_name      = (data.get("name") or "").strip()
    postcode      = (data.get("postcode") or "").strip().upper()
    sector_over   = (data.get("sector") or "").strip() or None
    selected_uarn = (data.get("uarn") or "").strip()

    if not biz_name:
        return jsonify({"error": "Business name required"}), 400
    if not postcode:
        return jsonify({"error": "Postcode required"}), 400
    if not re.match(r"^[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}$", postcode, re.I):
        return jsonify({"error": "Invalid postcode — use format e.g. EC1N 7TE"}), 400

    # ── 1. Companies House: verify the company ────────────────────────────────
    ch_profile: dict = {}
    sic_codes: list  = []
    company_age_years = None
    company_type = ""
    ch_verification = "not_found"   # "verified" | "likely" | "name_only" | "not_found"
    ch_note = ""

    if CH_KEY:
        try:
            from data.ingest_companies import search_by_name
            candidates = search_by_name(biz_name, CH_KEY, items_per_page=10)
            pc_norm = postcode.replace(" ", "").upper()

            # Score each candidate by name match + postcode match
            scored = []
            for c in candidates:
                ns = _name_score(biz_name, c.get("name", ""))
                pc_match = c.get("postcode", "").replace(" ", "").upper() == pc_norm
                scored.append((ns + (20 if pc_match else 0), pc_match, c))

            scored.sort(key=lambda x: -x[0])

            if scored and scored[0][0] >= 50:  # minimum name similarity threshold
                score, pc_match, best = scored[0]
                # Always fetch full profile — search results never include SIC codes
                from data.ingest_companies import get_by_number
                full = get_by_number(best["company_number"], CH_KEY) if best.get("company_number") else None
                if full:
                    best = {**best, **full}  # merge: full profile wins
                ch_profile   = best
                sic_codes    = best.get("sic_codes", [])
                company_type = best.get("status", "")
                created      = best.get("date_of_creation", "")
                if created:
                    try:
                        company_age_years = date.today().year - int(created[:4])
                    except (ValueError, TypeError):
                        pass

                if score >= 100 and pc_match:
                    ch_verification = "verified"
                    ch_note = "Name and postcode match Companies House records."
                elif score >= 85:
                    ch_verification = "likely"
                    ch_note = f"Strong name match. Registered address: {best.get('address','unknown')} — may differ from trading address."
                else:
                    ch_verification = "name_only"
                    ch_note = f"Partial name match. Registered at {best.get('postcode','unknown')}. Trading address may differ."
            elif scored:
                ch_note = f"No close match found. Closest: '{scored[0][2].get('name','')}' — check the spelling."
        except Exception as e:
            ch_note = f"Companies House lookup failed: {e}"

    # Fallback: local bulk index (postcode first, then FTS name search)
    if not sic_codes:
        try:
            from data.ingest_companies_local import search_by_postcode, search_by_name_local
            local_cos = search_by_postcode(postcode)
            if not local_cos:
                local_cos = search_by_name_local(biz_name)
            if local_cos:
                local_cos.sort(key=lambda c: -_name_score(biz_name, c["name"]))
                if _name_score(biz_name, local_cos[0]["name"]) >= 50:
                    c = local_cos[0]
                    sic_codes = [s for s in [c.get("sic1",""), c.get("sic2","")] if s]
                    if not ch_profile:
                        ch_profile = {"name": c["name"], "number": c["company_number"],
                                      "status": c["status"], "sic_codes": sic_codes}
                    if not company_age_years and c.get("date_of_creation"):
                        try:
                            company_age_years = date.today().year - int(c["date_of_creation"][:4])
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass

    # Derive sector: user override → SIC codes → company name inference
    effective_sector = (sector_over
                        or _sic_to_sector(sic_codes)
                        or _name_to_sector(ch_profile.get("name", "") or biz_name))

    # ── 2. VOA: all properties at postcode ────────────────────────────────────
    voa_result = run(postcode)
    all_props  = voa_result.get("businesses", [])

    if not all_props:
        return jsonify({"error": f"No properties found at {postcode} in the VOA 2026 rating list. Check the postcode is correct."}), 404

    # ── 3. Auto-select property ───────────────────────────────────────────────
    if not selected_uarn:
        # Filter by effective sector (SIC-derived or user-specified)
        sector_matches = [b for b in all_props if b.get("sector") == effective_sector] if effective_sector else []
        pool = sector_matches if sector_matches else all_props

        # Sort: savings first, then smallest RV (most likely to be an SME occupier)
        pool.sort(key=lambda b: (-b["totals"]["total_annual_savings"], b["rateable_value"]))

        with_savings = [b for b in pool if b["totals"]["total_annual_savings"] > 0]

        if len(pool) == 1:
            selected_uarn = pool[0]["uarn"]
        elif len(with_savings) == 1:
            selected_uarn = with_savings[0]["uarn"]  # exactly one in sector has savings
        elif len(with_savings) == 0 and len(pool) == 1:
            selected_uarn = pool[0]["uarn"]
        else:
            # Genuine ambiguity — show compact picker (sector-filtered only)
            return jsonify({
                "step":              "pick_property",
                "properties":        pool,
                "ch_profile":        ch_profile or None,
                "ch_verification":   ch_verification,
                "ch_note":           ch_note,
                "sic_codes":         sic_codes,
                "company_age_years": company_age_years,
                "biz_name":          biz_name,
                "postcode":          postcode,
                "sector":            effective_sector,
                "reason":            f"Found {len(pool)} {effective_sector or ''} premises at {postcode} — which is yours?",
            })

    # ── 4. Full analysis on selected property ─────────────────────────────────
    prop_map = {b["uarn"]: b for b in all_props}
    prop = prop_map.get(selected_uarn)
    if not prop:
        return jsonify({"error": f"Property not found at {postcode} — try again"}), 404

    if effective_sector and effective_sector != prop["sector"]:
        prop = _apply_sector_override(prop, effective_sector)

    from engines.rules_grants import match_grants
    grants = match_grants(
        sector=prop["sector"],
        sic_codes=sic_codes,
        borough=prop["borough"],
        rateable_value=prop["rateable_value"],
        company_age_years=company_age_years,
        company_type=company_type,
    )

    from data.borough_contacts import get_contact
    borough = (prop.get("borough") or "").lower()
    council = get_contact(borough)

    return jsonify({
        "step":              "analysis",
        "property":          prop,
        "biz_name":          biz_name,
        "ch_profile":        ch_profile or None,
        "ch_verification":   ch_verification,
        "ch_note":           ch_note,
        "sic_codes":         sic_codes,
        "company_age_years": company_age_years,
        "grants":            grants,
        "lsoa":              voa_result.get("lsoa"),
        "council":           council,
    })


@app.route("/api/draft-email", methods=["POST"])
def draft_email():
    data = request.json or {}
    business = data.get("business", {})
    finding_lines = "\n".join(
        f"- {f['headline']}: £{f['annual_value']:,.0f}/yr"
        for f in business.get("findings", []) if f.get("annual_value")
    )
    prompt = (
        f"Write a professional email under 120 words from the owner of a small business "
        f"to their council claiming business rates relief. "
        f"Address: {business.get('address')}. UARN: {business.get('uarn')}. "
        f"Borough: {business.get('borough')}. RV: £{business.get('rateable_value',0):,.0f}. "
        f"Relief: {finding_lines}. Include UARN. End with [Your name]."
    )
    def generate():
        try:
            from agent.llm import stream_chat
            for chunk in stream_chat(prompt):
                yield f"data: {json.dumps({'t': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/draft-grant", methods=["POST"])
def draft_grant():
    data    = request.json or {}
    grant   = data.get("grant", {})
    biz     = data.get("business", {})
    mode    = data.get("mode", "email")  # "email" or "steps"
    if mode == "email":
        prompt = (
            f"Write a professional email under 100 words from the owner of "
            f"{biz.get('name','our business')}, a {biz.get('sector','')} in {biz.get('borough','London')}, "
            f"to {grant.get('funder')} applying for {grant.get('name')} ({grant.get('value')}). "
            f"Eligible because: {', '.join(grant.get('match_reasons',[]))}. "
            f"Company age {biz.get('company_age_years','')} years. End with [Your name]."
        )
    else:
        prompt = (
            f"Give 5 numbered action steps to apply for {grant.get('name')} from {grant.get('funder')}. "
            f"Include documents needed, URL ({grant.get('url')}), deadline ({grant.get('deadline')}). "
            f"Be specific and brief."
        )
    def generate():
        try:
            from agent.llm import stream_chat
            for chunk in stream_chat(prompt):
                yield f"data: {json.dumps({'t': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"
    return Response(stream_with_context(generate()), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/insights", methods=["POST"])
def insights():
    """Extra insights for My Business: RV cliff, sector peers, deprivation, aggregate stats."""
    import csv as _csv
    data   = request.json or {}
    rv     = float(data.get("rateable_value", 0))
    sector = (data.get("sector") or "").lower()
    borough= (data.get("borough") or "").lower()
    postcode = (data.get("postcode") or "").upper()
    cards  = []

    # ── 1. London-wide unclaimed stat ────────────────────────────────────────
    cards.append({
        "type": "stat",
        "icon": "💰",
        "title": "£536M unclaimed across London",
        "body": "117,188 London properties qualify for Small Business Rate Relief but most owners never applied. STELLA found yours.",
        "color": "#4ade80",
    })

    # ── 2. RV cliff warning ───────────────────────────────────────────────────
    if 12_000 < rv <= 13_500:
        gap = rv - 12_000
        cards.append({
            "type": "alert",
            "icon": "⚠",
            "title": f"You're £{gap:,.0f} above the full-relief threshold",
            "body": f"RV £{rv:,.0f} is just above £12,000. A successful 2026 revaluation appeal could drop you below and unlock 100% SBRR — saving ~£{rv*0.382:,.0f}/yr. You have until 31 March 2027 to appeal.",
            "color": "#facc15",
            "action": "Check appeal at gov.uk/business-rates-valuation-account",
            "action_url": "https://www.gov.uk/business-rates-valuation-account",
        })
    elif 15_000 < rv <= 17_000:
        cards.append({
            "type": "alert",
            "icon": "⚠",
            "title": f"Just above tapered relief — appeal could save money",
            "body": f"RV £{rv:,.0f} is above £15,000 so no SBRR applies. An appeal to reduce RV below £15k could unlock tapered relief. Deadline: 31 March 2027.",
            "color": "#f97316",
            "action": "Appeal your RV",
            "action_url": "https://www.gov.uk/business-rates-valuation-account",
        })

    # ── 3. Sector peer comparison ─────────────────────────────────────────────
    if sector and rv > 0:
        try:
            peer_rvs = []
            with open(Path(__file__).parent.parent / "data" / "voa_london_index.csv") as f:
                for row in _csv.DictReader(f):
                    if row.get("sector","").lower() == sector:
                        b = row.get("borough","").lower()
                        if borough and b != borough:
                            continue
                        try:
                            peer_rvs.append(float(row["rateable_value"]))
                        except (ValueError, KeyError):
                            pass
                    if len(peer_rvs) >= 5000:
                        break
            if len(peer_rvs) >= 10:
                peer_rvs.sort()
                median = peer_rvs[len(peer_rvs)//2]
                pct = sum(1 for p in peer_rvs if p <= rv) / len(peer_rvs) * 100
                location = borough.title() if borough else "London"
                if rv < median * 0.8:
                    verdict = f"Your RV is well below the median — you're in the bottom {pct:.0f}% for your sector. Good position for relief."
                    col = "#4ade80"
                elif rv > median * 1.3:
                    verdict = f"Your RV is above the median — consider a 2026 revaluation appeal to benchmark against peers."
                    col = "#f97316"
                else:
                    verdict = f"Your RV is close to the {location} median for {sector}s."
                    col = "#60a5fa"
                cards.append({
                    "type": "peer",
                    "icon": "📊",
                    "title": f"Your RV vs {len(peer_rvs):,} {sector}s in {location}",
                    "body": f"Median {sector} RV in {location}: £{median:,.0f}. Yours: £{rv:,.0f}. {verdict}",
                    "color": col,
                })
        except Exception:
            pass

    return jsonify({"insights": cards})


@app.route("/api/companies-at", methods=["POST"])
def companies_at():
    """Return Companies House records at a postcode. Local DB first, API fallback."""
    data = request.json or {}
    postcode = (data.get("postcode") or "").strip().upper()
    if not postcode:
        return jsonify({"companies": [], "total": 0})

    # ── Local index (offline / DGX Spark mode) ────────────────────────────────
    try:
        from data.ingest_companies_local import search_by_postcode
        local = search_by_postcode(postcode)
        if local:
            companies = [{
                "name":             r["name"],
                "number":           r["company_number"],
                "status":           r["status"],
                "sic_codes":        [s for s in [r.get("sic1",""), r.get("sic2","")] if s],
                "date_of_creation": r.get("date_of_creation", ""),
                "address":          r.get("address", ""),
                "source":           "local",
            } for r in local]
            return jsonify({"companies": companies, "total": len(companies), "source": "local"})
    except (ImportError, Exception):
        pass

    # ── Companies House API fallback ───────────────────────────────────────────
    if not CH_KEY:
        return jsonify({"companies": [], "total": 0, "error": "no_key"})

    import base64, urllib.request, urllib.parse, json as _json
    try:
        url = (
            "https://api.company-information.service.gov.uk/advanced-search/companies"
            f"?location={urllib.parse.quote(postcode)}&items_per_page=20"
        )
        token = base64.b64encode(f"{CH_KEY}:".encode()).decode()
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = _json.load(resp)
        companies = []
        for item in raw.get("items", []):
            addr = item.get("registered_office_address", {})
            companies.append({
                "name":             item.get("company_name", ""),
                "number":           item.get("company_number", ""),
                "status":           item.get("company_status", ""),
                "sic_codes":        item.get("sic_codes", []),
                "date_of_creation": item.get("date_of_creation", ""),
                "address": ", ".join(filter(None, [
                    addr.get("address_line_1", ""), addr.get("address_line_2", ""),
                    addr.get("locality", ""), addr.get("postal_code", ""),
                ])),
                "source": "api",
            })
        return jsonify({"companies": companies, "total": raw.get("hits", len(companies)), "source": "api"})
    except Exception as exc:
        return jsonify({"companies": [], "total": 0, "error": str(exc)})


@app.route("/api/grants", methods=["POST"])
def grants():
    data = request.json or {}
    from engines.rules_grants import match_grants
    matched = match_grants(
        sector=data.get("sector", "other"),
        sic_codes=data.get("sic_codes", []),
        borough=data.get("borough", ""),
        rateable_value=float(data.get("rateable_value", 0)),
        company_age_years=data.get("company_age_years"),
        company_type=data.get("company_type", ""),
    )
    return jsonify({"grants": matched})


def _static_grants(sector: str, borough: str) -> list[dict]:
    """Curated always-on grants for London small businesses."""
    grants = [
        {
            "name": "UK Shared Prosperity Fund — Small Business Support",
            "value": "Up to £25,000",
            "who": "London small businesses, especially in priority areas",
            "action": "Contact your borough council's economic development team",
            "url": "https://www.gov.uk/government/publications/uk-shared-prosperity-fund-prospectus",
            "confidence": "high",
        },
        {
            "name": "Start Up Loan (British Business Bank)",
            "value": "£500–£25,000 at 6% fixed",
            "who": "Businesses trading under 3 years",
            "action": "Apply at startuploans.co.uk",
            "url": "https://www.startuploans.co.uk/",
            "confidence": "high",
        },
        {
            "name": "GLA Good Growth Fund",
            "value": "£100k–£2M (community/cultural focus)",
            "who": "Businesses in regeneration areas, community benefit",
            "action": "Check current rounds at london.gov.uk/programmes-strategies/arts-culture/funding",
            "url": "https://www.london.gov.uk/programmes-strategies/arts-culture/funding",
            "confidence": "medium",
        },
        {
            "name": "London Growth Hub — Business Support",
            "value": "Free advice + matched funding referral",
            "who": "All London SMBs",
            "action": "Register at londongrowthub.co.uk",
            "url": "https://www.londongrowthub.co.uk/",
            "confidence": "high",
        },
    ]
    if sector in ("cafe", "pub", "hospitality", "retail"):
        grants.append({
            "name": "Hospitality & Retail Energy Efficiency Grant",
            "value": "Up to £5,000 (varies by borough)",
            "who": "Food & drink and retail businesses, energy efficiency works",
            "action": "Contact your borough council's sustainability team",
            "url": "https://www.find-government-grants.service.gov.uk/",
            "confidence": "medium",
        })
    if "hackney" in borough.lower() or "tower hamlets" in borough.lower() or "newham" in borough.lower():
        grants.append({
            "name": "East London Business Place Grant",
            "value": "Up to £10,000",
            "who": "East London SMBs — Hackney, Tower Hamlets, Newham priority",
            "action": "Contact ELBP directly",
            "url": "https://elbp.co.uk/",
            "confidence": "medium",
        })
    return grants


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"STELLA running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
