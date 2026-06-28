#!/usr/bin/env python3
"""Phase 5 speed benchmark.

Usage:
  python scripts/run_benchmarks.py --models all
  python scripts/run_benchmarks.py --models Qwen3-30B-A3B,gemma-4-E2B-it
  python scripts/run_benchmarks.py --models gemma-4-E2B-it --smoke   # 1 short prompt
"""
import _bootstrap  # noqa: F401
import argparse

from geekom_benchmarks.config import DEFAULT_ENDPOINT, select_models
from geekom_benchmarks.clients import LemonadeClient
from geekom_benchmarks.runners.speed import SpeedRunner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all")
    ap.add_argument("--category", default="speed", choices=["speed"])
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--smoke", action="store_true", help="single short prompt only (fast)")
    ap.add_argument("--no-metrics", action="store_true")
    args = ap.parse_args()

    models = select_models(args.models)
    if not models:
        print(f"No enabled models matched '{args.models}'")
        return 1

    client = LemonadeClient(args.endpoint)
    runner = SpeedRunner(client, sample_metrics=not args.no_metrics)
    if args.smoke:
        # trim to a single short prompt for a fast pipeline smoke test
        runner.cfg = dict(runner.cfg)
        runner.cfg["prompts"] = [p for p in runner.cfg.get("prompts", []) if p["id"] == "short_fact"][:1]
        runner.cfg["max_tokens"] = args.max_tokens or 128

    print(f"== speed: {len(models)} model(s), run_id={runner.run_id} ==")
    for m in models:
        print(f"\n# {m.display_name} ({m.id})")
        try:
            runner.run_model(m, max_tokens=args.max_tokens)
        except Exception as e:  # overnight-safe: keep going
            print(f"  ERROR on {m.display_name}: {type(e).__name__}: {e}")

    summ = runner.write_run_summary()
    print(f"\nRaw:     {runner.raw_path}")
    print(f"Summary: {summ}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
