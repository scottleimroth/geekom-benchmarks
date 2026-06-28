"""MLPerf Client importer.

MLPerf Client runs its own runtime stack, so this adapter only imports result JSON
artifacts into the canonical schema for cross-device / cross-vendor comparison.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


CATEGORY = "mlperf_client"


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def _result_files(path: str) -> List[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.exists():
        return []
    return [f for f in sorted(p.rglob("*.json")) if f.is_file()]


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _walk_payload(payload: Any, *, seen: Optional[set[int]] = None) -> List[tuple[str, float]]:
    """Walk arbitrary JSON and return (key_path, numeric_value) for leaves."""
    seen = seen if seen is not None else set()
    out: List[tuple[str, float]] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            if id(v) in seen:
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.append((str(k), _as_float(v) or 0.0))
                continue
            if isinstance(v, (dict, list)):
                seen.add(id(v))
                for sub_k, sub_v in _walk_payload(v, seen=seen):
                    out.append((f"{k}.{sub_k}", sub_v))
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            if id(item) in seen:
                continue
            if isinstance(item, (dict, list)):
                seen.add(id(item))
                for sub_k, sub_v in _walk_payload(item, seen=seen):
                    out.append((f"[{idx}].{sub_k}", sub_v))
            elif isinstance(item, (int, float)) and not isinstance(item, bool):
                out.append((f"[{idx}]", _as_float(item) or 0.0))
    return out


def _find_string(payload: Dict[str, Any], keys: List[str], default: str = "unknown") -> str:
    wanted = {
        "".join(ch for ch in key.lower() if ch.isalnum())
        for key in keys
    }
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = _find_string(value, keys, default=default)
            if nested != default:
                return nested
    for key, value in payload.items():
        normalized = "".join(ch for ch in str(key).lower() if ch.isalnum())
        if normalized in wanted and isinstance(value, str) and value.strip():
            return value.strip()
    for value in payload.values():
        if isinstance(value, dict):
            nested = _find_string(value, keys, default=default)
            if nested != default:
                return nested
    return default


def import_results(path: str, *, model_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Import MLPerf Client JSON artifacts into canonical row dicts."""
    files = _result_files(path)
    if not files:
        raise FileNotFoundError(f"No JSON files found for MLPerf import at {path}")

    rows: List[Dict[str, Any]] = []
    for f in files:
        payload = _load_json(f)
        if not payload:
            continue

        detected_model = (
            model_id
            or _find_string(payload, ["model", "model_id", "model_name", "Model Name", "ModelName", "name"])
            or "unknown"
        )
        runtime = _find_string(
            payload,
            ["runtime", "device", "backend", "execution", "engine", "Execution Provider Name", "Device Type"],
            default="",
        )

        metrics = _walk_payload(payload)
        recognized = [
            (k, v) for k, v in metrics
            if any(
                token in k.lower()
                for token in [
                    "tokens_per_second",
                    "tok",
                    "/s",
                    "throughput",
                    "ttft",
                    "time_to_first_token",
                    "time to first token",
                    "token generation rate",
                    "generated tokens",
                    "input tokens",
                ]
            )
        ]

        if not recognized:
            recognized = metrics

        added_for_file = False
        for key, value in recognized:
            lname = key.lower()
            if not isinstance(value, (int, float)):
                continue

            row: Dict[str, Any] = {
                "model_id": detected_model,
                "model_display_name": detected_model,
                "benchmark_name": f"{CATEGORY}:{key}",
                "task_id": key,
                "success": True,
                "notes": f"MLPerf Client metric '{key}'",
                "extra": {
                    "suite": CATEGORY,
                    "output_file": str(f).replace("\\", "/"),
                    "runtime": runtime,
                    "metric_key": key,
                },
                "raw_response_path": str(f).replace("\\", "/"),
            }

            if "time_to_first_token" in lname or "time to first token" in lname or "ttft" in lname:
                # If ms was accidentally stored, normalize to seconds.
                if value > 60:
                    value /= 1000.0
                row["first_token_latency_sec"] = float(value)
            elif "tokens_per_second" in lname or "throughput" in lname or "token generation rate" in lname:
                row["output_tokens_per_sec"] = float(value)
                row["tg_tokens_per_sec"] = float(value)
            elif "generated tokens" in lname:
                row["completion_tokens"] = int(value)
                row["tokens_estimated"] = False
            elif "input tokens" in lname:
                row["prompt_tokens"] = int(value)
                row["tokens_estimated"] = False
            else:
                row["score"] = float(value)

            rows.append(row)
            added_for_file = True

        if not added_for_file and model_id:
            rows.append(
                {
                    "model_id": model_id,
                    "model_display_name": model_id,
                    "benchmark_name": f"{CATEGORY}:import",
                    "task_id": "import",
                    "success": False,
                    "error_type": "other",
                    "error_message": "No recognizable MLPerf metrics found",
                    "notes": f"Checked {f}",
                    "extra": {
                        "suite": CATEGORY,
                        "warning": "no recognizable metrics found",
                    },
                }
            )

    if not rows:
        return [
            {
                "model_id": model_id or "unknown",
                "model_display_name": model_id or "unknown",
                "benchmark_name": f"{CATEGORY}:import",
                "task_id": "import",
                "success": False,
                "error_type": "other",
                "error_message": "Could not parse recognizable MLPerf metrics",
                "notes": f"Checked {len(files)} json file(s) under {path}",
                "extra": {"suite": CATEGORY, "warning": "no recognized metrics found"},
            }
        ]

    return rows
