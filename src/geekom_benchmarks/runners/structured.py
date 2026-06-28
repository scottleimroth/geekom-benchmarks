"""Structured-output reliability: valid JSON, schema-conformance, content, no prose.

Scores five sub-skills (produce flat/nested, extract, enum, repair). Each trial's
score in 0..1 is the mean of the checks that apply:
  valid_json, schema_valid, content_correct (when an `expect` is given),
  no_extra_prose. success = score == 1.0.

Uses a small built-in validator for the JSON-Schema subset used in tasks.yaml so
the suite has no hard dependency on `jsonschema`.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..config import ModelSpec, load_tasks
from ..schemas.result import Category, ErrorType
from .base import BaseRunner

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Tuple[Optional[Any], bool]:
    """Return (parsed, had_extra_prose). Tries fenced block, then first {...}/[...]."""
    if text is None:
        return None, False
    raw = text.strip()
    had_prose = False
    m = _FENCE.search(raw)
    if m:
        candidate = m.group(1).strip()
        had_prose = bool(raw.replace(m.group(0), "").strip())
    else:
        # find first balanced-looking object/array
        start = min([i for i in (raw.find("{"), raw.find("[")) if i >= 0] or [-1])
        if start < 0:
            return None, bool(raw)
        had_prose = start > 0 or not (raw.endswith("}") or raw.endswith("]"))
        candidate = raw[start:]
    # progressively trim from the end to find valid JSON
    for end in range(len(candidate), 0, -1):
        try:
            return json.loads(candidate[:end]), had_prose or end != len(candidate)
        except json.JSONDecodeError:
            continue
    return None, True


def validate_schema(obj: Any, schema: Dict[str, Any]) -> List[str]:
    """Minimal JSON-Schema validator. Returns a list of error strings ([] == valid)."""
    errs: List[str] = []

    def _check(o: Any, s: Dict[str, Any], path: str) -> None:
        t = s.get("type")
        if t == "object":
            if not isinstance(o, dict):
                errs.append(f"{path}: expected object")
                return
            for req in s.get("required", []):
                if req not in o:
                    errs.append(f"{path}.{req}: missing required")
            props = s.get("properties", {})
            if s.get("additionalProperties") is False:
                for k in o:
                    if k not in props:
                        errs.append(f"{path}.{k}: additional property not allowed")
            for k, sub in props.items():
                if k in o:
                    _check(o[k], sub, f"{path}.{k}")
        elif t == "array":
            if not isinstance(o, list):
                errs.append(f"{path}: expected array")
                return
            item_s = s.get("items")
            if item_s:
                for i, it in enumerate(o):
                    _check(it, item_s, f"{path}[{i}]")
        elif t == "integer":
            if isinstance(o, bool) or not isinstance(o, int):
                errs.append(f"{path}: expected integer")
        elif t == "number":
            if isinstance(o, bool) or not isinstance(o, (int, float)):
                errs.append(f"{path}: expected number")
        elif t == "string":
            if not isinstance(o, str):
                errs.append(f"{path}: expected string")
        elif t == "boolean":
            if not isinstance(o, bool):
                errs.append(f"{path}: expected boolean")
        if "enum" in s and o not in s["enum"]:
            errs.append(f"{path}: {o!r} not in enum {s['enum']}")

    _check(obj, schema, "$")
    return errs


class StructuredRunner(BaseRunner):
    category = Category.STRUCTURED

    def __init__(self, client, **kw):
        super().__init__(client, **kw)
        self.cfg = load_tasks().get("structured_output", {})

    def run_model(self, model: ModelSpec) -> List[Dict[str, Any]]:
        max_tokens = self.cfg.get("max_tokens", 512)
        rows: List[Dict[str, Any]] = []
        for case in self.cfg.get("cases", []):
            cid = case["id"]
            res = self.new_result(model, benchmark_name=f"structured:{case.get('kind', cid)}",
                                  task_id=cid, prompt_id=cid)
            with self.metrics_scope(full=False) as scope:
                chat = self.client.chat(
                    model.id,
                    [{"role": "user", "content": case["instruction"]}],
                    max_tokens=max_tokens, temperature=0.0,
                )
            res.metrics_before, res.metrics_after = scope.before, scope.after
            res.elapsed_sec = round(chat.elapsed_sec, 3)
            res.prompt_tokens, res.completion_tokens = chat.prompt_tokens, chat.completion_tokens
            res.total_tokens, res.tokens_estimated = chat.total_tokens, chat.tokens_estimated
            if not chat.ok:
                res.success = False
                res.error_type = chat.error_type
                res.error_message = chat.error_message
                self.emit(res)
                rows.append(res.to_dict())
                continue

            parsed, had_prose = extract_json(chat.content)
            checks: Dict[str, bool] = {}
            checks["valid_json"] = parsed is not None
            schema = case.get("schema")
            if parsed is not None and schema:
                checks["schema_valid"] = not validate_schema(parsed, schema)
            elif schema:
                checks["schema_valid"] = False
            checks["no_extra_prose"] = not had_prose
            expect = case.get("expect")
            if expect:
                checks["content_correct"] = isinstance(parsed, dict) and all(
                    str(parsed.get(k)) == str(v) for k, v in expect.items()
                )
            score = sum(1 for v in checks.values() if v) / max(1, len(checks))
            res.score = round(score, 3)
            res.success = score == 1.0
            if not checks["valid_json"]:
                res.error_type = ErrorType.INVALID_JSON
            elif not checks.get("schema_valid", True):
                res.error_type = ErrorType.SCHEMA_INVALID
            elif expect and not checks.get("content_correct", True):
                res.error_type = ErrorType.WRONG_CONTENT
            elif not res.success:
                res.error_type = ErrorType.OTHER
            res.extra = {"checks": checks, "parsed_ok": parsed is not None}
            res.notes = f"checks={checks}"
            self.emit(res)
            rows.append(res.to_dict())
            self.log(f"  [{cid}] score={res.score} {checks}")
        return rows
