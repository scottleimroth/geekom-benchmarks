"""EleutherAI lm-evaluation-harness adapter.

lm-eval is the de-facto standard for academic LLM task accuracy (MMLU, GSM8K,
HellaSwag, ARC, ...). It can target OpenAI-compatible endpoints via
`local-completions` and `local-chat-completions`, which is exactly what Lemonade
serves. This adapter provides a best-effort run + importer path while keeping the
repo's local dependency surface unchanged (lm-eval remains opt-in).
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..utils.io import sanitize

MODEL_TYPE_CHAT = "local-chat-completions"
MODEL_TYPE_COMPLETIONS = "local-completions"
DEFAULT_TASKS = ["arc_easy", "gsm8k"]


def build_command(
    model_id: str,
    tasks: List[str],
    *,
    endpoint: str = "http://127.0.0.1:13305/api/v1",
    chat: bool = True,
    num_concurrent: int = 1,
    max_retries: int = 2,
    tokenized_requests: bool = False,
    output_path: str = "results/raw/lm_eval/",
    extra_args: Optional[List[str]] = None,
) -> List[str]:
    """Build the lm-eval CLI argv for evaluating Lemonade.

    Returns only an argv list so callers can log exactly what will run.
    """
    path = "chat/completions" if chat else "completions"
    model_type = MODEL_TYPE_CHAT if chat else MODEL_TYPE_COMPLETIONS
    model_args = (
        f"model={model_id},base_url={endpoint.rstrip('/')}/{path},"
        f"num_concurrent={num_concurrent},max_retries={max_retries},"
        f"tokenized_requests={str(bool(tokenized_requests)).lower()}"
    )
    cmd = [
        "lm_eval",
        "--model",
        model_type,
        "--model_args",
        model_args,
        "--tasks",
        ",".join(tasks),
        "--output_path",
        output_path,
    ]
    if extra_args:
        cmd.extend(extra_args)
    return cmd


def run(
    model_id: str,
    tasks: List[str],
    *,
    endpoint: str = "http://127.0.0.1:13305/api/v1",
    chat: bool = True,
    num_concurrent: int = 1,
    max_retries: int = 2,
    tokenized_requests: bool = False,
    output_path: str = "results/raw/lm_eval/",
    extra_args: Optional[List[str]] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute lm-eval if installed and return subprocess completion metadata.

    lm-eval can be slow or fail for unsupported tasks; callers should inspect
    `returncode` before attempting import.
    """
    cmd = build_command(
        model_id,
        tasks,
        endpoint=endpoint,
        chat=chat,
        num_concurrent=num_concurrent,
        max_retries=max_retries,
        tokenized_requests=tokenized_requests,
        output_path=output_path,
        extra_args=extra_args,
    )
    try:
        cp = subprocess.run(cmd, check=False, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "lm-eval CLI not found. Install with `pip install lm-eval` (user opt-in)."
        ) from exc
    return {
        "returncode": cp.returncode,
        "command": cmd,
        "stdout": cp.stdout,
        "stderr": cp.stderr,
        "output_path": output_path,
    }


