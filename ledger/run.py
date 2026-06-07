#!/usr/bin/env python3
"""LEDGER CLI — look up what a London business is owed in rates relief."""

import argparse
import json
import os
import sys

from agent.pipeline import run, run_by_name


def main() -> int:
    parser = argparse.ArgumentParser(description="LEDGER — what your business is owed")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--postcode", "-p", help="London postcode, e.g. E8 1DY")
    group.add_argument("--name", "-n", help="Business name (requires COMPANIES_HOUSE_KEY)")
    parser.add_argument("--key", help="Companies House API key (or set COMPANIES_HOUSE_KEY)")
    args = parser.parse_args()

    if args.key:
        os.environ["COMPANIES_HOUSE_KEY"] = args.key

    if args.postcode:
        result = run(args.postcode)
    else:
        result = run_by_name(args.name)

    # Pretty print findings
    businesses = result.get("businesses", [])
    if not businesses:
        print(f"No results: {result.get('error', 'unknown error')}")
        if "candidates" in result:
            print("\nCompanies House candidates found (no VOA match for their postcode):")
            for c in result["candidates"]:
                print(f"  {c['name']} | {c['postcode']} | {c['address']}")
        return 1

    print(f"\n{'='*60}")
    print(f"LEDGER — Relief Finder")
    print(f"Query: {result['query']}  |  LSOA: {result.get('lsoa') or 'n/a'}")
    print(f"{'='*60}")
    print(f"Found {len(businesses)} property/properties at this postcode\n")

    for b in businesses:
        total = b["totals"]["total_annual_savings"]
        if total == 0 and not b["findings"]:
            continue  # skip no-relief silently unless it's the only one

        print(f"  {b['name']}")
        print(f"  {b['address']}  |  RV £{b['rateable_value']:,.0f}  |  {b['borough']}")
        if b["findings"]:
            for f in b["findings"]:
                if f["annual_value"]:
                    print(f"  ✓ {f['headline']}: £{f['annual_value']:,.0f}/yr  (backdated est. £{f['backdated_value']:,.0f})")
                else:
                    print(f"  ⚠ {f['headline']}")
            print(f"  → TOTAL SAVING: £{total:,.0f}/yr")
        else:
            print(f"  No relief applicable (RV £{b['rateable_value']:,.0f} above thresholds)")
        print()

    # Also dump raw JSON for the agent layer
    if "--json" in sys.argv:
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
