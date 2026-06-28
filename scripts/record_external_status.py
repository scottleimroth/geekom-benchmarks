#!/usr/bin/env python3
"""Record canonical external-suite status rows.

Use this for benchmark families that are deliberately blocked or not applicable
after a real feasibility check. It keeps those decisions visible in the same
raw JSONL/report flow as completed external imports.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import _bootstrap  # noqa: F401

from geekom_benchmarks.runners import ExternalImportRunner
from geekom_benchmarks.schemas.result import Category, ErrorType
from geekom_benchmarks.utils.io import local_stamp, sanitize


CATEGORY_BY_SUITE = {
    "mlperf_client": Category.MLPERF_CLIENT,
    "opencompass": Category.OPENCOMPASS,
    "vllm": Category.VLLM,
    "ragas": Category.RAGAS,
    "deepeval": Category.DEEP_EVAL,
    "swe_bench": Category.SWE_BENCH,
    "bfcl": Category.BFCL,
    "tau_bench": Category.TAU_BENCH,
    "evalscope": Category.EVALSCOPE,
}


def _row_from_status(record: Dict[str, Any], source: Path) -> Dict[str, Any]:
    suite = str(record["suite"])
    status = str(record.get("status") or "blocked-with-evidence")
    success = status == "completed"
    error_type = None
    if not success:
        error_type = ErrorType.SKIPPED if status == "not-applicable-by-definition" else ErrorType.OTHER
    extra = dict(record.get("extra") or {})
    extra.update(
        {
            "suite": suite,
            "status": status,
            "evidence": record.get("evidence"),
            "source_file": str(source).replace("\\", "/"),
        }
    )
    return {
        "model_id": str(record.get("model_id") or "external_suite"),
        "model_display_name": str(record.get("model_display_name") or record.get("model_id") or "External suite"),
        "benchmark_name": str(record.get("benchmark_name") or f"{suite}:status"),
        "task_id": str(record.get("task_id") or status),
        "success": success,
        "score": record.get("score"),
        "error_type": error_type,
        "error_message": record.get("reason") if not success else None,
        "notes": record.get("notes") or record.get("reason"),
        "extra": extra,
        "raw_response_path": str(source).replace("\\", "/"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("status_json", help="JSON file containing a list of status records")
    ap.add_argument("--endpoint", default="http://127.0.0.1:13305/api/v1")
    ap.add_argument("--run-id-suffix", default=local_stamp())
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    source = Path(args.status_json)
    records = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(records, list):
        raise TypeError("status_json must contain a list")

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for record in records:
        suite = str(record["suite"])
        if suite not in CATEGORY_BY_SUITE:
            raise ValueError(f"Unsupported status suite: {suite}")
        grouped.setdefault(suite, []).append(_row_from_status(record, source))

    total = 0
    for suite, rows in sorted(grouped.items()):
        run_id = f"{sanitize(suite)}_status_{args.run_id_suffix}"
        if args.dry_run:
            print(f"{suite}: {len(rows)} row(s)")
            total += len(rows)
            continue
        runner = ExternalImportRunner(
            category=CATEGORY_BY_SUITE[suite],
            run_id=run_id,
            endpoint=args.endpoint,
            runtime="status-import",
        )
        runner.emit_many(rows)
        runner.write_run_summary({"source": str(source).replace("\\", "/"), "n_emitted": len(rows)})
        print(f"{suite}: wrote {len(rows)} row(s) -> {runner.raw_path}")
        total += len(rows)
    print(f"Total status rows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
