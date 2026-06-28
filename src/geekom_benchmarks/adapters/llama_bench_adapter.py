"""llama-bench compatibility adapter.

`llama.cpp/llama-bench` reports prompt-processing (pp) and token-generation (tg)
throughput separately, plus the launch config (n_gpu_layers, batch, ubatch,
flash_attn, model file). This adapter derives the equivalent fields from a
geekom-benchmarks ChatResult + the Lemonade model metadata, so our speed results
can be read side-by-side with llama-bench numbers.

HONESTY RULE: anything Lemonade's OpenAI-compatible API does not expose is left
`None` and a reason is recorded in the returned `provenance` dict. We never
fabricate a llama-bench field.

What we CAN derive honestly:
  - pp_tokens          = prompt_tokens (API-reported)
  - tg_tokens          = completion_tokens (API-reported)
  - pp_tokens_per_sec  = pp_tokens / prefill_time, where prefill_time is the
                         measured first-token latency (time-to-first-token is the
                         prompt-processing phase). Marked as an ftl-derived
                         estimate in provenance.
  - tg_tokens_per_sec  = tg_tokens / (elapsed - prefill_time)  (decode phase)
  - backend            = declared by config (llama.cpp Vulkan on the GEEKOM)
  - quant              = declared by the model catalog
  - model_file         = the .gguf filename echoed in the server response
  - system build       = llama.cpp build from system_fingerprint (kept in provenance)

What Lemonade does NOT expose (=> None + reason):
  - gpu_layers, batch_size, ubatch_size, flash_attention, model_hash

TODO: if Lemonade later adds a launch-params or /props endpoint, read
n_gpu_layers / n_batch / n_ubatch / flash_attn / gguf sha here instead of null.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def derive_llama_bench_fields(
    chat: Any,                 # clients.base.ChatResult
    *,
    model: Any = None,         # config.ModelSpec (for quant/backend declarations)
    meta: Optional[Dict[str, Any]] = None,  # Lemonade /models entry
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return (fields, provenance).

    `fields` maps directly onto BenchmarkResult's llama-bench columns. Unknown
    fields are present and set to None. `provenance` documents source/reason for
    each field (esp. the nulls).
    """
    meta = meta or {}
    provenance: Dict[str, Any] = {}

    pp_tokens = chat.prompt_tokens
    tg_tokens = chat.completion_tokens
    elapsed = chat.elapsed_sec or 0.0
    ftl = chat.first_token_latency_sec

    pp_tps: Optional[float] = None
    tg_tps: Optional[float] = None
    if pp_tokens and ftl and ftl > 0:
        pp_tps = round(pp_tokens / ftl, 2)
        provenance["pp_tokens_per_sec"] = "estimate: prompt_tokens / first_token_latency (ttft = prefill)"
    else:
        provenance["pp_tokens_per_sec"] = "null: needs prompt_tokens and first_token_latency (streaming only)"
    if tg_tokens and elapsed and ftl is not None and (elapsed - ftl) > 0:
        tg_tps = round(tg_tokens / (elapsed - ftl), 2)
        provenance["tg_tokens_per_sec"] = "estimate: completion_tokens / (elapsed - ttft) (decode phase)"
    else:
        provenance["tg_tokens_per_sec"] = "null: needs completion_tokens and a positive decode window"

    backend = getattr(model, "backend", None) or "llamacpp:vulkan"
    provenance["backend"] = "declared by config (hardware.yaml/models.yaml)"
    quant = getattr(model, "quant", None) or meta.get("recipe_options", {}).get("quant")
    provenance["quant"] = "declared by model catalog"

    model_file = getattr(chat, "response_model", None)
    provenance["model_file"] = (
        "from server response 'model' field" if model_file else "null: server did not echo a model filename"
    )

    # Not exposed by Lemonade's OpenAI-compatible API:
    for f in ("gpu_layers", "batch_size", "ubatch_size", "flash_attention", "model_hash"):
        provenance[f] = "null: not exposed by Lemonade /models or chat API"
    if getattr(chat, "system_fingerprint", None):
        provenance["llamacpp_build"] = chat.system_fingerprint  # extra context, not a schema field

    fields: Dict[str, Any] = {
        "pp_tokens": pp_tokens,
        "tg_tokens": tg_tokens,
        "pp_tokens_per_sec": pp_tps,
        "tg_tokens_per_sec": tg_tps,
        "backend": backend,
        "gpu_layers": None,
        "batch_size": None,
        "ubatch_size": None,
        "flash_attention": None,
        "quant": quant,
        "model_file": model_file,
        "model_hash": None,
    }
    return fields, provenance


