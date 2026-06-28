#!/usr/bin/env python3
"""Phase 15 historical comparison between two runs (speed tok/s + tool deltas).

Usage:
  python scripts/compare_runs.py --list
  python scripts/compare_runs.py --a speed_20260625-2310 --b speed_20260626-0110
"""
import _bootstrap  # noqa: F401
import argparse
import json

from geekom_benchmarks.reporting.report import compare_runs, load_all_raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a")
    ap.add_argument("--b")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list or not (args.a and args.b):
        runs = sorted({r.get("run_id") for r in load_all_raw() if r.get("run_id")})
        print("Available run_ids:")
        for r in runs:
            print(f"  {r}")
        if not (args.a and args.b):
            print("\nProvide --a <run_id> --b <run_id> to compare.")
            return 0

    result = compare_runs(args.a, args.b)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
