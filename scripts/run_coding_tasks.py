#!/usr/bin/env python3
"""Phase 9 coding benchmark (deterministic local tasks; temp workspace only).

Usage:
  python scripts/run_coding_tasks.py --models Qwen3-Coder-30B-A3B
  python scripts/run_coding_tasks.py --models all --tasks refactor_dedupe
  python scripts/run_coding_tasks.py --list
"""
import _bootstrap  # noqa: F401
import argparse

from geekom_benchmarks.config import DEFAULT_ENDPOINT, select_models
from geekom_benchmarks.clients import LemonadeClient
from geekom_benchmarks.runners.coding import CodingRunner, TASKS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all")
    ap.add_argument("--tasks", default=None, help="comma-separated task ids (default: all)")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-metrics", action="store_true")
    args = ap.parse_args()

    if args.list:
        for t in TASKS:
            print(f"  {t.id:24} {t.kind}")
        return 0

    models = select_models(args.models, uses="coding") if args.models == "all" else select_models(args.models)
    if not models:
        print(f"No enabled models matched '{args.models}'")
        return 1
    task_ids = [t.strip() for t in args.tasks.split(",")] if args.tasks else None

    client = LemonadeClient(args.endpoint)
    runner = CodingRunner(client, sample_metrics=not args.no_metrics)
    print(f"== coding: {len(models)} model(s), run_id={runner.run_id} ==")
    print(f"   temp workspace: {runner.workspace}")
    for m in models:
        print(f"\n# {m.display_name}")
        try:
            runner.run_model(m, task_ids=task_ids)
        except Exception as e:
            print(f"  ERROR on {m.display_name}: {type(e).__name__}: {e}")
    runner.write_run_summary()
    print(f"\nRaw: {runner.raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
