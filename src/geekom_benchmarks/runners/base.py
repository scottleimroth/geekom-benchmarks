"""BaseRunner: the shared spine every benchmark category uses.

Responsibilities:
  - own the RunContext + run_id
  - own the single raw JSONL output file for the run
  - sample system metrics before/during/after work (via MetricsScope)
  - emit canonical BenchmarkResult records
  - never raise out of a single task: a crash in one task is captured as a
    failed result so an overnight sweep keeps going.

Category-specific logic lives in subclasses; they call `self.emit(result)` with
fully-populated canonical results. They MUST NOT invent their own file format.
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..clients.base import ChatClient
from ..config import ModelSpec
from ..metrics.windows import MetricSampler
from ..schemas.result import BenchmarkResult, RunContext
from ..utils.io import append_jsonl, new_run_id, paths, sanitize, write_json_atomic


def _log(msg: str) -> None:
    print(msg, flush=True)


class MetricsScope:
    """Context manager that captures before/after metrics and one 'during' sample.

    The 'during' sample is taken by a daemon thread after `during_delay` seconds,
    so longer generations get a genuine mid-run reading; short calls simply won't
    have one (recorded as None) rather than a fabricated value.
    """

    def __init__(self, sampler: MetricSampler, during_delay: float = 1.5, full: bool = True):
        self._sampler = sampler
        self._during_delay = during_delay
        self._full = full
        self.before: Optional[Dict[str, Any]] = None
        self.during: Optional[Dict[str, Any]] = None
        self.after: Optional[Dict[str, Any]] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def _during_worker(self) -> None:
        if self._stop.wait(self._during_delay):
            return  # scope ended before the delay elapsed -> no during sample
        try:
            self.during = self._sampler.light()
        except Exception:
            self.during = None

    def __enter__(self) -> "MetricsScope":
        try:
            self.before = self._sampler.full() if self._full else self._sampler.light()
        except Exception:
            self.before = None
        self._thread = threading.Thread(target=self._during_worker, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        try:
            self.after = self._sampler.full() if self._full else self._sampler.light()
        except Exception:
            self.after = None


class BaseRunner:
    category = "base"

    def __init__(
        self,
        client: ChatClient,
        *,
        run_id: Optional[str] = None,
        log: Callable[[str], None] = _log,
        sample_metrics: bool = True,
    ):
        self.client = client
        self.run_id = run_id or new_run_id(self.category)
        self.ctx = RunContext(
            run_id=self.run_id,
            endpoint=client.endpoint,
            runtime=getattr(client, "runtime", "unknown"),
        )
        self.log = log
        self.sample_metrics = sample_metrics
        self.sampler = MetricSampler()
        self._results: List[BenchmarkResult] = []
        self.raw_path: Path = paths()["raw"] / sanitize(self.category) / f"{self.run_id}.jsonl"
        self.raw_path.parent.mkdir(parents=True, exist_ok=True)

    # -- result helpers -----------------------------------------------------
    def new_result(self, model: ModelSpec, **kw) -> BenchmarkResult:
        return BenchmarkResult.start(
            self.ctx,
            model_id=model.id,
            model_display_name=model.display_name,
            category=self.category,
            **kw,
        )

    def emit(self, result: BenchmarkResult) -> None:
        result.finish()
        self._results.append(result)
        append_jsonl(self.raw_path, result.to_dict())

    def metrics_scope(self, full: bool = True) -> MetricsScope:
        if not self.sample_metrics:
            # a no-op scope that records nothing
            return _NullScope()  # type: ignore[return-value]
        return MetricsScope(self.sampler, full=full)

    # -- summary ------------------------------------------------------------
    def write_run_summary(self, extra: Optional[Dict[str, Any]] = None) -> Path:
        """Write a small per-run summary next to the raw file and in summary/."""
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

    def safe_task(self, fn: Callable[[], BenchmarkResult], *, fallback: BenchmarkResult) -> BenchmarkResult:
        """Run one task fn; if it raises, record a captured failure instead."""
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            fallback.success = False
            fallback.error_type = "other"
            fallback.error_message = f"runner_exception: {type(exc).__name__}: {exc}"
            fallback.notes = traceback.format_exc()[-1500:]
            return fallback


class _NullScope:
    before = during = after = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None
