"""Verify a real business against the VOA index — runs engine on ALL matches.

Usage:
    python3 data/verify_business.py "E8 1DY"
    python3 data/verify_business.py "EC1N 7TE" --name "Prufrock Coffee"
    python3 data/verify_business.py "EC1N 7TE" --uarn 01042003930015   # target specific property
    python3 data/verify_business.py "E8 1DY" --sector cafe             # override sector on first match

Cross-check RV at: https://www.gov.uk/correct-your-business-rates
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.pipeline import _lookup_postcode
from engines.rules_relief import Business, assess, _gross_bill


def main() -> None:
    parser = argparse.ArgumentParser(description="STELLA — verify a real business end-to-end")
    parser.add_argument("postcode", nargs="+", help="Postcode e.g. E8 1DY")
    parser.add_argument("--name",   default="", help="Business name (display only)")
    parser.add_argument("--uarn",   default="", help="Target a specific UARN from the list")
    parser.add_argument("--sector", help="Override sector for the targeted entry")
    args = parser.parse_args()

    postcode = " ".join(args.postcode)

    print(f"\n{'='*60}")
    print("STELLA — Verification Report")
    print(f"Postcode : {postcode}" + (f"  ({args.name})" if args.name else ""))
    print(f"{'='*60}\n")

    matches = _lookup_postcode(postcode)
    if not matches:
        print(f"No VOA entries found for {postcode}")
        print("Check: https://www.gov.uk/correct-your-business-rates")
        sys.exit(1)

    # Filter to specific UARN if requested
    if args.uarn:
        matches = [m for m in matches if m["uarn"] == args.uarn]
        if not matches:
            print(f"UARN {args.uarn} not found at {postcode}. Run without --uarn to see all.")
            sys.exit(1)

    found_savings = False

    for m in matches:
        rv     = m["rateable_value"]
        sector = args.sector if (args.sector and (not args.uarn or m["uarn"] == args.uarn)) else m["sector"]
        borough = m["borough"]

        biz = Business(
            name=m.get("desc_text", ""),
            rateable_value=rv,
            borough=borough,
            sector=sector,
            uarn=m.get("uarn", ""),
            address=m.get("address", ""),
            postcode=m.get("postcode", ""),
        )
        findings = assess(biz)
        gross    = _gross_bill(rv, sector)
        total    = sum(f.annual_value for f in findings)
        back     = sum(f.backdated_value for f in findings)

        # Highlight rows with savings
        flag = "  💰 " if total > 0 else "     "
        print(f"{flag}{m['desc_text']}")
        print(f"     UARN: {m['uarn']}  |  RV: £{rv:,.0f}  |  Sector: {sector}  |  Gross bill: £{gross:,.0f}/yr")
        print(f"     Address: {m['address']}")

        if findings:
            for f in findings:
                if f.annual_value:
                    print(f"     ✓ {f.headline}: £{f.annual_value:,.0f}/yr  (backdated ~£{f.backdated_value:,.0f})")
                else:
                    print(f"     ⚠  {f.headline}")
            if total:
                print(f"     → TOTAL: £{total:,.0f}/yr saving  |  backdated ~£{back:,.0f}")
                found_savings = True
        else:
            print(f"     No relief (RV above SBRR threshold, not a qualifying pub)")
        print()

    if found_savings:
        print("NEXT STEP: confirm the RV at https://www.gov.uk/correct-your-business-rates")
        print("Then contact the billing authority to claim — reference the UARN above.")
    else:
        print("No relief found for any property at this postcode.")
        print("If you know the specific property, run with --uarn <UARN> --sector <sector>")


if __name__ == "__main__":
    main()