def _is_numeric(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and not math.isnan(float(v))


def _load_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _metric_value_preference(key: str, value: float) -> bool:
    if not _is_numeric(value):
        return False
    k = key.lower()
    if k.endswith("_stderr") or k in {"sample_len", "alias"}:
        return False
    if "acc" in k or "exact" in k or "f1" in k or "rouge" in k or "bleu" in k or "ppl" in k:
        return True
    # Generic performance/likelihood outputs included when nothing better exists.
    return isinstance(value, (int, float))


def _extract_task_scores(payload: Dict[str, Any]) -> Iterable[tuple[str, str, float, Dict[str, Any]]]:
    """Yield ``(task_id, metric_name, score, meta)`` from one lm-eval JSON payload."""
    results = payload.get("results")
    if not isinstance(results, dict):
        return

    for task, metrics in results.items():
        if not isinstance(metrics, dict):
            continue
        for metric, value in metrics.items():
            if _metric_value_preference(str(metric), value):
                yield task, str(metric), float(value), payload


def _discover_result_files(path: str) -> List[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.exists():
        return []

    files = [p / "results.json"]
    files.extend(sorted(p.rglob("*.json")))
    out: List[Path] = []
    for f in files:
        if f.exists() and f not in out:
            out.append(f)
    return out


def _normalize_records(
    payloads: List[Path],
    model_id: Optional[str],
    model_display_name: Optional[str],
    task_filter: Optional[List[str]],
    metric_filter: Optional[List[str]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    task_filter_set = {t.lower() for t in (task_filter or []) if t}
    metric_filter_set = {m.lower() for m in (metric_filter or []) if m}

    for p in payloads:
        payload = _load_json(p)
        if not payload:
            continue

        detected_model = str(
            payload.get("model_name")
            or payload.get("model")
            or payload.get("model_name_or_path")
            or model_id
            or "unknown"
        )
        detected_display = model_display_name or detected_model
        for task, metric, score, _meta in _extract_task_scores(payload):
            if task_filter_set and task.lower() not in task_filter_set:
                continue
            if metric_filter_set and metric.lower() not in metric_filter_set:
                continue

            rows.append(
                {
                    "model_id": detected_model,
                    "model_display_name": detected_display,
                    "benchmark_name": f"lm_eval:{task}:{metric}",
                    "task_id": f"{task}:{metric}",
                    "success": True,
                    "score": score,
                    "notes": f"lm-eval task='{task}' metric='{metric}'",
                    "extra": {
                        "suite": "lm_eval",
                        "metric": metric,
                        "task": task,
                        "output_file": str(p).replace("\\", "/"),
                    },
                    "raw_response_path": str(p).replace("\\", "/"),
                }
            )

        if not rows:
            # Some lm-eval versions may place scores in an alternate shape.
            alt = payload.get("results")
            if isinstance(alt, dict):
                for task in alt:
                    if not isinstance(alt[task], (int, float)):
                        continue
                    t = str(task)
                    if task_filter_set and t.lower() not in task_filter_set:
                        continue
                    rows.append(
                        {
                            "model_id": detected_model,
                            "model_display_name": detected_display,
                            "benchmark_name": f"lm_eval:{t}",
                            "task_id": t,
                            "success": True,
                            "score": float(alt[task]),
                            "notes": f"lm-eval task='{t}'",
                            "extra": {
                                "suite": "lm_eval",
                                "metric": "score",
                                "task": t,
                                "output_file": str(p).replace("\\", "/"),
                            },
                            "raw_response_path": str(p).replace("\\", "/"),
                        }
                    )

    return rows


def import_results(
    lm_eval_json_path: str,
    *,
    model_id: Optional[str] = None,
    model_display_name: Optional[str] = None,
    tasks: Optional[List[str]] = None,
    metrics: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Map lm-eval result JSON files/folders into canonical row dicts.

    Returns rows in canonical adapter format (without run context).
    """
    payloads = _discover_result_files(lm_eval_json_path)
    if not payloads:
        raise FileNotFoundError(f"No lm-eval result JSON found at: {lm_eval_json_path}")

    rows = _normalize_records(payloads, model_id, model_display_name, tasks, metrics)
    if not rows:
        # Keep failure transparent: return a model-anchored failed row for visibility.
        mid = model_id or (payloads[0].name if payloads else "unknown")
        mname = model_display_name or mid
        return [
            {
                "model_id": mid,
                "model_display_name": mname,
                "benchmark_name": "lm_eval:import",
                "task_id": "import",
                "success": False,
                "error_type": "other",
                "error_message": "Could not parse recognizable lm-eval metrics",
                "notes": f"Checked {len(payloads)} json file(s) under {lm_eval_json_path}",
                "extra": {
                    "suite": "lm_eval",
                    "warning": "no recognizable task scores found",
                },
            }
        ]

    return rows


def summarize_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"n": 0}
    scores = [r.get("score") for r in rows if isinstance(r.get("score"), (int, float))]
    return {
        "n": len(rows),
        "n_models": len({r.get("model_id") for r in rows}),
        "n_tasks": len({r.get("task_id") for r in rows}),
        "best_score": max(scores) if scores else None,
        "mean_score": round(sum(scores) / len(scores), 4) if scores else None,
    }
