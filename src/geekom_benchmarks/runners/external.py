"""Shared helpers for importing external benchmark outputs into canonical JSONL rows."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..schemas.result import BenchmarkResult, RunContext
from ..utils.io import append_jsonl, local_stamp, new_run_id, paths, sanitize, write_json_atomic


@dataclass
class _StaticClient:
    endpoint: str


class ExternalImportRunner:
    """Emit imported external suite rows through the same canonical schema.

    This runner is intentionally lightweight: it doesn't call any chat endpoint;
    it only standardizes external artifacts into local run context.
    """

    def __init__(
        self,
        category: str,
        *,
        run_id: Optional[str] = None,
        endpoint: str = "http://127.0.0.1:13305/api/v1",
        sample_metrics: bool = False,
        runtime: str = "import-only",
    ) -> None:
        self.category = category
        self.run_id = run_id or f"{sanitize(category)}_{local_stamp()}"
        self.ctx = RunContext(
            run_id=self.run_id,
            endpoint=endpoint,
            runtime=runtime,
        )
        self.raw_path = paths()["raw"] / sanitize(self.category) / f"{self.run_id}.jsonl"
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)
        self._results: list[BenchmarkResult] = []

    # -- result helpers -----------------------------------------------------
    def emit_record(self, record: Dict[str, Any]) -> BenchmarkResult:
        """Emit one canonical result row from an already-parsed import record."""
        benchmark_name = record.get("benchmark_name") or record.get("task_id") or "imported"
        task_id = record.get("task_id") or benchmark_name
        model_id = str(record.get("model_id", "unknown"))
        model_display_name = str(
            record.get("model_display_name", model_id)
        )

        result = BenchmarkResult.start(
            self.ctx,
            model_id=model_id,
            model_display_name=model_display_name,
            category=self.category,
            benchmark_name=str(benchmark_name),
            task_id=str(task_id),
            prompt_id=record.get("prompt_id"),
        )

        # Core outcome metrics.
        result.success = bool(record.get("success", False))
        result.score = record.get("score")
        result.error_type = record.get("error_type")
        result.error_message = record.get("error_message")
        result.notes = record.get("notes")
        result.extra = record.get("extra", {}) or {}

        # Timing / throughput.
        result.elapsed_sec = record.get("elapsed_sec")
        result.first_token_latency_sec = record.get("first_token_latency_sec")
        result.output_tokens_per_sec = record.get("output_tokens_per_sec")
        result.total_tokens_per_sec = record.get("total_tokens_per_sec")
        result.prompt_tokens = record.get("prompt_tokens")
        result.completion_tokens = record.get("completion_tokens")
        result.total_tokens = record.get("total_tokens")
        result.tokens_estimated = bool(record.get("tokens_estimated", False))

        # Llama-bench-style alignment fields if available.
        result.pp_tokens = record.get("pp_tokens")
        result.tg_tokens = record.get("tg_tokens")
        result.pp_tokens_per_sec = record.get("pp_tokens_per_sec")
        result.tg_tokens_per_sec = record.get("tg_tokens_per_sec")
        result.backend = record.get("backend")
        result.gpu_layers = record.get("gpu_layers")
        result.batch_size = record.get("batch_size")
        result.ubatch_size = record.get("ubatch_size")
        result.flash_attention = record.get("flash_attention")
        result.quant = record.get("quant")
        result.model_file = record.get("model_file")
        result.model_hash = record.get("model_hash")

        result.raw_response_path = record.get("raw_response_path")
        result.retry_count = int(record.get("retry_count") or 0)

        # Snapshot any optional adapter-specific provenance.
        self._push(result)
        return result

    def emit_many(self, rows: list[Dict[str, Any]]) -> list[BenchmarkResult]:
        return [self.emit_record(row) for row in rows]

    def _push(self, result: BenchmarkResult) -> None:
        result.finish()
        self._results.append(result)
        append_jsonl(self.raw_path, result.to_dict())

    def write_run_summary(self, extra: Optional[Dict[str, Any]] = None) -> None:
        passed = sum(1 for r in self._results if r.success)
        summary = {
            "run_id": self.run_id,
            "category": self.category,
            "endpoint": self.ctx.endpoint,
            "machine_hostname": self.ctx.machine_hostname,
            "raw_path": str(self.raw_path).replace("\\", "/"),
            "n_results": len(self._results),
            "n_passed": passed,
            "models": sorted({r.model_display_name for r in self._results}),
            "extra": extra or {},
        }
        out = paths()["summary"] / f"{self.run_id}.json"
        write_json_atomic(out, summary)
        return out
