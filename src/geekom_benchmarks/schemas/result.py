"""THE canonical benchmark result schema.

Every benchmark category in this repo emits records of exactly this shape, one
JSON object per task/trial, written as JSONL. Summaries and reports are derived
from these records — no runner is allowed to invent its own output format.

If you need category-specific data, put it under `extra` (a free-form dict).
Never add a top-level field in one runner that the others don't share.
"""
from __future__ import annotations

import dataclasses
import os
import platform
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from ..utils.io import utc_now_iso

RESULT_SCHEMA_VERSION = "1.0.0"


class Category:
    """Canonical benchmark category names."""

    SPEED = "speed"
    TOOL = "tool_reliability"
    STRUCTURED = "structured_output"
    CODING = "coding"
    VISION = "vision"
    LONG_CONTEXT = "long_context"
    AGENT = "agent_workflow"
    ENVIRONMENT = "environment"
    LLAMA_BENCH = "llama_bench"
    LM_EVAL = "lm_eval"
    EVALSCOPE = "evalscope"
    MLPERF_CLIENT = "mlperf_client"
    OPENCOMPASS = "opencompass"
    VLLM = "vllm"
    BFCL = "bfcl"
    TAU_BENCH = "tau_bench"
    SWE_BENCH = "swe_bench"
    RAGAS = "ragas"
    DEEP_EVAL = "deepeval"


class ErrorType:
    """Canonical error_type values shared across runners (None == success)."""

    NONE = None
    API_ERROR = "api_error"
    TIMEOUT = "timeout"
    REFUSAL = "refusal"
    INVALID_JSON = "invalid_json"
    INVALID_TOOL_ARGS = "invalid_tool_args"
    WRONG_YEAR = "wrong_year"
    WRONG_TOOL_ORDER = "wrong_tool_order"
    MISSING_TOOL = "missing_tool"
    EXTRA_TOOL = "extra_tool"
    FAILED_TO_USE_METADATA = "failed_to_use_metadata"
    SCHEMA_INVALID = "schema_invalid"
    WRONG_CONTENT = "wrong_content"
    TEST_FAILED = "test_failed"
    UNSAFE_OPERATION = "unsafe_operation"
    SKIPPED = "skipped"
    OTHER = "other"


@dataclass
class RunContext:
    """Per-invocation context shared by every result in a run.

    Created once at the top of a runner and stamped into each BenchmarkResult so
    a single JSONL row is fully self-describing (machine, endpoint, runtime...).
    """

    run_id: str
    endpoint: str
    runtime: str = "lemonade/llamacpp-vulkan"
    machine_hostname: str = field(default_factory=lambda: os.environ.get("GEEKOM_BENCH_PUBLIC_HOST_LABEL", "local-geekom"))
    os: str = field(default_factory=lambda: f"{platform.system()} {platform.release()}")
    repo_path: str = "repo-local"
    schema_version: str = RESULT_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class BenchmarkResult:
    """One task/trial outcome. Serialized as a single JSONL line."""

    # --- identity / context (filled from RunContext) ---
    run_id: str
    machine_hostname: str
    os: str
    repo_path: str
    endpoint: str
    runtime: str
    schema_version: str

    # --- what was run ---
    model_id: str
    model_display_name: str
    benchmark_category: str
    benchmark_name: str
    task_id: str
    timestamp_start: str
    timestamp_end: str

    prompt_id: Optional[str] = None

    # --- outcome ---
    success: bool = False
    score: Optional[float] = None  # 0..1 where applicable
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    # --- token accounting ---
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    tokens_estimated: bool = False  # True if counts are heuristic, not API-reported

    # --- timing ---
    elapsed_sec: Optional[float] = None
    first_token_latency_sec: Optional[float] = None
    output_tokens_per_sec: Optional[float] = None
    total_tokens_per_sec: Optional[float] = None
    retry_count: int = 0

    # --- llama-bench-compatible fields -------------------------------------
    # Populated where the runtime actually exposes them. Anything Lemonade does
    # NOT expose is left null and the reason is recorded in extra["llama_bench"].
    # These are NEVER fabricated. pp = prompt-processing (prefill); tg = token
    # generation (decode). See adapters/llama_bench_adapter.py for derivation.
    pp_tokens: Optional[int] = None
    tg_tokens: Optional[int] = None
    pp_tokens_per_sec: Optional[float] = None
    tg_tokens_per_sec: Optional[float] = None
    backend: Optional[str] = None
    gpu_layers: Optional[int] = None
    batch_size: Optional[int] = None
    ubatch_size: Optional[int] = None
    flash_attention: Optional[bool] = None
    quant: Optional[str] = None
    model_file: Optional[str] = None
    model_hash: Optional[str] = None

    # --- system metrics snapshots (each: metric -> {value, unit, quality}) ---
    metrics_before: Optional[Dict[str, Any]] = None
    metrics_during: Optional[Dict[str, Any]] = None
    metrics_after: Optional[Dict[str, Any]] = None

    # --- provenance / extensibility ---
    raw_response_path: Optional[str] = None
    notes: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def start(
        cls,
        ctx: RunContext,
        *,
        model_id: str,
        model_display_name: str,
        category: str,
        benchmark_name: str,
        task_id: str,
        prompt_id: Optional[str] = None,
    ) -> "BenchmarkResult":
        """Create a result pre-stamped with context and a start timestamp.

        The runner mutates fields as it goes, then calls `.finish()`.
        """
        now = utc_now_iso()
        return cls(
            run_id=ctx.run_id,
            machine_hostname=ctx.machine_hostname,
            os=ctx.os,
            repo_path=ctx.repo_path,
            endpoint=ctx.endpoint,
            runtime=ctx.runtime,
            schema_version=ctx.schema_version,
            model_id=model_id,
            model_display_name=model_display_name,
            benchmark_category=category,
            benchmark_name=benchmark_name,
            task_id=task_id,
            prompt_id=prompt_id,
            timestamp_start=now,
            timestamp_end=now,
        )

    def finish(self) -> "BenchmarkResult":
        """Stamp the end timestamp and derive tok/s if not already set."""
        self.timestamp_end = utc_now_iso()
        if self.total_tokens is None and (
            self.prompt_tokens is not None or self.completion_tokens is not None
        ):
            self.total_tokens = (self.prompt_tokens or 0) + (self.completion_tokens or 0)
        if self.elapsed_sec and self.elapsed_sec > 0:
            if self.output_tokens_per_sec is None and self.completion_tokens:
                self.output_tokens_per_sec = round(self.completion_tokens / self.elapsed_sec, 2)
            if self.total_tokens_per_sec is None and self.total_tokens:
                self.total_tokens_per_sec = round(self.total_tokens / self.elapsed_sec, 2)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
