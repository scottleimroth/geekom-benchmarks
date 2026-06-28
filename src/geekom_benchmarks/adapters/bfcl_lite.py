"""BFCL-lite: a small, local function-calling taxonomy inspired by the Berkeley
Function Calling Leaderboard (BFCL).

This is NOT the BFCL dataset or its AST/executable scoring. It is a thin labeling
layer so our local tool-reliability benchmark reports results in BFCL-adjacent
terms, making the numbers easier to reason about next to BFCL categories.

Mapping from our tool-reliability exposure modes -> BFCL-lite labels:
    nopar     -> "serial"           (tools available, one call per turn)
    parallel  -> "parallel"         (parallel_tool_calls=True)
    strict    -> "staged"           (tools revealed one phase at a time)

Our task itself is a "multi_step_dependent" case: get_paper_metadata(title) then
save_note(text) where the note MUST carry the year returned by the first call —
i.e. a value must propagate across calls. BFCL's hardest local-equivalent is this
sequential/dependent pattern.

Outcome taxonomy (BFCL-style, mapped from our internal failure categories):
    correct                 - all calls + value propagation correct
    no_call                 - model never called the required function
    wrong_function          - called an unexpected / extra function
    wrong_parameter         - malformed or invalid arguments
    value_propagation_error - called both, but carried the WRONG value (year)
    api_error               - transport/server error
    other

TODO: add an optional importer that runs a subset of the real BFCL prompts through
the Lemonade endpoint and scores with BFCL's official checker (left out to avoid a
heavy dependency / dataset download).
"""
from __future__ import annotations

from typing import Dict

EXPOSURE_FROM_MODE: Dict[str, str] = {
    "nopar": "serial",
    "parallel": "parallel",
    "strict": "staged",
    # accept the BFCL-lite names as aliases too (idempotent)
    "serial": "serial",
    "staged": "staged",
    "multistep": "staged",
    "multi_step": "staged",
}

# Reverse aliases so callers can pass BFCL-lite names to the runner.
MODE_ALIASES: Dict[str, str] = {
    "serial": "nopar",
    "staged": "strict",
    "multistep": "strict",
    "multi_step": "strict",
    "multi-step": "strict",
}

TASK_CLASS = "multi_step_dependent"

# our internal failure category  ->  BFCL-lite outcome
OUTCOME_FROM_CATEGORY: Dict[str, str] = {
    "pass": "correct",
    "called tools but saved wrong year": "value_propagation_error",
    "got metadata but never saved note": "no_call",
    "didn't call the first tool": "no_call",
    "called wrong tool / wrong args": "wrong_function",
    "malformed tool-call JSON": "wrong_parameter",
    "api_error": "api_error",
    "other": "other",
}


def exposure_for_mode(mode: str) -> str:
    return EXPOSURE_FROM_MODE.get(mode, mode)


def resolve_mode(mode: str) -> str:
    """Map a BFCL-lite mode name back to the runner's internal mode name."""
    return MODE_ALIASES.get(mode, mode)


def classify_outcome(failure_category: str | None, passed: bool) -> str:
    if passed:
        return "correct"
    return OUTCOME_FROM_CATEGORY.get(failure_category or "other", "other")


def bfcl_label(mode: str, failure_category: str | None, passed: bool) -> Dict[str, str]:
    """The block stamped into each tool-reliability result's extra['bfcl']."""
    return {
        "exposure": exposure_for_mode(mode),
        "task_class": TASK_CLASS,
        "outcome": classify_outcome(failure_category, passed),
    }
