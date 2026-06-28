#!/usr/bin/env python3
"""Phase 7 tool-calling reliability (BFCL-lite exposure modes).

Modes (internal name -> BFCL-lite exposure label):
  nopar    -> serial     (tools available, one call/turn)
  parallel -> parallel   (parallel_tool_calls=True)
  strict   -> staged     (tools revealed one phase at a time)
BFCL-lite aliases are accepted: --modes serial,parallel,staged (or multistep).
The task is a multi_step_dependent case (metadata -> note carrying the year).

Usage:
  python scripts/run_tool_reliability.py --models all --trials 20
  python scripts/run_tool_reliability.py --models Qwen3-30B-A3B --modes staged --trials 20
"""
import _bootstrap  # noqa: F401
import argparse

from geekom_benchmarks.config import DEFAULT_ENDPOINT, select_models
from geekom_benchmarks.clients import LemonadeClient
from geekom_benchmarks.runners.tool_reliability import ToolReliabilityRunner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all")
    ap.add_argument("--modes", default="parallel,nopar,strict")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--no-metrics", action="store_true")
    args = ap.parse_args()

    models = select_models(args.models)
    if not models:
        print(f"No enabled models matched '{args.models}'")
        return 1
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    client = LemonadeClient(args.endpoint)
    runner = ToolReliabilityRunner(client, sample_metrics=not args.no_metrics)
    print(f"== tool reliability: {len(models)} model(s) x {modes}, {args.trials} trials, run_id={runner.run_id} ==")

    summaries = []
    for m in models:
        print(f"\n# {m.display_name}")
        for mode in modes:
            try:
                s = runner.run_model_mode(m, mode, trials=args.trials)
                summaries.append(s)
                print(f"  {mode:8} -> {s['score_str']}  fails={s['failure_categories']}")
            except Exception as e:
                print(f"  {mode:8} ERROR: {type(e).__name__}: {e}")

    runner.write_run_summary({"results": summaries})
    print(f"\nRaw:     {runner.raw_path}")
    print("\n--- Tool reliability summary ---")
    for s in summaries:
        print(f"  {s['model_display_name']:30} {s['mode']:8} {s['score_str']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
