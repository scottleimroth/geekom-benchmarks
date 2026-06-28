#!/usr/bin/env python3
"""Run/import canonical external suites into the umbrella schema.

This keeps external frameworks optional while still letting this repo ingest their
results as additional canonical categories:
  - llama.cpp llama-bench (import only)
  - lm-eval (run + import)
  - EvalScope (run + import)
  - MLPerf Client (import only)
  - OpenCompass / vLLM / BFCL / tau-bench / SWE-bench / RAGAS / DeepEval (import only)
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import _bootstrap  # noqa: F401

from geekom_benchmarks.adapters import evalscope_adapter, llama_bench_adapter, lm_eval_adapter, mlperf_client_importer
from geekom_benchmarks.config import DEFAULT_ENDPOINT, ModelSpec, select_models
from geekom_benchmarks.runners import ExternalImportRunner
from geekom_benchmarks.schemas.result import Category
from geekom_benchmarks.utils.io import local_stamp, sanitize, paths

SUPPORTED_SUITES = (
    "llama_bench",
    "lm_eval",
    "evalscope",
    "mlperf_client",
    "opencompass",
    "vllm",
    "bfcl",
    "tau_bench",
    "swe_bench",
    "ragas",
    "deepeval",
)

PLANNED_SUITES = {}

EXTERNAL_METRIC_HINTS = (
    "accuracy",
    "acc",
    "exact",
    "f1",
    "precision",
    "recall",
    "score",
    "pass",
    "success",
    "throughput",
    "tokens_per_second",
    "tokens_per_sec",
    "token/s",
    "tok/s",
    "tps",
    "request_per_sec",
    "requests_per_sec",
    "latency",
    "ttft",
    "tpot",
    "itl",
    "time_to_first_token",
    "p50",
    "p90",
    "p95",
    "p99",
    "bleu",
    "rouge",
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
    "tool_call",
    "function_call",
)

SUITE_ALIASES = {
    "all": "all",
    "llama.cpp": "llama_bench",
    "llama-cpp": "llama_bench",
    "llamacpp": "llama_bench",
    "llama_bench": "llama_bench",
    "llama-bench": "llama_bench",
    "lm-eval": "lm_eval",
    "lm_eval": "lm_eval",
    "lm-evaluation-harness": "lm_eval",
    "evalscope": "evalscope",
    "mlperf-client": "mlperf_client",
    "mlperf_client": "mlperf_client",
    "mlperfclient": "mlperf_client",
    "opencompass": "opencompass",
    "vllm": "vllm",
    "vllm-bench": "vllm",
    "bfcl": "bfcl",
    "tau-bench": "tau_bench",
    "tau_bench": "tau_bench",
    "ragas": "ragas",
    "deepeval": "deepeval",
    "deep_eval": "deepeval",
    "swe-bench": "swe_bench",
    "swe_bench": "swe_bench",
}

GENERIC_IMPORT_SUITES = {
    "opencompass": ("opencompass", Category.OPENCOMPASS, "opencompass_path"),
    "vllm": ("vllm", Category.VLLM, "vllm_path"),
    "bfcl": ("bfcl", Category.BFCL, "bfcl_path"),
    "tau_bench": ("tau-bench", Category.TAU_BENCH, "tau_bench_path"),
    "swe_bench": ("swe-bench", Category.SWE_BENCH, "swe_bench_path"),
    "ragas": ("ragas", Category.RAGAS, "ragas_path"),
    "deepeval": ("deepeval", Category.DEEP_EVAL, "deepeval_path"),
}

OPENCOMPASS_MODEL_ID_BY_ABBR = {
    "Gemma-4-E2B-it-GGUF": "Gemma-4-E2B-it-GGUF",
    "Qwen3-30B-A3B-GGUF": "Qwen3-30B-A3B-GGUF",
    "Qwen3-Coder-30B-A3B-Instruct-GGUF": "Qwen3-Coder-30B-A3B-Instruct-GGUF",
    "Nemotron-Cascade-2-30B-A3B-GGUF-Q4-K-M": "nvidia_Nemotron-Cascade-2-30B-A3B-GGUF-Q4_K_M",
    "Qwen3p6-35B-A3B-GGUF-UD-Q4-K-M": "Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M",
    "gpt-oss-20b-mxfp4-GGUF": "gpt-oss-20b-mxfp4-GGUF",
    "Qwen3-Coder-30B-A3B-Instruct-GGUF-Q4-K-M": "Qwen3-Coder-30B-A3B-Instruct-GGUF-Q4_K_M",
    "gemma-4-E4B-it-GGUF-UD-Q4-K-XL": "gemma-4-E4B-it-GGUF:UD-Q4_K_XL",
    "Qwen3-VL-8B-Instruct-GGUF": "Qwen3-VL-8B-Instruct-GGUF",
    "allenai-olmOCR-2-7B-1025-GGUF-Q4-K-M": "allenai_olmOCR-2-7B-1025-GGUF-Q4_K_M",
    "Qwen3p5-27B-GGUF-Q4-0": "Qwen3.5-27B-GGUF:Q4_0",
    "gemma-4-12b-it-GGUF-Q4-K-M": "gemma-4-12b-it-GGUF-Q4_K_M",
    "gemma-4-12b-it-text-Q4-K-M": "gemma-4-12b-it-text-Q4_K_M",
    "gemma-4-12b-it-vision-fixed-Q4-K-M": "gemma-4-12b-it-vision-fixed-Q4_K_M",
    "gemma-4-E4B-it-OBLITERATED-Q4-K-M": "gemma-4-E4B-it-OBLITERATED-Q4_K_M",
}


def _parse_csv(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _normalize_suite_name(value: str) -> str:
    key = value.strip().lower()
    key = key.replace(" ", "_")
    return SUITE_ALIASES.get(key, key.replace("-", "_"))


def _safe_float(value: Any) -> Optional[float]:
    try:
        if isinstance(value, bool):
            return None
        n = float(value)
        if n != n:
            return None
        return n
    except Exception:
        return None


def _looks_like_external_metric(metric: str) -> bool:
    lname = metric.lower()
    if any(skip in lname for skip in ("seed", "hash", "version", "index", "id_number")):
        return False
    return any(token in lname for token in EXTERNAL_METRIC_HINTS)


def _override_model_metadata(rows: List[Dict[str, Any]], model: Optional[ModelSpec]) -> List[Dict[str, Any]]:
    if not rows or not model:
        return rows
    for r in rows:
        rid = str(r.get("model_id", ""))
        # Prefer explicit IDs from catalog for consistency, but keep imported IDs when
        # parsing produced a different model name (some tools do this).
        if rid == model.id:
            r["model_display_name"] = model.display_name
        else:
            r.setdefault("model_display_name", model.display_name)
    return rows


def _emit_suite_rows(
    category: str,
    rows: List[Dict[str, Any]],
    *,
    run_id: str,
    endpoint: str,
    model: Optional[ModelSpec] = None,
    dry_run: bool = False,
) -> int:
    rows = _override_model_metadata(rows, model)
    if dry_run:
        print(f"  dry-run import: {len(rows)} row(s) for category={category}")
        return len(rows)

    runner = ExternalImportRunner(category=category, run_id=run_id, endpoint=endpoint)
    emitted = runner.emit_many(rows)
    if emitted:
        summary_model = model.id if model else (rows[0].get("model_id") if rows else "import")
        runner.write_run_summary({"model": summary_model, "n_emitted": len(emitted)})
        print(f"  imported: {len(emitted)} row(s) -> {runner.raw_path}")
        return len(emitted)
    print("  no rows to import")
    runner.write_run_summary({"model": model.id if model else "import", "n_emitted": 0})
    return 0


def _run_lm_eval(args, model: ModelSpec, run_id: str) -> int:
    out_dir = Path(args.output_root) / "lm_eval" / run_id / sanitize(model.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    import_path = Path(args.lm_eval_path) if args.lm_eval_path else out_dir

    if args.run_external:
        run_meta = lm_eval_adapter.run(
            model.id,
            args.lm_eval_tasks,
            endpoint=args.endpoint,
            chat=args.lm_eval_chat,
            num_concurrent=args.lm_eval_concurrency,
            output_path=str(out_dir),
            extra_args=args.lm_eval_extra_args,
            timeout=args.lm_eval_timeout,
        )
        if run_meta["returncode"] != 0:
            print(f"  lm-eval returned non-zero ({run_meta['returncode']}).")
            if args.strict:
                raise RuntimeError(f"lm-eval failed for {model.id}: {run_meta['stderr'][:2000]}")

    rows = lm_eval_adapter.import_results(
        str(import_path),
        model_id=model.id,
        model_display_name=model.display_name,
        tasks=args.lm_eval_tasks,
        metrics=args.lm_eval_metrics,
    )
    return _emit_suite_rows(Category.LM_EVAL, rows, run_id=run_id, endpoint=args.endpoint, model=model, dry_run=args.dry_run)


def _run_evalscope(args, model: ModelSpec, run_id: str) -> int:
    out_dir = Path(args.output_root) / "evalscope" / run_id / sanitize(model.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    import_path = Path(args.evalscope_path) if args.evalscope_path else out_dir
    dataset_args = args.evalscope_dataset_args
    if args.evalscope_dataset_args_file:
        dataset_args = Path(args.evalscope_dataset_args_file).read_text(encoding="utf-8")

    if args.run_external:
        run_meta = evalscope_adapter.run(
            model.id,
            args.evalscope_datasets,
            endpoint=args.endpoint,
            mode=args.evalscope_mode,
            concurrency=args.evalscope_concurrency,
            output_path=str(out_dir),
            dataset_hub=args.evalscope_dataset_hub or None,
            dataset_args=dataset_args or None,
            generation_config=args.evalscope_generation_config or None,
            no_timestamp=args.evalscope_no_timestamp,
            extra_args=args.evalscope_extra_args,
            timeout=args.evalscope_timeout,
        )
        (out_dir / "evalscope_command.json").write_text(
            json.dumps(run_meta["command"], indent=2),
            encoding="utf-8",
        )
        (out_dir / "evalscope_stdout.log").write_text(run_meta.get("stdout") or "", encoding="utf-8")
        (out_dir / "evalscope_stderr.log").write_text(run_meta.get("stderr") or "", encoding="utf-8")
        if run_meta["returncode"] != 0:
            print(f"  EvalScope returned non-zero ({run_meta['returncode']}).")
            if args.strict:
                raise RuntimeError(f"EvalScope failed for {model.id}: {run_meta['stderr'][:2000]}")
            return _emit_suite_rows(
                Category.EVALSCOPE,
                [
                    {
                        "model_id": model.id,
                        "model_display_name": model.display_name,
                        "benchmark_name": "evalscope:run",
                        "task_id": "run_failed",
                        "success": False,
                        "error_type": "other",
                        "error_message": (run_meta.get("stderr") or run_meta.get("stdout") or "")[:1000],
                        "notes": f"EvalScope exited with {run_meta['returncode']}",
                        "extra": {
                            "suite": "evalscope",
                            "command": run_meta["command"],
                            "output_path": str(out_dir).replace("\\", "/"),
                        },
                    }
                ],
                run_id=run_id,
                endpoint=args.endpoint,
                model=model,
                dry_run=args.dry_run,
            )

    rows = evalscope_adapter.import_results(
        str(import_path),
        model_id=model.id,
        model_display_name=model.display_name,
        datasets=args.evalscope_datasets,
    )
    return _emit_suite_rows(Category.EVALSCOPE, rows, run_id=run_id, endpoint=args.endpoint, model=model, dry_run=args.dry_run)


def _run_mlperf(args, run_id: str, model: Optional[ModelSpec]) -> int:
    rows = mlperf_client_importer.import_results(args.mlperf_path, model_id=args.mlperf_model)

    total = 0
    # MLPerf artifacts are often one file spanning all models. Group by model
    # if possible, then import per model to preserve per-model summary info.
    by_model: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_model.setdefault(str(row.get("model_id") or "unknown"), []).append(row)

    for model_id, model_rows in by_model.items():
        if model and args.mlperf_model and model_id != args.mlperf_model:
            continue
        temp = ModelSpec(id=model_id, display_name=model_id)
        if model:
            temp = model
        total += _emit_suite_rows(
            Category.MLPERF_CLIENT,
            model_rows,
            run_id=run_id,
            endpoint=args.endpoint,
            model=temp,
            dry_run=args.dry_run,
        )
    return total


def _run_llama_bench_import(args, run_id: str) -> int:
    rows = llama_bench_adapter.import_results(args.llama_bench_path)
    return _emit_suite_rows(
        Category.LLAMA_BENCH,
        rows,
        run_id=run_id,
        endpoint=args.endpoint,
        dry_run=args.dry_run,
    )


def _guess_model_from_container(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        for key in ("model_id", "model_name", "model", "name", "model_name_or_path"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in data.values():
            found = _guess_model_from_container(value)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _guess_model_from_container(value)
            if found:
                return found
    return None


def _flatten_numeric_metrics(
    data: Any,
    *,
    prefix: str = "",
    model_id: Optional[str] = None,
    seen: Optional[Set[int]] = None,
) -> List[Tuple[str, float, Optional[str]]]:
    seen = seen if seen is not None else set()
    out: List[Tuple[str, float, Optional[str]]] = []
    if isinstance(data, dict):
        local_model = _guess_model_from_container(data) or model_id
        if id(data) in seen:
            return out
        seen.add(id(data))
        for key, value in data.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_flatten_numeric_metrics(value, prefix=next_prefix, model_id=local_model, seen=seen))
    elif isinstance(data, list):
        if id(data) in seen:
            return out
        seen.add(id(data))
        for index, value in enumerate(data):
            next_prefix = f"{prefix}[{index}]"
            out.extend(_flatten_numeric_metrics(value, prefix=next_prefix, model_id=model_id, seen=seen))
    else:
        value = _safe_float(data)
        if value is None:
            return out
        if prefix:
            out.append((prefix, value, model_id))
    return out


def _iter_records_from_json_obj(
    payload: Any,
    *,
    source_path: str,
    model_filter: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path, value, inferred_model in _flatten_numeric_metrics(payload):
        metric = str(path).replace("..", ".").strip(".")
        if not metric or not _looks_like_external_metric(metric):
            continue
        payload_model = _guess_model_from_container(payload)
        mname = inferred_model or payload_model
        if not mname:
            mname = "unknown"
        if model_filter and (mname not in model_filter) and (payload_model and payload_model not in model_filter):
            continue

        lname = metric.lower()
        row: Dict[str, Any] = {
            "model_id": mname,
            "model_display_name": mname,
            "benchmark_name": metric if "." not in metric else metric.replace("[", ":").replace("]", ""),
            "task_id": metric,
            "success": True,
            "score": value,
            "notes": f"imported from {source_path}",
            "extra": {"suite": "external_generic", "metric": metric, "output_file": source_path},
            "raw_response_path": source_path,
        }
        if "time_to_first_token" in lname or "ttft" in lname:
            # Convert ms-like values to seconds.
            if value > 60:
                value = value / 1000.0
            row["first_token_latency_sec"] = value
        if any(k in lname for k in ("tok/s", "tokens_per_sec", "throughput", "tps")):
            row["output_tokens_per_sec"] = value
            row["tg_tokens_per_sec"] = value
        if "latency" in lname and "token" not in lname and "ttft" not in lname and "time_to_first_token" not in lname:
            row["elapsed_sec"] = value
        rows.append(row)
    return rows


def _read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        dialect = "excel-tab" if path.suffix.lower() == ".tsv" else "excel"
        reader = csv.DictReader(fh, dialect=dialect)
        for raw in reader:
            out.append({k.strip(): v for k, v in raw.items() if k is not None})
    return out


def _iter_records_from_csv(
    path: Path,
    *,
    model_filter: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    source = str(path).replace("\\", "/")
    for row in _read_csv_rows(path):
        model_id = str(
            row.get("model_id") or row.get("model") or row.get("model_name") or row.get("name") or "unknown"
        )
        if model_filter and model_id not in model_filter and row.get("model_display_name") not in model_filter:
            continue

        for key, value in row.items():
            value_f = _safe_float(value)
            if value_f is None:
                continue
            metric = str(key).strip()
            if not metric or not _looks_like_external_metric(metric):
                continue
            lname = metric.lower()
            task = metric
            row_obj: Dict[str, Any] = {
                "model_id": model_id,
                "model_display_name": str(row.get("model_display_name", model_id)),
                "benchmark_name": f"external_csv:{metric}",
                "task_id": f"{task}",
                "success": True,
                "score": value_f,
                "notes": f"imported from {source}",
                "extra": {"suite": "external_csv", "metric": metric, "output_file": source},
                "raw_response_path": source,
            }
            if "time_to_first_token" in lname or "ttft" in lname:
                if value_f > 60:
                    value_f = value_f / 1000.0
                row_obj["first_token_latency_sec"] = value_f
            if any(k in lname for k in ("tok/s", "tokens_per_sec", "throughput", "tps")):
                row_obj["output_tokens_per_sec"] = value_f
                row_obj["tg_tokens_per_sec"] = value_f
            if "latency" in lname and "token" not in lname and "ttft" not in lname and "time_to_first_token" not in lname:
                row_obj["elapsed_sec"] = value_f
            out.append(row_obj)
    return out


def _read_json_lines(path: Path) -> List[Any]:
    lines: List[Any] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for raw in fh:
            text = raw.strip()
            if not text:
                continue
            try:
                lines.append(json.loads(text))
            except Exception:
                pass
    return lines


def _run_import_only_suite(
    *,
    suite_name: str,
    source_path: str,
    run_id: str,
    endpoint: str,
    category: str,
    model_filter: Optional[Set[str]] = None,
    dry_run: bool = False,
) -> int:
    if not source_path:
        raise ValueError(f"--{suite_name}-path is required for suite='{suite_name}'")
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist for suite '{suite_name}': {source_path}")

    records: List[Dict[str, Any]] = []
    if source.is_file():
        candidates = [source]
    else:
        candidates = sorted(
            p for p in source.rglob("*")
            if p.suffix.lower() in {".json", ".jsonl", ".ndjson", ".csv", ".tsv"}
        )

    for p in candidates:
        suffix = p.suffix.lower()
        p_str = str(p).replace("\\", "/")
        if suffix in {".json", ".jsonl", ".ndjson"}:
            payloads: Iterable[Any]
            if suffix == ".json":
                try:
                    payloads = [json.loads(p.read_text(encoding="utf-8-sig"))] if p.exists() else []
                except Exception:
                    payloads = _read_json_lines(p)
            else:
                try:
                    payloads = _read_json_lines(p)
                except Exception:
                    payloads = []
            for payload in payloads:
                records.extend(_iter_records_from_json_obj(payload, source_path=p_str, model_filter=model_filter))
        elif suffix in {".csv", ".tsv"}:
            records.extend(_iter_records_from_csv(p, model_filter=model_filter))
        else:
            # Skip unknown extension files quietly.
            continue

    if not records:
        records = [
            {
                "model_id": "unknown",
                "model_display_name": "unknown",
                "benchmark_name": f"{category}:import",
                "task_id": "import",
                "success": False,
                "error_type": "other",
                "error_message": "No recognizable numeric metrics found",
                "notes": f"Checked {source}",
                "extra": {"suite": suite_name, "output_file": source_path},
                "raw_response_path": source_path,
            }
        ]
    else:
        for record in records:
            extra = record.get("extra")
            if not isinstance(extra, dict):
                extra = {}
                record["extra"] = extra
            extra["suite"] = suite_name
            if str(record.get("benchmark_name", "")).startswith("external_"):
                record["benchmark_name"] = f"{category}:{record.get('task_id', 'metric')}"

    return _emit_suite_rows(category, records, run_id=run_id, endpoint=endpoint, dry_run=dry_run)


def _run_opencompass_import(
    *,
    source_path: str,
    run_id: str,
    endpoint: str,
    dry_run: bool = False,
) -> int:
    """Import OpenCompass summary matrices without losing model names.

    OpenCompass writes summary CSV files shaped as:
    dataset,version,metric,mode,<model abbr 1>,<model abbr 2>,...
    The generic CSV importer treats columns as metrics, which loses the model
    identity. Import the matrix explicitly and fall back to the generic parser
    only when no OpenCompass summary file is found.
    """
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist for OpenCompass import: {source_path}")

    summary_files = [source] if source.is_file() and source.name.startswith("summary_") else []
    if source.is_dir():
        summary_files.extend(sorted(source.rglob("summary/summary_*.csv")))

    rows: List[Dict[str, Any]] = []
    reserved = {"dataset", "version", "metric", "mode"}
    for p in summary_files:
        p_str = str(p).replace("\\", "/")
        exp_root = p.parent.parent if p.parent.name == "summary" else p.parent
        for raw in _read_csv_rows(p):
            dataset = str(raw.get("dataset") or "opencompass")
            metric = str(raw.get("metric") or "score")
            version = str(raw.get("version") or "")
            mode = str(raw.get("mode") or "")
            for key, value in raw.items():
                if key in reserved:
                    continue
                score = _safe_float(value)
                model_id = OPENCOMPASS_MODEL_ID_BY_ABBR.get(key, key.removesuffix("-lemonade-smoke"))
                if score is None:
                    if not str(value).strip():
                        continue
                    infer_log = exp_root / "logs" / "infer" / key / f"{dataset}.out"
                    eval_log = exp_root / "logs" / "eval" / key / f"{dataset}.out"
                    failure_log = infer_log if infer_log.exists() else eval_log if eval_log.exists() else p
                    failure_text = ""
                    if failure_log.exists() and failure_log.is_file():
                        try:
                            failure_text = "\n".join(
                                line.strip()
                                for line in failure_log.read_text(encoding="utf-8", errors="replace").splitlines()
                                if "ERROR" in line or "model_load_error" in line or "failed" in line.lower()
                            )[-1200:]
                        except Exception:
                            failure_text = ""
                    rows.append({
                        "model_id": model_id,
                        "model_display_name": model_id,
                        "benchmark_name": f"opencompass:{dataset}:{metric}",
                        "task_id": dataset,
                        "success": False,
                        "score": None,
                        "error_type": "api_error",
                        "error_message": failure_text or f"OpenCompass did not produce a numeric {metric} value: {value}",
                        "notes": "OpenCompass failed-task import",
                        "extra": {
                            "suite": "opencompass",
                            "dataset": dataset,
                            "metric": metric,
                            "mode": mode,
                            "version": version,
                            "opencompass_model_abbr": key,
                            "opencompass_value": value,
                            "failure_log": str(failure_log).replace("\\", "/"),
                            "output_file": p_str,
                        },
                        "raw_response_path": str(failure_log).replace("\\", "/"),
                    })
                    continue
                rows.append({
                    "model_id": model_id,
                    "model_display_name": model_id,
                    "benchmark_name": f"opencompass:{dataset}:{metric}",
                    "task_id": dataset,
                    "success": True,
                    "score": score,
                    "notes": "OpenCompass summary import",
                    "extra": {
                        "suite": "opencompass",
                        "dataset": dataset,
                        "metric": metric,
                        "mode": mode,
                        "version": version,
                        "score_scale": "opencompass_percent",
                        "opencompass_model_abbr": key,
                        "output_file": p_str,
                    },
                    "raw_response_path": p_str,
                })

    if rows:
        return _emit_suite_rows(Category.OPENCOMPASS, rows, run_id=run_id, endpoint=endpoint, dry_run=dry_run)

    return _run_import_only_suite(
        suite_name="opencompass",
        source_path=source_path,
        run_id=run_id,
        endpoint=endpoint,
        category=Category.OPENCOMPASS,
        dry_run=dry_run,
    )


def _run_bfcl_import(
    *,
    source_path: str,
    run_id: str,
    endpoint: str,
    dry_run: bool = False,
) -> int:
    """Import EvalScope BFCL-v4 reports without generic JSON over-flattening.

    BFCL report JSON contains many function names inside sample metadata. The
    generic importer can mistake those for model ids, so BFCL gets an explicit
    parser that only reads report-level model, subset, aggregate, and perf rows.
    """
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist for BFCL import: {source_path}")
    report_files = [source] if source.is_file() else sorted(source.rglob("reports/*/bfcl_v4.json"))
    rows: List[Dict[str, Any]] = []

    for p in report_files:
        try:
            payload = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        model_id = str(payload.get("model_name") or "unknown")
        dataset = str(payload.get("dataset_name") or "bfcl_v4")
        p_str = str(p).replace("\\", "/")
        overall_score = _safe_float(payload.get("score"))
        if overall_score is not None:
            rows.append({
                "model_id": model_id,
                "model_display_name": model_id,
                "benchmark_name": "bfcl_v4:overall",
                "task_id": "overall",
                "success": True,
                "score": overall_score,
                "notes": "BFCL-v4 overall score",
                "extra": {"suite": "bfcl", "dataset": dataset, "metric": "overall", "output_file": p_str},
                "raw_response_path": p_str,
            })

        for metric in payload.get("metrics") or []:
            metric_name = str(metric.get("name") or "metric")
            for category in metric.get("categories") or []:
                for subset in category.get("subsets") or []:
                    subset_name = str(subset.get("name") or "subset")
                    score = _safe_float(subset.get("score"))
                    if score is None:
                        continue
                    rows.append({
                        "model_id": model_id,
                        "model_display_name": model_id,
                        "benchmark_name": f"bfcl_v4:{subset_name}:{metric_name}",
                        "task_id": subset_name,
                        "success": True,
                        "score": score,
                        "notes": f"BFCL-v4 {metric_name} for {subset_name}",
                        "extra": {
                            "suite": "bfcl",
                            "dataset": dataset,
                            "metric": metric_name,
                            "subset": subset_name,
                            "num": subset.get("num"),
                            "is_aggregate": bool(subset.get("is_aggregate")),
                            "output_file": p_str,
                        },
                        "raw_response_path": p_str,
                    })

        perf = ((payload.get("perf_metrics") or {}).get("summary") or {})
        throughput = perf.get("throughput") or {}
        usage = perf.get("usage") or {}
        for key, value in {
            "avg_output_tps": throughput.get("avg_output_tps"),
            "avg_req_ps": throughput.get("avg_req_ps"),
            "latency_mean": (perf.get("latency") or {}).get("mean"),
            "input_tokens_mean": (usage.get("input_tokens") or {}).get("mean"),
            "output_tokens_mean": (usage.get("output_tokens") or {}).get("mean"),
        }.items():
            score = _safe_float(value)
            if score is None:
                continue
            row: Dict[str, Any] = {
                "model_id": model_id,
                "model_display_name": model_id,
                "benchmark_name": f"bfcl_v4:perf:{key}",
                "task_id": f"perf:{key}",
                "success": True,
                "score": score,
                "notes": f"BFCL-v4 perf metric {key}",
                "extra": {"suite": "bfcl", "dataset": dataset, "metric": key, "output_file": p_str},
                "raw_response_path": p_str,
            }
            if key == "avg_output_tps":
                row["output_tokens_per_sec"] = score
                row["tg_tokens_per_sec"] = score
            if key == "latency_mean":
                row["elapsed_sec"] = score
            rows.append(row)

    if not rows:
        rows = [{
            "model_id": "unknown",
            "model_display_name": "unknown",
            "benchmark_name": "bfcl:import",
            "task_id": "import",
            "success": False,
            "error_type": "other",
            "error_message": "No BFCL report JSON found or parsed",
            "notes": f"Checked {source_path}",
            "extra": {"suite": "bfcl", "output_file": source_path},
            "raw_response_path": source_path,
        }]
    return _emit_suite_rows(Category.BFCL, rows, run_id=run_id, endpoint=endpoint, dry_run=dry_run)


def _run_tau_bench_import(
    *,
    source_path: str,
    run_id: str,
    endpoint: str,
    dry_run: bool = False,
) -> int:
    """Import tau-bench reports without flattening full conversation JSON."""
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist for tau-bench import: {source_path}")
    report_files = [source] if source.is_file() else sorted(source.rglob("reports/*/tau_bench.json"))
    rows: List[Dict[str, Any]] = []

    for p in report_files:
        try:
            payload = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        model_id = str(payload.get("model_name") or "unknown")
        dataset = str(payload.get("dataset_name") or "tau_bench")
        p_str = str(p).replace("\\", "/")
        overall_score = _safe_float(payload.get("score"))
        if overall_score is not None:
            rows.append({
                "model_id": model_id,
                "model_display_name": model_id,
                "benchmark_name": "tau_bench:overall",
                "task_id": "overall",
                "success": True,
                "score": overall_score,
                "notes": "tau-bench overall score",
                "extra": {
                    "suite": "tau_bench",
                    "dataset": dataset,
                    "metric": "overall",
                    "num": payload.get("num"),
                    "output_file": p_str,
                },
                "raw_response_path": p_str,
            })

        for metric in payload.get("metrics") or []:
            metric_name = str(metric.get("name") or "metric")
            metric_score = _safe_float(metric.get("score"))
            if metric_score is not None:
                rows.append({
                    "model_id": model_id,
                    "model_display_name": model_id,
                    "benchmark_name": f"tau_bench:{metric_name}",
                    "task_id": metric_name,
                    "success": True,
                    "score": metric_score,
                    "notes": f"tau-bench {metric_name}",
                    "extra": {
                        "suite": "tau_bench",
                        "dataset": dataset,
                        "metric": metric_name,
                        "num": metric.get("num"),
                        "output_file": p_str,
                    },
                    "raw_response_path": p_str,
                })
            for category in metric.get("categories") or []:
                category_name = category.get("name")
                if isinstance(category_name, list):
                    category_name = ",".join(str(v) for v in category_name)
                for subset in category.get("subsets") or []:
                    subset_name = str(subset.get("name") or "subset")
                    subset_score = _safe_float(subset.get("score"))
                    if subset_score is None:
                        continue
                    rows.append({
                        "model_id": model_id,
                        "model_display_name": model_id,
                        "benchmark_name": f"tau_bench:{subset_name}:{metric_name}",
                        "task_id": subset_name,
                        "success": True,
                        "score": subset_score,
                        "notes": f"tau-bench {metric_name} for {subset_name}",
                        "extra": {
                            "suite": "tau_bench",
                            "dataset": dataset,
                            "metric": metric_name,
                            "subset": subset_name,
                            "category": category_name,
                            "num": subset.get("num"),
                            "is_aggregate": bool(subset.get("is_aggregate")),
                            "output_file": p_str,
                        },
                        "raw_response_path": p_str,
                    })

        perf = ((payload.get("perf_metrics") or {}).get("summary") or {})
        throughput = perf.get("throughput") or {}
        usage = perf.get("usage") or {}
        for key, value in {
            "avg_output_tps": throughput.get("avg_output_tps"),
            "avg_req_ps": throughput.get("avg_req_ps"),
            "latency_mean": (perf.get("latency") or {}).get("mean"),
            "input_tokens_mean": (usage.get("input_tokens") or {}).get("mean"),
            "output_tokens_mean": (usage.get("output_tokens") or {}).get("mean"),
            "total_tokens_count": usage.get("total_tokens_count"),
        }.items():
            score = _safe_float(value)
            if score is None:
                continue
            row: Dict[str, Any] = {
                "model_id": model_id,
                "model_display_name": model_id,
                "benchmark_name": f"tau_bench:perf:{key}",
                "task_id": f"perf:{key}",
                "success": True,
                "score": score,
                "notes": f"tau-bench perf metric {key}",
                "extra": {
                    "suite": "tau_bench",
                    "dataset": dataset,
                    "metric": key,
                    "n_samples": perf.get("n_samples"),
                    "output_file": p_str,
                },
                "raw_response_path": p_str,
            }
            if key == "avg_output_tps":
                row["output_tokens_per_sec"] = score
                row["tg_tokens_per_sec"] = score
            if key == "latency_mean":
                row["elapsed_sec"] = score
            rows.append(row)

    if not rows:
        rows = [{
            "model_id": "unknown",
            "model_display_name": "unknown",
            "benchmark_name": "tau_bench:import",
            "task_id": "import",
            "success": False,
            "error_type": "other",
            "error_message": "No tau-bench report JSON found or parsed",
            "notes": f"Checked {source_path}",
            "extra": {"suite": "tau_bench", "output_file": source_path},
            "raw_response_path": source_path,
        }]
    return _emit_suite_rows(Category.TAU_BENCH, rows, run_id=run_id, endpoint=endpoint, dry_run=dry_run)


def _run_swe_bench_import(
    *,
    source_path: str,
    run_id: str,
    endpoint: str,
    dry_run: bool = False,
) -> int:
    """Import EvalScope/SWE-bench reports without flattening prompt payloads."""
    source = Path(source_path)
    if not source.exists():
        raise FileNotFoundError(f"Source path does not exist for SWE-bench import: {source_path}")
    report_files = [source] if source.is_file() else sorted(source.rglob("reports/*/swe_bench*.json"))
    rows: List[Dict[str, Any]] = []

    for p in report_files:
        try:
            payload = json.loads(p.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        model_id = str(payload.get("model_name") or "unknown")
        dataset = str(payload.get("dataset_name") or "swe_bench")
        p_str = str(p).replace("\\", "/")
        overall_score = _safe_float(payload.get("score"))
        if overall_score is not None:
            rows.append({
                "model_id": model_id,
                "model_display_name": model_id,
                "benchmark_name": f"{dataset}:overall",
                "task_id": "overall",
                "success": True,
                "score": overall_score,
                "notes": "SWE-bench aggregate score",
                "extra": {
                    "suite": "swe_bench",
                    "dataset": dataset,
                    "metric": "overall",
                    "num": payload.get("num"),
                    "output_file": p_str,
                },
                "raw_response_path": p_str,
            })

        for metric in payload.get("metrics") or []:
            metric_name = str(metric.get("name") or "metric")
            metric_score = _safe_float(metric.get("score"))
            if metric_score is not None:
                rows.append({
                    "model_id": model_id,
                    "model_display_name": model_id,
                    "benchmark_name": f"{dataset}:{metric_name}",
                    "task_id": metric_name,
                    "success": True,
                    "score": metric_score,
                    "notes": f"SWE-bench {metric_name}",
                    "extra": {
                        "suite": "swe_bench",
                        "dataset": dataset,
                        "metric": metric_name,
                        "num": metric.get("num"),
                        "output_file": p_str,
                    },
                    "raw_response_path": p_str,
                })
            for category in metric.get("categories") or []:
                category_name = category.get("name")
                if isinstance(category_name, list):
                    category_name = ",".join(str(v) for v in category_name)
                for subset in category.get("subsets") or []:
                    subset_name = str(subset.get("name") or "subset")
                    subset_score = _safe_float(subset.get("score"))
                    if subset_score is None:
                        continue
                    rows.append({
                        "model_id": model_id,
                        "model_display_name": model_id,
                        "benchmark_name": f"{dataset}:{subset_name}:{metric_name}",
                        "task_id": subset_name,
                        "success": True,
                        "score": subset_score,
                        "notes": f"SWE-bench {metric_name} for {subset_name}",
                        "extra": {
                            "suite": "swe_bench",
                            "dataset": dataset,
                            "metric": metric_name,
                            "subset": subset_name,
                            "category": category_name,
                            "num": subset.get("num"),
                            "is_aggregate": bool(subset.get("is_aggregate")),
                            "output_file": p_str,
                        },
                        "raw_response_path": p_str,
                    })

        perf = ((payload.get("perf_metrics") or {}).get("summary") or {})
        throughput = perf.get("throughput") or {}
        usage = perf.get("usage") or {}
        for key, value in {
            "avg_output_tps": throughput.get("avg_output_tps"),
            "avg_req_ps": throughput.get("avg_req_ps"),
            "latency_mean": (perf.get("latency") or {}).get("mean"),
            "input_tokens_mean": (usage.get("input_tokens") or {}).get("mean"),
            "output_tokens_mean": (usage.get("output_tokens") or {}).get("mean"),
            "total_tokens_count": usage.get("total_tokens_count"),
        }.items():
            score = _safe_float(value)
            if score is None:
                continue
            row: Dict[str, Any] = {
                "model_id": model_id,
                "model_display_name": model_id,
                "benchmark_name": f"{dataset}:perf:{key}",
                "task_id": f"perf:{key}",
                "success": True,
                "score": score,
                "notes": f"SWE-bench perf metric {key}",
                "extra": {
                    "suite": "swe_bench",
                    "dataset": dataset,
                    "metric": key,
                    "n_samples": perf.get("n_samples"),
                    "output_file": p_str,
                },
                "raw_response_path": p_str,
            }
            if key == "avg_output_tps":
                row["output_tokens_per_sec"] = score
                row["tg_tokens_per_sec"] = score
            if key == "latency_mean":
                row["elapsed_sec"] = score
            rows.append(row)

    review_files = [source] if source.is_file() else sorted(source.rglob("reviews/*/swe_bench*.jsonl"))
    for p in review_files:
        p_str = str(p).replace("\\", "/")
        for payload in _read_json_lines(p):
            if not isinstance(payload, dict):
                continue
            metadata = payload.get("metadata") or {}
            sample_metadata = payload.get("sample_metadata") or {}
            instance_id = str(sample_metadata.get("instance_id") or payload.get("sample_id") or "instance")
            model_id = p.parent.name or "unknown"
            response_model = None
            for message in reversed(payload.get("messages") or []):
                if isinstance(message, dict) and message.get("role") == "assistant" and message.get("model"):
                    response_model = str(message.get("model")).replace(".gguf", "")
                    break
            score_value = (((payload.get("sample_score") or {}).get("score") or {}).get("value") or {})
            acc = _safe_float(score_value.get("acc") if isinstance(score_value, dict) else None)
            error = ((metadata.get("report") or {}).get("error") if isinstance(metadata, dict) else None)
            rows.append({
                "model_id": model_id,
                "model_display_name": model_id,
                "benchmark_name": "swe_bench:instance",
                "task_id": instance_id,
                "success": bool(acc and acc > 0),
                "score": acc,
                "error_type": "test_failed" if error else None,
                "error_message": str(error)[:1000] if error else None,
                "notes": "SWE-bench instance review",
                "extra": {
                    "suite": "swe_bench",
                    "dataset": "swe_bench",
                    "repo": sample_metadata.get("repo"),
                    "base_commit": sample_metadata.get("base_commit"),
                    "response_model": response_model,
                    "output_file": p_str,
                },
                "raw_response_path": p_str,
            })

    if not rows:
        rows = [{
            "model_id": "unknown",
            "model_display_name": "unknown",
            "benchmark_name": "swe_bench:import",
            "task_id": "import",
            "success": False,
            "error_type": "other",
            "error_message": "No SWE-bench report/review JSON found or parsed",
            "notes": f"Checked {source_path}",
            "extra": {"suite": "swe_bench", "output_file": source_path},
            "raw_response_path": source_path,
        }]
    return _emit_suite_rows(Category.SWE_BENCH, rows, run_id=run_id, endpoint=endpoint, dry_run=dry_run)


def _unsupported_suite(name: str) -> None:
    raise NotImplementedError(
        f"Suite '{name}' is not yet wired for automated run. "
        f"Use --{name}-path to import exported results into category '{name}'."
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="all", help="comma list of catalog ids/display names")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument(
        "--suites",
        default="",
        help="comma list or 'all': llama_bench,lm_eval,evalscope,mlperf_client,opencompass,vllm,bfcl,tau_bench,swe_bench,ragas,deepeval",
    )
    ap.add_argument("--run-external", action="store_true", help="execute suite CLI when supported")
    ap.add_argument("--strict", action="store_true", help="raise on first non-zero run returncode")
    ap.add_argument("--dry-run", action="store_true", help="parse inputs and report row counts without writing result JSONL")
    ap.add_argument("--output-root", default=str(paths()["raw"] / "external"))
    ap.add_argument("--list-suites", action="store_true", help="list supported and planned external suites")

    # lm-eval
    ap.add_argument("--lm-eval-path", default="", help="existing lm-eval output file/folder to import")
    ap.add_argument(
        "--lm-eval-tasks",
        default=",".join(lm_eval_adapter.DEFAULT_TASKS),
        help="comma-separated lm-eval tasks",
    )
    ap.add_argument("--lm-eval-metrics", default="", help="comma-separated lm-eval metric names to keep")
    ap.add_argument("--lm-eval-chat", action="store_true", default=True, help="target chat-completions endpoint")
    ap.add_argument("--lm-eval-completions", action="store_true", help="target completions endpoint")
    ap.add_argument("--lm-eval-concurrency", type=int, default=1)
    ap.add_argument("--lm-eval-timeout", type=int, default=None)
    ap.add_argument(
        "--lm-eval-extra-arg",
        dest="lm_eval_extra_args",
        action="append",
        default=[],
        help="extra argument passed through to lm-eval; repeat for multiple args",
    )

    # EvalScope
    ap.add_argument("--evalscope-path", default="", help="existing EvalScope output file/folder to import")
    ap.add_argument("--evalscope-datasets", default="gsm8k,arc_easy")
    ap.add_argument("--evalscope-mode", default="accuracy", choices=["accuracy", "perf"])
    ap.add_argument("--evalscope-concurrency", type=int, default=1)
    ap.add_argument("--evalscope-timeout", type=int, default=None)
    ap.add_argument("--evalscope-dataset-hub", default="", help="EvalScope dataset hub override, e.g. huggingface")
    ap.add_argument("--evalscope-dataset-args", default="", help="EvalScope dataset-args JSON string")
    ap.add_argument("--evalscope-dataset-args-file", default="", help="Path to EvalScope dataset-args JSON")
    ap.add_argument("--evalscope-generation-config", default="", help="EvalScope generation-config string")
    ap.add_argument("--evalscope-no-timestamp", action="store_true", help="Pass --no-timestamp to EvalScope")
    ap.add_argument(
        "--evalscope-extra-arg",
        dest="evalscope_extra_args",
        action="append",
        default=[],
        help="extra argument passed through to EvalScope; repeat for multiple args",
    )

    # Import-only suite artifact paths.
    ap.add_argument("--llama-bench-path", default="", help="llama.cpp llama-bench output file or folder")
    ap.add_argument("--mlperf-path", default="", help="MLPerf JSON artifact path (file or folder)")
    ap.add_argument("--mlperf-model", default="", help="override model id when MLPerf parser is ambiguous")
    ap.add_argument("--opencompass-path", default="", help="OpenCompass output file or folder (JSON/JSONL/CSV)")
    ap.add_argument("--vllm-path", default="", help="vLLM benchmark output file or folder (JSON/JSONL/CSV)")
    ap.add_argument("--bfcl-path", default="", help="BFCL result/score export file or folder (JSON/JSONL/CSV)")
    ap.add_argument("--tau-bench-path", default="", help="tau-bench result export file or folder (JSON/JSONL/CSV)")
    ap.add_argument("--swe-bench-path", default="", help="SWE-bench result export file or folder (JSON/JSONL/CSV)")
    ap.add_argument("--ragas-path", default="", help="RAGAS output file or folder (JSON/JSONL/CSV)")
    ap.add_argument("--deepeval-path", default="", help="DeepEval output file or folder (JSON/JSONL/CSV)")

    args = ap.parse_args()

    if args.list_suites:
        print("Supported external suites:")
        for suite in SUPPORTED_SUITES:
            mode = "run+import" if suite in {"lm_eval", "evalscope"} else "import-only"
            print(f"  {suite:16} {mode}")
        print("Planned external suites:")
        for suite, reason in PLANNED_SUITES.items():
            print(f"  {suite:16} {reason}")
        return 0

    args.suites = [_normalize_suite_name(s) for s in args.suites.split(",") if s.strip()]
    if not args.suites:
        args.suites = ["lm_eval"]
    if "all" in args.suites:
        args.suites = list(SUPPORTED_SUITES)

    unsupported = [s for s in args.suites if s not in SUPPORTED_SUITES and s not in PLANNED_SUITES]
    if unsupported:
        print(f"Unsupported suite(s): {', '.join(unsupported)}")
        print("Run with --list-suites to see supported names.")
        return 1

    args.lm_eval_tasks = _parse_csv(args.lm_eval_tasks)
    if not args.lm_eval_tasks:
        args.lm_eval_tasks = list(lm_eval_adapter.DEFAULT_TASKS)
    args.lm_eval_metrics = _parse_csv(args.lm_eval_metrics) or None
    args.evalscope_datasets = _parse_csv(args.evalscope_datasets)
    if not args.evalscope_datasets:
        args.evalscope_datasets = ["gsm8k"]

    if args.lm_eval_completions:
        args.lm_eval_chat = False

    import_model_filter: Optional[Set[str]]
    if args.models == "all":
        import_model_filter = None
        models = select_models(args.models) if any(s in args.suites for s in ("lm_eval", "evalscope")) else []
    else:
        selected = select_models(args.models)
        import_model_filter = {m.id for m in selected} | {m.display_name for m in selected}
        if any(s in args.suites for s in ("lm_eval", "evalscope")):
            models = selected
            if not models:
                print(f"No enabled models matched '{args.models}'")
                return 1
        else:
            models = []
    if "lm_eval" in args.suites and not args.run_external and not args.lm_eval_path:
        print("--lm-eval-path is required for lm_eval imports unless --run-external is used")
        return 1
    if "evalscope" in args.suites and not args.run_external and not args.evalscope_path:
        print("--evalscope-path is required for evalscope imports unless --run-external is used")
        return 1
    if "mlperf_client" in args.suites and not args.mlperf_path:
        print("--mlperf-path is required for mlperf_client suite")
        return 1
    if "llama_bench" in args.suites and not args.llama_bench_path:
        print("--llama-bench-path is required for llama_bench suite")
        return 1
    for suite, (_label, _category, path_attr) in GENERIC_IMPORT_SUITES.items():
        if suite in args.suites and not getattr(args, path_attr):
            print(f"--{path_attr.replace('_', '-')} is required for {suite} suite")
            return 1

    print(f"run_external_benchmarks: suites={args.suites} endpoint={args.endpoint}")

    total_rows = 0
    for suite in args.suites:
        run_id = f"{sanitize(suite)}_{local_stamp()}"
        suite_id = f"{sanitize(suite)}_suite"
        print(f"== {suite} ==")
        if suite == "lm_eval":
            for model in models:
                print(f"\n# {model.display_name} ({model.id})")
                total_rows += _run_lm_eval(args, model, run_id or suite_id)
        elif suite == "evalscope":
            for model in models:
                print(f"\n# {model.display_name} ({model.id})")
                total_rows += _run_evalscope(args, model, run_id or suite_id)
        elif suite == "mlperf_client":
            total_rows += _run_mlperf(args, run_id or suite_id, None)
        elif suite == "llama_bench":
            total_rows += _run_llama_bench_import(args, run_id or suite_id)
        elif suite in GENERIC_IMPORT_SUITES:
            suite_label, category, path_attr = GENERIC_IMPORT_SUITES[suite]
            if args.run_external:
                _unsupported_suite(suite_label)
            if suite == "bfcl":
                total_rows += _run_bfcl_import(
                    source_path=getattr(args, path_attr),
                    run_id=run_id or suite_id,
                    endpoint=args.endpoint,
                    dry_run=args.dry_run,
                )
            elif suite == "tau_bench":
                total_rows += _run_tau_bench_import(
                    source_path=getattr(args, path_attr),
                    run_id=run_id or suite_id,
                    endpoint=args.endpoint,
                    dry_run=args.dry_run,
                )
            elif suite == "swe_bench":
                total_rows += _run_swe_bench_import(
                    source_path=getattr(args, path_attr),
                    run_id=run_id or suite_id,
                    endpoint=args.endpoint,
                    dry_run=args.dry_run,
                )
            elif suite == "opencompass":
                total_rows += _run_opencompass_import(
                    source_path=getattr(args, path_attr),
                    run_id=run_id or suite_id,
                    endpoint=args.endpoint,
                    dry_run=args.dry_run,
                )
            else:
                total_rows += _run_import_only_suite(
                    suite_name=suite,
                    source_path=getattr(args, path_attr),
                    run_id=run_id or suite_id,
                    endpoint=args.endpoint,
                    category=category,
                    model_filter=import_model_filter,
                    dry_run=args.dry_run,
                )
        elif suite in PLANNED_SUITES:
            print(f"  planned, not run: {PLANNED_SUITES[suite]}")
        else:
            _unsupported_suite(suite)

    print(f"Total imported rows: {total_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
