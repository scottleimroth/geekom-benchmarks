#!/usr/bin/env python3
"""Phase 6 standalone Windows metrics snapshot (RAM/CPU/GPU/NPU/temp/power).

Every metric carries a quality flag; unavailable metrics are null with a reason.
Nothing here fabricates numbers.

Usage:
  python scripts/collect_windows_metrics.py            # one full sample, pretty
  python scripts/collect_windows_metrics.py --light    # cheap psutil-only sample
  python scripts/collect_windows_metrics.py --json
"""
import _bootstrap  # noqa: F401
import argparse
import json

from geekom_benchmarks.metrics.windows import sample
from geekom_benchmarks.utils.io import local_stamp, paths, write_json_atomic


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--light", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--save", action="store_true", help="write to results/summary/metrics_<ts>.json")
    args = ap.parse_args()

    data = sample(full=not args.light)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(f"=== Windows metrics ({'light' if args.light else 'full'}) ===")
        for k, v in data.items():
            val = v.get("value")
            print(f"  {k:18} {str(val):>12} {v.get('unit',''):4}  [{v.get('quality')}]"
                  + (f"  ({v.get('reason')})" if v.get("reason") else ""))
    if args.save:
        out = paths()["summary"] / f"metrics_{local_stamp()}.json"
        write_json_atomic(out, {"timestamp": local_stamp(), "metrics": data})
        print(f"\nSaved: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
