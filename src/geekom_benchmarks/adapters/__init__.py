"""Adapters that align this umbrella harness with canonical benchmark styles.

This package is the seam between geekom-benchmarks' own runners and the wider
ecosystem (llama-bench, lm-evaluation-harness, EvalScope, MLPerf Client, BFCL,
tau-bench). Most modules here are deliberate, practical wrappers with honest
limitations, not fake implementations.

Currently functional:
  - llama_bench_adapter      : derives llama-bench-compatible fields from a ChatResult
  - bfcl_lite                : BFCL-style exposure modes + outcome taxonomy
  - tau_lite                 : tau-bench-style repeated-trial / pass@k / policy helpers
  - lm_eval_adapter          : command builder + parser/import for lm-eval output
  - evalscope_adapter        : command builder + parser/import for EvalScope output
  - mlperf_client_importer   : parser/import for MLPerf Client output artifacts

Backlog:
  - opencompass, vLLM scripts, RAGAS, DeepEval import helpers
"""

from . import bfcl_lite, evalscope_adapter, llama_bench_adapter, lm_eval_adapter, mlperf_client_importer, tau_lite

__all__ = [
    "llama_bench_adapter",
    "bfcl_lite",
    "tau_lite",
    "lm_eval_adapter",
    "evalscope_adapter",
    "mlperf_client_importer",
]
