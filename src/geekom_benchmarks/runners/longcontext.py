"""Long-context benchmark: needle-in-haystack retrieval at increasing context sizes.

Conservative by design: starts at 4K and only attempts a size the model's
configured context_window can hold. A unique needle fact is injected at the
begin/middle/end; the model must retrieve it AND honor an output constraint
(answer with the code only), which detects constraint-forgetting.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..config import ModelSpec, load_tasks
from ..schemas.result import Category, ErrorType
from .base import BaseRunner

_FILLER = (
    "The unified memory controller streams weights directly to the integrated GPU. "
    "Bandwidth is the binding constraint for decode throughput on these parts. "
    "Mixture-of-experts models activate a fraction of parameters per token. "
)


def _build_haystack(target_tokens: int, needle: str, position: str) -> str:
    # ~4 chars/token; reserve room for the needle
    units = max(4, (target_tokens * 4) // len(_FILLER))
    body = [_FILLER] * units
    needle_line = f"\n[IMPORTANT FACT] The secret access code is {needle}.\n"
    if position == "begin":
        idx = 1
    elif position == "end":
        idx = len(body) - 1
    else:
        idx = len(body) // 2
    body.insert(idx, needle_line)
    return "".join(body)


class LongContextRunner(BaseRunner):
    category = Category.LONG_CONTEXT

    def __init__(self, client, **kw):
        super().__init__(client, **kw)
        self.cfg = load_tasks().get("long_context", {})

    def run_model(self, model: ModelSpec) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        lengths = self.cfg.get("lengths", [4000, 8000, 16000])
        positions = self.cfg.get("needle_positions", ["begin", "middle", "end"])
        ctx_win = model.context_window or 8192
        for length in lengths:
            # need headroom for prompt scaffold + output; require 1.5x
            if length * 1.5 > ctx_win:
                res = self.new_result(model, benchmark_name=f"longctx:{length}",
                                      task_id=f"{length}_skip", prompt_id=str(length))
                res.success = False
                res.error_type = ErrorType.SKIPPED
                res.error_message = f"context_window {ctx_win} too small for {length} tokens"
                res.notes = "SKIPPED"
                self.emit(res)
                rows.append(res.to_dict())
                continue
            for pos in positions:
                needle = f"GEEKOM-{length}-{pos[:3].upper()}-{length % 97:02d}"
                hay = _build_haystack(length, needle, pos)
                prompt = (
                    hay
                    + "\n\nThe text above contains exactly one line marked [IMPORTANT FACT] "
                    "with a secret access code. Reply with ONLY the code, nothing else."
                )
                res = self.new_result(model, benchmark_name=f"longctx:{length}:{pos}",
                                      task_id=f"{length}_{pos}", prompt_id=f"{length}_{pos}")
                with self.metrics_scope(full=False) as scope:
                    chat = self.client.chat(model.id, [{"role": "user", "content": prompt}],
                                            max_tokens=self.cfg.get("max_tokens", 256), temperature=0.0)
                res.metrics_before, res.metrics_after = scope.before, scope.after
                res.elapsed_sec = round(chat.elapsed_sec, 3)
                res.prompt_tokens, res.completion_tokens = chat.prompt_tokens, chat.completion_tokens
                res.total_tokens, res.tokens_estimated = chat.total_tokens, chat.tokens_estimated
                if not chat.ok:
                    res.success = False
                    res.error_type = chat.error_type
                    res.error_message = chat.error_message
                else:
                    found = needle in chat.content
                    constraint_ok = len(chat.content.strip()) <= len(needle) + 30  # didn't ramble
                    res.success = found
                    res.score = 1.0 if found else 0.0
                    res.error_type = ErrorType.NONE if found else ErrorType.WRONG_CONTENT
                    res.extra = {"needle": needle, "position": pos, "context_tokens": length,
                                 "found": found, "honored_output_constraint": constraint_ok,
                                 "answer": chat.content[:200]}
                self.emit(res)
                rows.append(res.to_dict())
                self.log(f"  [{length}/{pos}] found={res.extra.get('found') if res.extra else False} "
                         f"({res.prompt_tokens} prompt tok)")
        return rows
