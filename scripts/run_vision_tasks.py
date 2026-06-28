#!/usr/bin/env python3
"""Phase 10 vision benchmark (vision-capable models only; SKIPPED otherwise).

Usage:
  python scripts/run_vision_tasks.py --models vision    # all vision-capable models
  python scripts/run_vision_tasks.py --models Qwen3-VL-8B
"""
import _bootstrap  # noqa: F401
import argparse

from geekom_benchmarks.config import DEFAULT_ENDPOINT, select_models
from geekom_benchmarks.clients import LemonadeClient
from geekom_benchmarks.runners.vision import VisionRunner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="vision",
                    help="'vision' = all vision-capable; or all / comma list")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--no-metrics", action="store_true")
    args = ap.parse_args()

    if args.models == "vision":
        models = select_models("all", uses="vision")
    else:
        models = select_models(args.models)
    if not models:
        print("No vision-capable models matched.")
        return 1
    client = LemonadeClient(args.endpoint)
    runner = VisionRunner(client, sample_metrics=not args.no_metrics)
    print(f"== vision: {len(models)} model(s), run_id={runner.run_id} ==")
    for m in models:
        print(f"\n# {m.display_name}")
        try:
            runner.run_model(m)
        except Exception as e:
            print(f"  ERROR on {m.display_name}: {type(e).__name__}: {e}")
    runner.write_run_summary()
    print(f"\nRaw: {runner.raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
