#!/usr/bin/env python3
"""Phase 11 long-context (needle retrieval) benchmark.

Usage:  python scripts/run_longcontext.py --models Nemotron-Cascade-2-30B-A3B
"""
import _bootstrap  # noqa: F401
import argparse

from geekom_benchmarks.config import DEFAULT_ENDPOINT, select_models
from geekom_benchmarks.clients import LemonadeClient
from geekom_benchmarks.runners.longcontext import LongContextRunner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--no-metrics", action="store_true")
    args = ap.parse_args()

    models = select_models(args.models)
    if not models:
        print(f"No enabled models matched '{args.models}'")
        return 1
    client = LemonadeClient(args.endpoint)
    runner = LongContextRunner(client, sample_metrics=not args.no_metrics)
    print(f"== long context: {len(models)} model(s), run_id={runner.run_id} ==")
    for m in models:
        print(f"\n# {m.display_name} (ctx_window={m.context_window})")
        try:
            runner.run_model(m)
        except Exception as e:
            print(f"  ERROR on {m.display_name}: {type(e).__name__}: {e}")
    runner.write_run_summary()
    print(f"\nRaw: {runner.raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
