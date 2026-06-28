"""EvalScope adapter.

EvalScope (ModelScope) can target OpenAI-compatible endpoints and supports both
accuracy suites and a concurrency-focused `perf` mode. This adapter offers a
best-effort command + parser so benchmark results can be imported into the
umbrella schema without adding a hard dependency.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def build_command(
    model_id: str,
    datasets: List[str],
    *,
    endpoint: str = "http://127.0.0.1:13305/api/v1",
    api_key: str = "lemonade",
    mode: str = "accuracy",
    concurrency: int = 1,
    output_path: str = "results/raw/evalscope/",
    dataset_hub: Optional[str] = None,
    dataset_args: Optional[str] = None,
    generation_config: Optional[str] = None,
    no_timestamp: bool = False,
    extra_args: Optional[List[str]] = None,
) -> List[str]:
    """Build an EvalScope CLI argv for Lemonade."""
    evalscope_exe = shutil.which("evalscope")
    if not evalscope_exe:
        candidate = Path(sys.executable).with_name("evalscope.exe")
        evalscope_exe = str(candidate) if candidate.exists() else "evalscope"
    cmd = [
        evalscope_exe,
        "eval",
        "--model",
        model_id,
        "--api-url",
        endpoint.rstrip("/"),
        "--api-key",
        api_key,
        "--eval-type",
        "openai_api",
        "--datasets",
        *datasets,
        "--work-dir",
        output_path,
    ]
    if dataset_hub:
        cmd.extend(["--dataset-hub", dataset_hub])
    if dataset_args:
        cmd.extend(["--dataset-args", dataset_args])
    if generation_config:
        cmd.extend(["--generation-config", generation_config])
    if no_timestamp:
        cmd.append("--no-timestamp")
    if mode == "perf":
        cmd.extend(["--collect-perf", "--eval-batch-size", str(concurrency)])
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def build_config(
    model_id: str,
    datasets: List[str],
    *,
    endpoint: str = "http://127.0.0.1:13305/api/v1",
    api_key: str = "lemonade",
) -> Dict[str, Any]:
    """Return an EvalScope-style config dict (not executed)."""
    return {
        "model": model_id,
        "api_url": endpoint,
        "api_key": api_key,
        "eval_type": "openai_api",
        "datasets": list(datasets),
    }


def run(
    model_id: str,
    datasets: List[str],
    *,
    endpoint: str = "http://127.0.0.1:13305/api/v1",
    api_key: str = "lemonade",
    mode: str = "accuracy",
    concurrency: int = 1,
    output_path: str = "results/raw/evalscope/",
    dataset_hub: Optional[str] = None,
    dataset_args: Optional[str] = None,
    generation_config: Optional[str] = None,
    no_timestamp: bool = False,
    extra_args: Optional[List[str]] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute EvalScope if installed and return command metadata."""
    cmd = build_command(
        model_id,
        datasets,
        endpoint=endpoint,
        api_key=api_key,
        mode=mode,
        concurrency=concurrency,
        output_path=output_path,
        dataset_hub=dataset_hub,
        dataset_args=dataset_args,
        generation_config=generation_config,
        no_timestamp=no_timestamp,
        extra_args=extra_args,
    )
    try:
        cp = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "EvalScope CLI not found. Install with `pip install evalscope` (user opt-in)."
        ) from exc
    return {
        "returncode": cp.returncode,
        "command": cmd,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
        "output_path": output_path,
    }


