"""Speed benchmark: throughput + latency across short/medium/long/coding/agent prompts.

Methodology (recorded in every row so it's never ambiguous):
  - a warm-up call (warmup_tokens) runs first and is EXCLUDED from results.
  - each measured prompt runs once, streaming, so first-token latency is real.
  - token counts are API-reported when available; otherwise estimated and the
    row is flagged tokens_estimated=true.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from ..adapters.llama_bench_adapter import derive_llama_bench_fields
from ..config import ModelSpec, load_tasks
from ..schemas.result import Category
from .base import BaseRunner

_SYNTH_DOC = (
    "Modern integrated graphics architectures share a single memory controller "
    "between the CPU and GPU. On an AMD Ryzen AI APU the LPDDR5X pool is unified, "
    "so model weights do not need to be copied across a PCIe bus before inference. "
    "Memory bandwidth, not raw compute, is usually the binding constraint for "
    "decode throughput on these parts. Mixture-of-experts models activate only a "
    "fraction of their parameters per token, so a 30B MoE with ~3B active behaves "
    "much more like a 3B dense model for bandwidth purposes while retaining the "
    "quality headroom of the full parameter count. Quantization to 4 bits roughly "
    "halves the bytes moved per token versus 8-bit, directly improving tok/s. "
)


def _make_long_prompt(instruction: str, target_tokens: int = 2500) -> str:
    reps = max(1, (target_tokens * 4) // len(_SYNTH_DOC))
    return _SYNTH_DOC * reps + "\n\n" + instruction


class SpeedRunner(BaseRunner):
    category = Category.SPEED

    def __init__(self, client, **kw):
        super().__init__(client, **kw)
        self.cfg = load_tasks().get("speed", {})

    def _prompt_text(self, p: Dict[str, Any]) -> str:
        if p.get("kind") == "long":
            return _make_long_prompt(p["text"])
        return p["text"]

    def run_model(self, model: ModelSpec, max_tokens: Optional[int] = None) -> List[Dict[str, Any]]:
        max_tokens = max_tokens or self.cfg.get("max_tokens", 512)
        warmup_tokens = self.cfg.get("warmup_tokens", 8)
        prompts = self.cfg.get("prompts", [])

        # llama-bench fields draw on the model's catalog entry (quant/checkpoint).
        try:
            meta = self.client.model_metadata(model.id)  # type: ignore[attr-defined]
        except Exception:
            meta = {}

        # ---- warm-up (excluded) ----
        self.log(f"  [warmup] {model.display_name} ...")
        self.client.chat(
            model.id,
            [{"role": "user", "content": "Warm up. Reply with the single word: ready."}],
            max_tokens=warmup_tokens, temperature=0.0,
        )
        time.sleep(1.0)

        rows: List[Dict[str, Any]] = []
        for p in prompts:
            pid = p["id"]
            res = self.new_result(
                model,
                benchmark_name=f"speed:{p.get('kind', pid)}",
                task_id=pid,
                prompt_id=pid,
            )
            text = self._prompt_text(p)
            with self.metrics_scope(full=True) as scope:
                chat = self.client.chat(
                    model.id,
                    [{"role": "user", "content": text}],
                    max_tokens=max_tokens, temperature=0.0, stream=True,
                )
            res.metrics_before = scope.before
            res.metrics_during = scope.during
            res.metrics_after = scope.after
            res.elapsed_sec = round(chat.elapsed_sec, 3)
            res.first_token_latency_sec = chat.first_token_latency_sec
            res.prompt_tokens = chat.prompt_tokens
            res.completion_tokens = chat.completion_tokens
            res.total_tokens = chat.total_tokens
            res.tokens_estimated = chat.tokens_estimated
            # llama-bench-compatible fields (honest: null + reason where unknown)
            lb_fields, lb_prov = derive_llama_bench_fields(chat, model=model, meta=meta)
            for k, v in lb_fields.items():
                setattr(res, k, v)
            res.extra["llama_bench"] = lb_prov
            if not chat.ok:
                res.success = False
                res.error_type = chat.error_type
                res.error_message = chat.error_message
                self.log(f"  [{pid}] FAIL: {chat.error_type} {chat.error_message}")
            else:
                res.success = True
                res.notes = f"methodology=stream; warmup_excluded; max_tokens={max_tokens}"
                self.emit(res)
                tps = res.output_tokens_per_sec
                self.log(
                    f"  [{pid}] {tps} tok/s out "
                    f"({res.completion_tokens} tok / {res.elapsed_sec}s, "
                    f"ftl={res.first_token_latency_sec}s"
                    f"{', est' if res.tokens_estimated else ''})"
                )
                rows.append(res.to_dict())
                continue
            self.emit(res)
            rows.append(res.to_dict())
        return rows
