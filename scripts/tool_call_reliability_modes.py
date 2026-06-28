#!/usr/bin/env python3
"""DEPRECATED shim -> the unified tool-reliability runner.

The original multi-mode harness (which wrote to a hard-coded WSL path) now lives
in the framework as `geekom_benchmarks.runners.tool_reliability.ToolReliabilityRunner`,
driven by `run_tool_reliability.py`, with repo-relative output and the unified
result schema. The original source is preserved at
  results/archive/pre-framework-2026-06-25/tool_call_reliability_modes.py.orig

This shim translates the old `--model X --mode Y` flags and forwards.
"""
import _bootstrap  # noqa: F401
import os
import runpy
import sys

print("[deprecated] scripts/tool_call_reliability_modes.py -> use "
      "scripts/run_tool_reliability.py. Forwarding...\n", file=sys.stderr)

new_argv = ["run_tool_reliability.py"]
argv = sys.argv[1:]
i = 0
while i < len(argv):
    a = argv[i]
    if a == "--model" and i + 1 < len(argv):
        new_argv += ["--models", argv[i + 1]]
        i += 2
    elif a == "--mode" and i + 1 < len(argv):
        new_argv += ["--modes", argv[i + 1]]
        i += 2
    elif a == "--out":
        i += 2  # output path is managed by the framework now
    else:
        new_argv.append(a)
        i += 1

sys.argv = new_argv
runpy.run_path(os.path.join(os.path.dirname(__file__), "run_tool_reliability.py"), run_name="__main__")