def _load_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _discover_result_files(path: str) -> List[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.exists():
        return []

    candidates = [
        p / "result.json",
        p / "results.json",
        p / "summary.json",
    ]
    candidates.extend(sorted(p.rglob("reviews/**/*.jsonl")))
    candidates.extend(sorted(p.rglob("*.json")))
    out: List[Path] = []
    for c in candidates:
        if c.exists() and c not in out:
            out.append(c)
    return out


def _read_jsonl(p: Path) -> Iterable[Dict[str, Any]]:
    with p.open("r", encoding="utf-8-sig") as fh:
        for raw in fh:
            text = raw.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except Exception:
                continue
            if isinstance(payload, dict):
                yield payload


def _infer_dataset_from_review_path(p: Path) -> str:
    return p.stem


def _find_perf_metrics(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        perf = payload.get("perf_metrics")
        if isinstance(perf, dict):
            return perf
        for value in payload.values():
            found = _find_perf_metrics(value)
            if found:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _find_perf_metrics(value)
            if found:
                return found
    return {}


def _score_values_from_review(payload: Dict[str, Any]) -> Dict[str, float]:
    score = payload.get("sample_score") or {}
    if isinstance(score, dict):
        score = score.get("score") or score
    if isinstance(score, dict):
        score = score.get("value") or score
    out: Dict[str, float] = {}
    if isinstance(score, dict):
        for key, value in score.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[str(key)] = float(value)
    elif isinstance(score, (int, float)) and not isinstance(score, bool):
        out["score"] = float(score)
    return out


def _review_rows(
    p: Path,
    *,
    model_id: Optional[str],
    model_display_name: Optional[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    dataset = _infer_dataset_from_review_path(p)
    p_str = str(p).replace("\\", "/")
    for payload in _read_jsonl(p):
        scores = _score_values_from_review(payload)
        if not scores:
            continue
        sample_id = payload.get("sample_id", payload.get("index", "unknown"))
        messages = payload.get("messages") or []
        detected_model = model_id or payload.get("model") or "unknown"
        if not model_id and isinstance(messages, list):
            for msg in reversed(messages):
                if isinstance(msg, dict) and msg.get("model"):
                    detected_model = msg.get("model")
                    break
        perf = _find_perf_metrics(payload)
        for metric_name, value in scores.items():
            row: Dict[str, Any] = {
                "model_id": detected_model,
                "model_display_name": model_display_name or str(detected_model),
                "benchmark_name": f"evalscope:{dataset}:{metric_name}",
                "task_id": f"{dataset}:{sample_id}:{metric_name}",
                "success": bool(value),
                "score": value,
                "notes": f"EvalScope review metric '{metric_name}'",
                "extra": {
                    "suite": "evalscope",
                    "metric": metric_name,
                    "dataset": dataset,
                    "sample_id": sample_id,
                    "output_file": p_str,
                },
                "raw_response_path": p_str,
            }
            if isinstance(perf, dict):
                if isinstance(perf.get("latency"), (int, float)):
                    row["elapsed_sec"] = float(perf["latency"])
                if isinstance(perf.get("ttft"), (int, float)):
                    row["first_token_latency_sec"] = float(perf["ttft"])
                if isinstance(perf.get("input_tokens"), int):
                    row["prompt_tokens"] = perf["input_tokens"]
                if isinstance(perf.get("output_tokens"), int):
                    row["completion_tokens"] = perf["output_tokens"]
            rows.append(row)
    return rows


def _flatten_numeric_metrics(
    obj: Any,
    *,
    prefix: str = "",
) -> List[tuple[str, float]]:
    out: List[tuple[str, float]] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            np = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append((np, float(value)))
            else:
                out.extend(_flatten_numeric_metrics(value, prefix=np))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            out.extend(_flatten_numeric_metrics(item, prefix=f"{prefix}[{idx}]"))
    return out


def _pick_metric_rows(payload: Dict[str, Any]) -> List[tuple[str, float]]:
    roots = []
    for key in ("results", "summary", "metrics"):
        block = payload.get(key)
        if isinstance(block, dict):
            roots.append(block)
    if not roots:
        roots = [payload]

    rows: List[tuple[str, float]] = []
    for root in roots:
        for name, value in _flatten_numeric_metrics(root):
            lname = name.lower()
            if any(skip in lname for skip in ("id", "hash", "seed", "version", "num_")):
                continue
            rows.append((name, value))
    return rows


def import_results(
    path: str,
    *,
    model_id: Optional[str] = None,
    model_display_name: Optional[str] = None,
    datasets: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Map EvalScope JSON into canonical row dicts."""
    payloads = _discover_result_files(path)
    if not payloads:
        raise FileNotFoundError(f"No EvalScope result JSON found at: {path}")

    rows: List[Dict[str, Any]] = []
    for p in payloads:
        if p.suffix.lower() == ".jsonl":
            rows.extend(_review_rows(p, model_id=model_id, model_display_name=model_display_name))
            continue
        payload = _load_json(p)
        if not payload:
            continue
        if not isinstance(payload, dict):
            continue

        mid = model_id or payload.get("model_name") or payload.get("model") or "unknown"
        mdn = model_display_name or str(mid)
        ds = str(payload.get("dataset", ""))

        metrics = _pick_metric_rows(payload)
        if not metrics:
            continue

        for metric_name, value in metrics:
            if datasets and ds and ds not in datasets:
                continue

            record_name = f"{metric_name}"
            benchmark_name = f"evalscope:{record_name}"
            if ds:
                benchmark_name = f"evalscope:{ds}:{record_name}"

            row: Dict[str, Any] = {
                "model_id": mid,
                "model_display_name": mdn,
                "benchmark_name": benchmark_name,
                "task_id": f"{record_name}",
                "success": True,
                "score": value,
                "notes": f"EvalScope metric '{metric_name}'",
                "extra": {
                    "suite": "evalscope",
                    "metric": metric_name,
                    "dataset": ds or payload.get("dataset_name"),
                    "output_file": str(p).replace("\\", "/"),
                },
                "raw_response_path": str(p).replace("\\", "/"),
            }

            lname = metric_name.lower()
            if "ttft" in lname or "first_token" in lname:
                row["first_token_latency_sec"] = float(value)
            if any(k in lname for k in ("tok/s", "tokens_per_sec", "throughput", "tps")):
                row["output_tokens_per_sec"] = float(value)
            rows.append(row)

    if not rows:
        return [
            {
                "model_id": model_id or "unknown",
                "model_display_name": model_display_name or (model_id or "unknown"),
                "benchmark_name": "evalscope:import",
                "task_id": "import",
                "success": False,
                "error_type": "other",
                "error_message": "Could not parse recognizable EvalScope metrics",
                "notes": f"Checked {len(payloads)} json file(s) under {path}",
                "extra": {
                    "suite": "evalscope",
                    "warning": "no recognizable metrics found",
                },
            }
        ]

    return rows
