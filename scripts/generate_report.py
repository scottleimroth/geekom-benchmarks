#!/usr/bin/env python3
"""Phase 13 report generator. Reads all raw JSONL -> summaries -> HTML.

Usage:
  python scripts/generate_report.py
  python scripts/generate_report.py --open
"""
import _bootstrap  # noqa: F401
import argparse
import os
import webbrowser

from geekom_benchmarks.reporting.report import generate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true", help="open the HTML report in a browser")
    args = ap.parse_args()

    out = generate()
    print("Wrote:")
    for k, v in out.items():
        print(f"  {k:14} {v}")
    if args.open:
        try:
            webbrowser.open(out["html_latest"].as_uri())
        except Exception as e:
            print(f"(could not auto-open: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
