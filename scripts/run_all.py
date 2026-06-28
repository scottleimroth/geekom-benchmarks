#!/usr/bin/env python3
"""Phase 14 orchestrator: run every benchmark category, then generate the report.

Overnight-safe: each stage is isolated; a stage failure is logged and the run
continues to the next independent stage.

Usage:
  python scripts/run_all.py --models all
  python scripts/run_all.py --models all --trials 20
  python scripts/run_all.py --skip vision,long_context
"""
import _bootstrap  # noqa: F401
import argparse
import traceback

from geekom_benchmarks.config import DEFAULT_ENDPOINT, select_models
from geekom_benchmarks.clients import LemonadeClient
from geekom_benchmarks.runners.speed import SpeedRunner
from geekom_benchmarks.runners.tool_reliability import ToolReliabilityRunner
from geekom_benchmarks.runners.structured import StructuredRunner
from geekom_benchmarks.runners.coding import CodingRunner
from geekom_benchmarks.runners.vision import VisionRunner
from geekom_benchmarks.runners.longcontext import LongContextRunner
from geekom_benchmarks.runners.agent import AgentWorkflowRunner
from geekom_benchmarks.reporting.report import generate


def _stage(name, fn, skip):
    if name in skip:
        print(f"\n### SKIP {name}")
        return
    print(f"\n### STAGE {name}")
    try:
        fn()
    except Exception as e:
        print(f"!!! stage {name} failed: {type(e).__name__}: {e}")
        print(traceback.format_exc()[-800:])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all")
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--skip", default="", help="comma list of stages to skip")
    args = ap.parse_args()

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    client = LemonadeClient(args.endpoint)
    models = select_models(args.models)
    vmodels = select_models(args.models, uses="vision")
    # For a full-suite run, coding is part of the all-enabled-model comparison.
    # The standalone coding CLI still supports narrower smoke runs.
    cmodels = models
    print(f"run_all: {len(models)} models, trials={args.trials}, endpoint={args.endpoint}")

    def speed():
        r = SpeedRunner(client)
        for m in models:
            r.run_model(m)
        r.write_run_summary()

    def tool():
        r = ToolReliabilityRunner(client)
        for m in models:
            for mode in ("parallel", "nopar", "strict"):
                r.run_model_mode(m, mode, trials=args.trials)
        r.write_run_summary()

    def structured():
        r = StructuredRunner(client)
        for m in models:
            r.run_model(m)
        r.write_run_summary()

    def coding():
        r = CodingRunner(client)
        for m in cmodels:
            r.run_model(m)
        r.write_run_summary()

    def vision():
        r = VisionRunner(client)
        for m in (vmodels or []):
            r.run_model(m)
        r.write_run_summary()

    def longctx():
        r = LongContextRunner(client)
        for m in models:
            r.run_model(m)
        r.write_run_summary()

    def agent():
        r = AgentWorkflowRunner(client)
        for m in models:
            r.run_model(m)
        r.write_run_summary()

    _stage("speed", speed, skip)
    _stage("tool_reliability", tool, skip)
    _stage("structured_output", structured, skip)
    _stage("coding", coding, skip)
    _stage("vision", vision, skip)
    _stage("long_context", longctx, skip)
    _stage("agent_workflow", agent, skip)

    print("\n### STAGE report")
    out = generate()
    print(f"Report: {out['html_latest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
