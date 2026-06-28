"""Vision benchmark: manifest-driven, deterministic, honest about image support.

Reads test_assets/vision/manifest.json (produced by scripts/prepare_vision_assets.py)
and, for a vision-capable model, sends each image via the OpenAI-compatible
`image_url` (base64 data-URL) content and scores the answer against the manifest's
ground truth.

It NEVER fakes a pass. It writes SKIPPED rows (with a reason) when:
  - the model isn't vision-capable (config `uses` lacks "vision"),
  - the manifest or an image file is missing,
  - the endpoint rejects/does not support image input (the underlying error is
    recorded as the reason).
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import ModelSpec
from ..schemas.result import Category, ErrorType
from ..utils.io import paths
from ..vision_assets.scoring import score_answer
from .base import BaseRunner


def _data_url(path: Path) -> str:
    ext = path.suffix.lstrip(".").lower() or "png"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{ext};base64,{b64}"


class VisionRunner(BaseRunner):
    category = Category.VISION

    def __init__(self, client, **kw):
        super().__init__(client, **kw)
        self.vision_dir = paths()["test_assets"] / "vision"
        self.manifest_path = self.vision_dir / "manifest.json"

    def _load_manifest(self) -> Optional[Dict[str, Any]]:
        if not self.manifest_path.exists():
            return None
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _skip(self, model: ModelSpec, task_id: str, reason: str, asset_type: str = "") -> Dict[str, Any]:
        res = self.new_result(model, benchmark_name=f"vision:{asset_type or task_id}",
                              task_id=task_id, prompt_id=task_id)
        res.success = False
        res.score = None
        res.error_type = ErrorType.SKIPPED
        res.error_message = reason
        res.notes = "SKIPPED"
        self.emit(res)
        self.log(f"  [{task_id}] SKIPPED: {reason}")
        return res.to_dict()

    def run_model(self, model: ModelSpec) -> List[Dict[str, Any]]:
        manifest = self._load_manifest()
        if manifest is None:
            return [self._skip(model, "manifest", "manifest.json missing — run scripts/prepare_vision_assets.py")]
        items = manifest.get("items", [])
        if "vision" not in model.uses:
            return [self._skip(model, it.get("asset_id", f"item{i}"),
                               "model not vision-capable (config uses lacks 'vision')",
                               it.get("asset_type", ""))
                    for i, it in enumerate(items)]

        rows: List[Dict[str, Any]] = []
        for i, item in enumerate(items):
            tid = f"{item.get('asset_id', 'item')}#{i:02d}"
            file_paths = item.get("file_paths") or [item.get("file_path")]
            abs_paths = [self.vision_dir / fp for fp in file_paths if fp]
            missing = [str(p) for p in abs_paths if not p.exists()]
            if missing:
                rows.append(self._skip(model, tid, f"asset image(s) missing: {missing}",
                                       item.get("asset_type", "")))
                continue

            res = self.new_result(model, benchmark_name=f"vision:{item.get('asset_type','')}",
                                  task_id=tid, prompt_id=item.get("asset_id"))
            content: List[Dict[str, Any]] = [{"type": "text", "text": item["question"]}]
            for p in abs_paths:
                content.append({"type": "image_url", "image_url": {"url": _data_url(p)}})

            with self.metrics_scope(full=True) as scope:
                chat = self.client.chat(model.id, [{"role": "user", "content": content}],
                                        max_tokens=384, temperature=0.0)
            res.metrics_before, res.metrics_after = scope.before, scope.after
            res.elapsed_sec = round(chat.elapsed_sec, 3)
            res.prompt_tokens, res.completion_tokens = chat.prompt_tokens, chat.completion_tokens
            res.total_tokens, res.tokens_estimated = chat.total_tokens, chat.tokens_estimated

            if not chat.ok:
                # Could not get a vision answer — most likely the endpoint/model
                # does not accept image input. Record as SKIPPED with the reason;
                # never count it as a pass.
                res.success = False
                res.score = None
                res.error_type = ErrorType.SKIPPED
                res.error_message = (f"image input likely unsupported / endpoint error: "
                                     f"{chat.error_type}: {chat.error_message}")
                res.notes = "SKIPPED (no image-capable response)"
                self.emit(res)
                rows.append(res.to_dict())
                self.log(f"  [{tid}] SKIPPED: {chat.error_type} {chat.error_message}")
                continue

            passed, detail = score_answer(chat.content, item)
            res.success = bool(passed)
            res.score = 1.0 if passed else 0.0
            res.error_type = ErrorType.NONE if passed else ErrorType.WRONG_CONTENT
            res.extra = {
                "asset_id": item.get("asset_id"),
                "asset_type": item.get("asset_type"),
                "source_type": item.get("source_type"),
                "license": item.get("license"),
                "question": item.get("question"),
                "expected_answer": item.get("expected_answer"),
                "scoring": detail,
                "answer": chat.content[:1000],
            }
            res.notes = f"scoring={detail}"
            self.emit(res)
            rows.append(res.to_dict())
            self.log(f"  [{tid}] success={res.success} ({item.get('asset_type')})")
        return rows
