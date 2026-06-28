"""Tool-calling reliability: 2-tool multi-step task in three exposure modes.

Task: get_paper_metadata(title) -> save_note(text containing the correct year).
Modes:
  parallel - both tools exposed, parallel_tool_calls=True
  nopar    - both tools exposed, parallel_tool_calls=False
  strict   - tools exposed one at a time (phase 1 metadata; phase 2 save).

STRICT IS A FIRST-CLASS ORCHESTRATION MODE, not a workaround. The report
compares loose exposure vs. staged orchestration explicitly.

Refactored from the original scripts/tool_call_reliability_modes.py:
  - scratch dir is now repo-relative (was a hard-coded WSL path)
  - results are emitted in the unified BenchmarkResult schema (one row/trial)
  - failure categories map onto canonical error_type values.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..adapters import bfcl_lite
from ..config import ModelSpec, load_tasks
from ..schemas.result import Category, ErrorType
from ..utils.io import paths, sanitize
from .base import BaseRunner

TOOL_META = {
    "type": "function",
    "function": {
        "name": "get_paper_metadata",
        "description": "Return structured metadata for a paper title.",
        "parameters": {
            "type": "object",
            "properties": {"title": {"type": "string", "description": "Exact paper title."}},
            "required": ["title"],
            "additionalProperties": False,
        },
    },
}
TOOL_SAVE = {
    "type": "function",
    "function": {
        "name": "save_note",
        "description": "Save a short note to disk.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Note text to save."}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}

# Map the human failure category -> canonical error_type
_CAT_TO_ERR = {
    "pass": ErrorType.NONE,
    "called tools but saved wrong year": ErrorType.WRONG_YEAR,
    "malformed tool-call JSON": ErrorType.INVALID_JSON,
    "didn't call the first tool": ErrorType.MISSING_TOOL,
    "called wrong tool / wrong args": ErrorType.INVALID_TOOL_ARGS,
    "got metadata but never saved note": ErrorType.MISSING_TOOL,
    "api_error": ErrorType.API_ERROR,
    "other": ErrorType.OTHER,
}


class ToolReliabilityRunner(BaseRunner):
    category = Category.TOOL

    def __init__(self, client, **kw):
        super().__init__(client, **kw)
        cfg = load_tasks().get("tool_reliability", {})
        self.papers: Dict[str, int] = cfg.get("papers", {})
        self.default_trials: int = cfg.get("trials", 20)

    # -- tool execution -----------------------------------------------------
    def _get_meta(self, title: str) -> Dict[str, Any]:
        return {
            "title": title,
            "year": self.papers.get(title, 1901),
            "authors": "Smith & Jones",
            "journal": "Journal of Testing",
        }

    def _do_save(self, text: str, scratch: Path, counter: Dict[str, int]) -> Dict[str, Any]:
        scratch.mkdir(parents=True, exist_ok=True)
        counter["n"] += 1
        p = scratch / f"note_{counter['n']:03d}.txt"
        p.write_text(text, encoding="utf-8")
        return {"status": "saved", "path": str(p)}

    def _exec_call(self, call: Dict[str, Any], scratch: Path, counter: Dict[str, int]) -> Dict[str, Any]:
        name = call["function"]["name"]
        raw = call["function"].get("arguments", "")
        try:
            args = json.loads(raw or "{}")
            if not isinstance(args, dict):
                raise ValueError("not an object")
        except Exception as e:
            return {"tool": name, "arguments": None, "arguments_raw": raw,
                    "result": {"error": f"malformed:{e}"}, "malformed": True}
        if name == "get_paper_metadata":
            r = self._get_meta(str(args.get("title") or ""))
        elif name == "save_note":
            r = self._do_save(str(args.get("text") or ""), scratch, counter)
        else:
            r = {"error": f"unknown_tool:{name}"}
        return {"tool": name, "arguments": args, "result": r, "malformed": False}

    def _hist(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        h = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            h["tool_calls"] = msg["tool_calls"]
        return h

    # -- trial scoring ------------------------------------------------------
    def _score(self, title: str, events: List[Dict[str, Any]], api_error: bool) -> Tuple[bool, str]:
        expected = self.papers[title]
        meta = [e for e in events if e["tool"] == "get_paper_metadata"]
        saves = [e for e in events if e["tool"] == "save_note"]
        wrong = [e for e in events if e["tool"] not in {"get_paper_metadata", "save_note"}]
        malformed = any(e["malformed"] for e in events)
        correct_meta = any(
            (e.get("arguments") or {}).get("title") == title
            and (e.get("result") or {}).get("year") == expected
            for e in meta
        )
        saved_texts = [str((e.get("arguments") or {}).get("text") or "") for e in saves]
        saved_year_ok = any(str(expected) in t for t in saved_texts)
        passed = bool(correct_meta and saves and saved_year_ok and not malformed and not wrong)
        if api_error:
            cat = "api_error"
        elif passed:
            cat = "pass"
        elif malformed:
            cat = "malformed tool-call JSON"
        elif not meta:
            cat = "didn't call the first tool"
        elif wrong or not correct_meta:
            cat = "called wrong tool / wrong args"
        elif correct_meta and saves and not saved_year_ok:
            cat = "called tools but saved wrong year"
        elif correct_meta and not saves:
            cat = "got metadata but never saved note"
        else:
            cat = "other"
        return passed, cat

    # -- trial runners ------------------------------------------------------
    def _sys_user(self, title: str) -> List[Dict[str, Any]]:
        return [
            {"role": "system", "content": "You are testing tool use. Use the provided tools. When a tool returns data, read it before deciding the next tool call."},
            {"role": "user", "content": f"Look up the paper titled '{title}', then save a note that states what year it was published."},
        ]

    def _run_strict(self, model_id, title, scratch, counter):
        messages = self._sys_user(title)
        events: List[Dict[str, Any]] = []
        c = self.client.chat(model_id, messages, tools=[TOOL_META], tool_choice="auto",
                             parallel_tool_calls=False, temperature=0.0)
        if not c.ok:
            return events, True
        messages.append(self._hist(c.raw_message))
        for call in (c.tool_calls or []):
            ev = self._exec_call(call, scratch, counter)
            events.append(ev)
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(ev["result"], ensure_ascii=False)})
        if events and not any(e["malformed"] for e in events):
            c = self.client.chat(model_id, messages, tools=[TOOL_SAVE], tool_choice="auto",
                                 parallel_tool_calls=False, temperature=0.0)
            if not c.ok:
                return events, True
            messages.append(self._hist(c.raw_message))
            for call in (c.tool_calls or []):
                ev = self._exec_call(call, scratch, counter)
                events.append(ev)
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(ev["result"], ensure_ascii=False)})
        return events, False

    def _run_both(self, model_id, title, scratch, counter, parallel_flag):
        messages = self._sys_user(title)
        events: List[Dict[str, Any]] = []
        for _ in range(4):
            c = self.client.chat(model_id, messages, tools=[TOOL_META, TOOL_SAVE], tool_choice="auto",
                                 parallel_tool_calls=parallel_flag, temperature=0.0)
            if not c.ok:
                return events, True
            messages.append(self._hist(c.raw_message))
            calls = c.tool_calls or []
            if not calls:
                break
            for call in calls:
                ev = self._exec_call(call, scratch, counter)
                events.append(ev)
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(ev["result"], ensure_ascii=False)})
            if any(e["malformed"] for e in events[-len(calls):]):
                break
        return events, False

    # -- public -------------------------------------------------------------
    def run_model_mode(self, model: ModelSpec, mode: str, trials: Optional[int] = None) -> Dict[str, Any]:
        trials = trials or self.default_trials
        # Accept BFCL-lite mode names (serial/staged/multistep) as aliases.
        mode = bfcl_lite.resolve_mode(mode)
        exposure = bfcl_lite.exposure_for_mode(mode)
        scratch = paths()["raw"] / sanitize(self.category) / "scratch" / f"{sanitize(model.id)}__{mode}"
        scratch.mkdir(parents=True, exist_ok=True)
        for old in scratch.glob("note_*.txt"):
            old.unlink()
        counter = {"n": 0}
        titles = list(self.papers.keys())
        cats: Counter = Counter()
        passes = 0
        # repeat the title list until we have `trials` trials
        t = 0
        while t < trials:
            for title in titles:
                if t >= trials:
                    break
                t += 1
                res = self.new_result(
                    model,
                    benchmark_name=f"tool:{mode}",
                    task_id=f"{mode}#{t:02d}",
                    prompt_id=title,
                )
                import time as _t
                t0 = _t.time()
                if mode == "strict":
                    events, api_err = self._run_strict(model.id, title, scratch, counter)
                else:
                    events, api_err = self._run_both(model.id, title, scratch, counter, mode == "parallel")
                res.elapsed_sec = round(_t.time() - t0, 3)
                passed, cat = self._score(title, events, api_err)
                cats[cat] += 1
                if passed:
                    passes += 1
                res.success = passed
                res.score = 1.0 if passed else 0.0
                res.error_type = _CAT_TO_ERR.get(cat, ErrorType.OTHER) if not passed else ErrorType.NONE
                res.error_message = None if passed else cat
                res.extra = {
                    "mode": mode,
                    "title": title,
                    "failure_category": None if passed else cat,
                    "tool_events": events,
                    "bfcl": bfcl_lite.bfcl_label(mode, None if passed else cat, passed),
                }
                self.emit(res)
            self.log(f"    [{model.display_name} {mode}] {t}/{trials} done, {passes} passed")
        return {
            "model": model.id,
            "model_display_name": model.display_name,
            "mode": mode,
            "bfcl_exposure": exposure,
            "bfcl_task_class": bfcl_lite.TASK_CLASS,
            "trials": trials,
            "passes": passes,
            "score_str": f"{passes}/{trials}",
            "failure_categories": {k: v for k, v in cats.items() if k != "pass"},
            "bfcl_outcomes": {bfcl_lite.classify_outcome(k, k == "pass"): v for k, v in cats.items()},
        }
