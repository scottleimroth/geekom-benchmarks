#!/usr/bin/env python3
"""Phase 12 agent-readiness workflow benchmark (tau-bench-inspired).

Composite workflow: plan -> tool -> file edit -> test -> verify, with domain
policy/rule compliance and a final-state check. With --trials > 1 it reports
reliability-over-retries and pass^k.

Usage:
  python scripts/run_agent_workflow.py --models Nemotron-Cascade-2-30B-A3B
  python scripts/run_agent_workflow.py --models Qwen3-30B-A3B --trials 5
"""
import _bootstrap  # noqa: F401
import argparse
import json

from geekom_benchmarks.config import DEFAULT_ENDPOINT, select_models
from geekom_benchmarks.clients import LemonadeClient
from geekom_benchmarks.runners.agent import AgentWorkflowRunner


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all")
    ap.add_argument("--trials", type=int, default=1, help="repeated trials per model (pass^k)")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--no-metrics", action="store_true")
    args = ap.parse_args()

    models = select_models(args.models)
    if not models:
        print(f"No enabled models matched '{args.models}'")
        return 1
    client = LemonadeClient(args.endpoint)
    runner = AgentWorkflowRunner(client, sample_metrics=not args.no_metrics)
    print(f"== agent workflow: {len(models)} model(s) x {args.trials} trial(s), run_id={runner.run_id} ==")
    summaries = []
    for m in models:
        print(f"\n# {m.display_name}")
        try:
            agg = runner.run_model(m, trials=args.trials)
            summaries.append(agg)
            print(f"  reliability={agg['reliability']} pass^k={agg['pass_hat_k']} "
                  f"policies={agg['policy_compliance']}")
        except Exception as e:
            print(f"  ERROR on {m.display_name}: {type(e).__name__}: {e}")
    runner.write_run_summary({"results": summaries})
    print(f"\nRaw: {runner.raw_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
