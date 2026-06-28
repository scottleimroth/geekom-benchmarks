#!/usr/bin/env python3
"""DEPRECATED shim -> the unified speed runner.

The original standalone speed benchmark now lives in the framework as
`geekom_benchmarks.runners.speed.SpeedRunner`, driven by `run_benchmarks.py`.
The original source is preserved at
  results/archive/pre-framework-2026-06-25/benchmark.py.bak-20260626d

This shim keeps old muscle memory working: it forwards to run_benchmarks.py.
Old flags `--model X` / `--json` are translated; prompt/gen-len flags are ignored
(the new runner uses config/tasks.yaml prompt set + warm-up exclusion).
"""
import _bootstrap  # noqa: F401
import runpy
import sys

print("[deprecated] scripts/benchmark.py -> use scripts/run_benchmarks.py "
      "(see config/tasks.yaml). Forwarding...\n", file=sys.stderr)

# translate legacy args
new_argv = ["run_benchmarks.py"]
argv = sys.argv[1:]
i = 0
while i < len(argv):
    a = argv[i]
    if a == "--model" and i + 1 < len(argv):
        new_argv += ["--models", argv[i + 1]]
        i += 2
    elif a in ("--prompt-len", "--gen-len") and i + 1 < len(argv):
        if a == "--gen-len":
            new_argv += ["--max-tokens", argv[i + 1]]
        i += 2  # prompt-len ignored
    elif a == "--json":
        i += 1  # new runner always writes structured JSONL
    else:
        new_argv.append(a)
        i += 1

sys.argv = new_argv
import os
runpy.run_path(os.path.join(os.path.dirname(__file__), "run_benchmarks.py"), run_name="__main__")
