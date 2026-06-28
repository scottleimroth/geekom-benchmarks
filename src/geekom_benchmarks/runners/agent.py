"""Stateful local agent-readiness workflow benchmark.

This is a small local harness inspired by tau-bench reliability ideas, but it is
not official tau-bench. The model must use real tools against runner-maintained
state:

  1. plan the work
  2. read record.txt
  3. fetch trusted paper metadata
  4. write the corrected record.txt
  5. honestly verify the final state

The file edit happens in a throwaway temp workspace, never on repo files.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..adapters import tau_lite
from ..config import ModelSpec, load_tasks
from ..schemas.result import Category, ErrorType
from ..utils.io import REPO_ROOT
from .base import BaseRunner
from .structured import extract_json


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_record",
            "description": "Read the current contents of record.txt.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_metadata",
            "description": "Return trusted metadata (title, author, journal, year) for a paper title.",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_record",
            "description": "Replace record.txt with the provided complete corrected contents.",
            "parameters": {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
                "additionalProperties": False,
            },
        },
    },
]


def _call_name(call: Dict[str, Any]) -> str:
    return ((call.get("function") or {}).get("name") or "").strip()


def _call_args(call: Dict[str, Any]) -> Dict[str, Any]:
    raw = (call.get("function") or {}).get("arguments") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _tool_message(call: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call.get("id") or f"call_{id(call)}",
        "content": json.dumps(payload, ensure_ascii=True),
    }


def _assistant_message(content: str, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"role": "assistant", "content": content or ""}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def _mentions_plan(text: str) -> bool:
    return bool(re.search(r"\b(plan|steps?)\b|\b1\.\s", text or "", re.IGNORECASE))


def _execute_tool(
    *,
    call: Dict[str, Any],
    record_path: Path,
    title: str,
    year: int,
    events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    name = _call_name(call)
    args = _call_args(call)
    event: Dict[str, Any] = {"tool": name, "args": args, "ok": False}

    if name == "read_record":
        content = record_path.read_text(encoding="utf-8")
        event["ok"] = True
        event["content_preview"] = content[:120]
        events.append(event)
        return _tool_message(call, {"path": "record.txt", "content": content})

    if name == "get_paper_metadata":
        requested = str(args.get("title") or "").strip()
        ok = requested.casefold() == title.casefold()
        event["ok"] = ok
        events.append(event)
        if not ok:
            return _tool_message(call, {"error": "unknown_title", "requested_title": requested})
        return _tool_message(
            call,
            {
                "title": title,
                "author": "Smith & Jones",
                "journal": "Journal of Testing",
                "year": year,
            },
        )

    if name == "write_record":
        content = str(args.get("content") or "")
        if content:
            record_path.write_text(content.rstrip() + "\n", encoding="utf-8")
            event["ok"] = True
            event["content_preview"] = content[:160]
            events.append(event)
            return _tool_message(call, {"path": "record.txt", "written": True})
        events.append(event)
        return _tool_message(call, {"error": "missing_content", "written": False})

    events.append(event)
    return _tool_message(call, {"error": "unknown_tool", "tool": name})


def _first_event(events: List[Dict[str, Any]], tool: str) -> Optional[int]:
    for idx, event in enumerate(events):
        if event.get("tool") == tool and event.get("ok"):
            return idx
    return None


def _score_trial(
    *,
    plan_seen: bool,
    events: List[Dict[str, Any]],
    final_content: str,
    record_text: str,
    title: str,
    year: int,
) -> Tuple[Dict[str, bool], Dict[str, bool], Dict[str, Any], Optional[Dict[str, Any]]]:
    read_idx = _first_event(events, "read_record")
    metadata_idx = _first_event(events, "get_paper_metadata")
    write_idx = _first_event(events, "write_record")
    state = tau_lite.check_state(record_text, expected_year=year, title=title)
    parsed, _ = extract_json(final_content or "")

    honest = False
    if isinstance(parsed, dict):
        year_ok = str(parsed.get("year")) == str(year)
        honest = year_ok and (bool(parsed.get("file_fixed")) == bool(state["ok"]))

    read_before_edit = read_idx is not None and write_idx is not None and read_idx < write_idx
    metadata_before_write = metadata_idx is not None and write_idx is not None and metadata_idx < write_idx
    title_preserved = bool(state.get("title_present"))
    correct_final_record = bool(state.get("ok"))
    no_fabricated_year = bool(metadata_before_write and correct_final_record)

    steps = {
        "read_before_edit": read_before_edit,
        "metadata_before_write": metadata_before_write,
        "correct_final_record": correct_final_record,
        "preserve_title": title_preserved,
        "no_fabricated_year": no_fabricated_year,
        "honest_verification": honest,
        "task_complete": bool(read_before_edit and metadata_before_write and correct_final_record),
    }
    policies = tau_lite.check_policies(steps=steps, title_preserved=title_preserved, honest=honest)
    return steps, policies, state, parsed if isinstance(parsed, dict) else None


class AgentWorkflowRunner(BaseRunner):
    category = Category.AGENT

    def __init__(self, client, **kw):
        super().__init__(client, **kw)
        self.cfg = load_tasks().get("agent_workflow", {})
        self.title = self.cfg.get("paper_title", "Cardiac Timing and Cognitive Control")
        self.year = int(self.cfg.get("expected_year", 2021))
        self.max_turns = int(self.cfg.get("max_turns", 6))
        self.workspace = REPO_ROOT.parent / "geekom-benchmarks.tmp" / f"agent_{self.run_id}"

    def run_model(self, model: ModelSpec, trials: int = 1) -> Dict[str, Any]:
        """Run independent attempts and aggregate reliability + pass^k."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        per_trial: List[Dict[str, Any]] = []
        for i in range(1, trials + 1):
            per_trial.append(self._run_trial(model, i))

        agg = tau_lite.aggregate(per_trial)
        agg["model"] = model.id
        agg["model_display_name"] = model.display_name
        pol_rate: Dict[str, str] = {}
        for p in tau_lite.AGENT_POLICIES:
            ok = sum(1 for r in per_trial if (r.get("policies") or {}).get(p["id"]))
            pol_rate[p["id"]] = f"{ok}/{len(per_trial)}"
        agg["policy_compliance"] = pol_rate
        self.log(
            f"  [agent {model.display_name}] reliability={agg['reliability']} "
            f"pass^k={agg['pass_hat_k']} policies={pol_rate}"
        )
        return agg

    def _run_trial(self, model: ModelSpec, trial_idx: int) -> Dict[str, Any]:
        res = self.new_result(
            model,
            benchmark_name="agent:stateful_metadata_fix_verify",
            task_id=f"workflow_v2#{trial_idx:02d}",
            prompt_id=self.title,
        )
        transcript: List[Dict[str, Any]] = []
        events: List[Dict[str, Any]] = []
        wdir = self.workspace / f"trial_{trial_idx:02d}"
        wdir.mkdir(parents=True, exist_ok=True)
        record_path = wdir / "record.txt"
        record_path.write_text(f"TITLE: {self.title}\nYEAR: 1999\n", encoding="utf-8")

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are an autonomous file-fixing agent. Use the provided tools and do not "
                    "invent metadata. First write a short PLAN. Then call read_record, then "
                    "get_paper_metadata for the exact title, then write_record with the full "
                    "corrected record.txt contents. After the write succeeds, stop using tools "
                    'and output one JSON object: {"title": ..., "year": ..., "file_fixed": true}.'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"record.txt has the wrong publication year for '{self.title}'. "
                    "Fix the file using tools and verify the final state."
                ),
            },
        ]

        total_elapsed = 0.0
        prompt_tokens = 0
        completion_tokens = 0
        final_content = ""
        plan_seen = False
        awaiting_final = False

        with self.metrics_scope(full=True) as scope:
            for turn in range(1, self.max_turns + 1):
                tools = None if awaiting_final else _TOOLS
                chat = self.client.chat(
                    model.id,
                    messages,
                    tools=tools,
                    tool_choice="auto" if tools else None,
                    parallel_tool_calls=False if tools else None,
                    temperature=0.0,
                    max_tokens=self.cfg.get("max_tokens", 768),
                )
                total_elapsed += chat.elapsed_sec
                prompt_tokens += chat.prompt_tokens or 0
                completion_tokens += chat.completion_tokens or 0
                if not chat.ok:
                    res.metrics_before, res.metrics_during, res.metrics_after = (
                        scope.before,
                        scope.during,
                        scope.after,
                    )
                    res.success = False
                    res.error_type = chat.error_type
                    res.error_message = chat.error_message
                    res.extra = {"trial": trial_idx, "api_error": True, "events": events, "transcript": transcript}
                    self.emit(res)
                    return {"success": False, "steps": {}, "policies": {}, "state": {"ok": False}, "score": 0.0}

                content = chat.content or ""
                tool_calls = chat.tool_calls or []
                plan_seen = plan_seen or _mentions_plan(content)
                transcript.append(
                    {
                        "turn": turn,
                        "content": content[:1000],
                        "tool_calls": [
                            {"name": _call_name(call), "arguments": _call_args(call)}
                            for call in tool_calls
                        ],
                    }
                )
                messages.append(_assistant_message(content, tool_calls))

                if tool_calls and not awaiting_final:
                    wrote = False
                    for call in tool_calls:
                        tool_msg = _execute_tool(
                            call=call,
                            record_path=record_path,
                            title=self.title,
                            year=self.year,
                            events=events,
                        )
                        if _call_name(call) == "write_record":
                            wrote = True
                        messages.append(tool_msg)
                    if wrote:
                        awaiting_final = True
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "Now output only the final verification JSON object with keys "
                                    "title, year, and file_fixed. Do not call more tools."
                                ),
                            }
                        )
                    continue

                final_content = content
                break

        res.metrics_before, res.metrics_during, res.metrics_after = scope.before, scope.during, scope.after
        res.elapsed_sec = round(total_elapsed, 3)
        res.prompt_tokens = prompt_tokens or None
        res.completion_tokens = completion_tokens or None
        record_text = record_path.read_text(encoding="utf-8")
        steps, policies, state, parsed = _score_trial(
            plan_seen=plan_seen,
            events=events,
            final_content=final_content,
            record_text=record_text,
            title=self.title,
            year=self.year,
        )

        res.score = round(sum(1 for value in steps.values() if value) / len(steps), 3)
        res.success = all(steps.values())
        res.error_type = ErrorType.NONE if res.success else ErrorType.OTHER
        res.error_message = None if res.success else f"incomplete: {[k for k, v in steps.items() if not v]}"
        res.extra = {
            "steps": steps,
            "policies": policies,
            "state": state,
            "final_json": parsed,
            "plan_seen": plan_seen,
            "trial": trial_idx,
            "events": events,
            "transcript": transcript,
            "workspace": str(wdir).replace("\\", "/"),
        }
        res.notes = f"trial {trial_idx}: steps={steps} state_ok={state['ok']}"
        self.emit(res)
        self.log(f"  [agent t{trial_idx}] score={res.score} success={res.success} steps={steps}")
        return {"success": res.success, "steps": steps, "policies": policies, "state": state, "score": res.score}