def to_llama_bench_row(result: Dict[str, Any]) -> Dict[str, Any]:
    """Project a BenchmarkResult dict onto a llama-bench-style row (for export).

    TODO: emit llama-bench's exact CSV/markdown columns once we add an export CLI.
    """
    return {
        "model": result.get("model_file") or result.get("model_id"),
        "backend": result.get("backend"),
        "n_gpu_layers": result.get("gpu_layers"),
        "n_batch": result.get("batch_size"),
        "n_ubatch": result.get("ubatch_size"),
        "flash_attn": result.get("flash_attention"),
        "pp_t/s": result.get("pp_tokens_per_sec"),
        "tg_t/s": result.get("tg_tokens_per_sec"),
        "quant": result.get("quant"),
    }


def _read_json_lines(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    text: Optional[str] = None
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeError:
            continue
        except Exception:
            return []
    if text is None:
        return rows

    try:
        for line in text.splitlines():
            text = line.strip()
            if not text.startswith("{"):
                continue
            try:
                payload = json.loads(text)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    except Exception:
        return []
    return rows


def _discover_files(path: str) -> List[Path]:
    p = Path(path)
    if p.is_file():
        return [p]
    if not p.exists():
        return []
    return [
        f for f in sorted(p.rglob("*"))
        if f.is_file() and f.suffix.lower() in {".json", ".jsonl", ".ndjson", ".txt", ".log"}
    ]


def _model_id_from_payload(payload: Dict[str, Any]) -> str:
    model_file = str(payload.get("model_filename") or "").strip()
    if model_file:
        return Path(model_file).stem
    model_type = str(payload.get("model_type") or "").strip()
    return model_type or "unknown"


def import_results(path: str) -> List[Dict[str, Any]]:
    """Import official llama.cpp llama-bench JSON/JSONL output.

    llama-bench emits one JSON object per prompt-processing/generation case with
    `avg_ts` as tokens/sec. This importer maps those rows into the canonical
    external category while preserving the real launch parameters.
    """
    files = _discover_files(path)
    if not files:
        raise FileNotFoundError(f"No llama-bench output files found at: {path}")

    rows: List[Dict[str, Any]] = []
    for file_path in files:
        for payload in _read_json_lines(file_path):
            avg_ts = payload.get("avg_ts")
            if not isinstance(avg_ts, (int, float)):
                continue
            n_prompt = int(payload.get("n_prompt") or 0)
            n_gen = int(payload.get("n_gen") or 0)
            if n_prompt > 0 and n_gen == 0:
                mode = "pp"
            elif n_gen > 0 and n_prompt == 0:
                mode = "tg"
            else:
                mode = "pg"

            model_id = _model_id_from_payload(payload)
            source = str(file_path).replace("\\", "/")
            record: Dict[str, Any] = {
                "model_id": model_id,
                "model_display_name": model_id,
                "benchmark_name": f"llama_bench:{model_id}:{mode}",
                "task_id": f"{mode}:p{n_prompt}:g{n_gen}",
                "success": True,
                "score": float(avg_ts),
                "notes": f"official llama.cpp llama-bench {mode} throughput",
                "extra": {
                    "suite": "llama_bench",
                    "mode": mode,
                    "output_file": source,
                    "build_commit": payload.get("build_commit"),
                    "build_number": payload.get("build_number"),
                    "cpu_info": payload.get("cpu_info"),
                    "gpu_info": payload.get("gpu_info"),
                    "backends": payload.get("backends"),
                    "stddev_ts": payload.get("stddev_ts"),
                    "samples_ts": payload.get("samples_ts"),
                    "avg_ns": payload.get("avg_ns"),
                    "samples_ns": payload.get("samples_ns"),
                },
                "raw_response_path": source,
                "pp_tokens": n_prompt or None,
                "tg_tokens": n_gen or None,
                "backend": payload.get("backends"),
                "gpu_layers": payload.get("n_gpu_layers"),
                "batch_size": payload.get("n_batch"),
                "ubatch_size": payload.get("n_ubatch"),
                "flash_attention": payload.get("flash_attn"),
                "model_file": payload.get("model_filename"),
            }
            if mode == "pp":
                record["pp_tokens_per_sec"] = float(avg_ts)
                record["prompt_tokens"] = n_prompt
            elif mode == "tg":
                record["tg_tokens_per_sec"] = float(avg_ts)
                record["output_tokens_per_sec"] = float(avg_ts)
                record["completion_tokens"] = n_gen
            else:
                record["total_tokens_per_sec"] = float(avg_ts)
                record["prompt_tokens"] = n_prompt or None
                record["completion_tokens"] = n_gen or None
            rows.append(record)

    if not rows:
        return [
            {
                "model_id": "unknown",
                "model_display_name": "unknown",
                "benchmark_name": "llama_bench:import",
                "task_id": "import",
                "success": False,
                "error_type": "other",
                "error_message": "No recognizable llama-bench JSON rows found",
                "notes": f"Checked {len(files)} file(s) under {path}",
                "extra": {"suite": "llama_bench"},
                "raw_response_path": path,
            }
        ]
    return rows
