"""tau-lite: tau-bench-inspired helpers for the agent-workflow benchmark.

tau-bench (Sierra) evaluates agents over REPEATED trials against a stateful
environment, checking (a) the final database/world state, (b) compliance with
domain policies/rules, and (c) reliability across retries via pass^k. This module
provides the small, local equivalents our agent runner uses. It is NOT tau-bench
itself (no airline/retail domains, no user simulator).

Provides:
  - pass_hat_k(n, c, k)      : unbiased pass^k estimator (HumanEval-style)
  - reliability(passes, n)   : simple pass rate over retries
  - AGENT_POLICIES           : the rule set the agent must comply with
  - check_policies(...)      : evaluate those rules for one trial
  - check_state(...)         : final file/"database" state check

This is still NOT official tau-bench. The local runner now provides a tiny
stateful tool environment, but it has no airline/retail domains or user
simulator.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def pass_hat_k(n: int, c: int, k: int) -> Optional[float]:
    """Unbiased estimate that at least one of k samples passes, given c/n passed.

    pass^k = 1 - C(n-c, k) / C(n, k).  Returns None if k > n.
    """
    if k > n or n <= 0:
        return None
    if c <= 0:
        return 0.0
    if n - c < k:
        return 1.0
    return round(1.0 - (math.comb(n - c, k) / math.comb(n, k)), 4)


def reliability(passes: int, n: int) -> Optional[float]:
    return round(passes / n, 4) if n else None


# Domain policies the agent must obey (local stand-in for tau-bench's rule docs).
AGENT_POLICIES: List[Dict[str, str]] = [
    {"id": "read_before_edit", "desc": "Must read the record before editing it."},
    {"id": "metadata_before_write", "desc": "Must call the metadata tool before writing the corrected file."},
    {"id": "no_fabricated_year", "desc": "The written year must come from the metadata tool, not be invented."},
    {"id": "preserve_title", "desc": "Must not alter the TITLE line of the record."},
    {"id": "honest_verification", "desc": "The final JSON's file_fixed flag must match the real outcome."},
]


def check_policies(*, steps: Dict[str, bool], title_preserved: bool, honest: bool) -> Dict[str, bool]:
    """Return {policy_id: complied}. `steps` is the agent runner's step dict."""
    return {
        "read_before_edit": bool(steps.get("read_before_edit")),
        "metadata_before_write": bool(steps.get("metadata_before_write")),
        "no_fabricated_year": bool(steps.get("no_fabricated_year")),
        "preserve_title": bool(title_preserved),
        "honest_verification": bool(honest),
    }


def check_state(file_text: Optional[str], *, expected_year: int, title: str, stale_year: str = "1999") -> Dict[str, Any]:
    """Final-state ('database') check on the edited record file."""
    if not file_text:
        return {"ok": False, "reason": "no edited file produced"}
    ok = (str(expected_year) in file_text) and (title in file_text) and (stale_year not in file_text)
    return {
        "ok": ok,
        "has_expected_year": str(expected_year) in file_text,
        "title_present": title in file_text,
        "stale_year_removed": stale_year not in file_text,
    }


def aggregate(trials: List[Dict[str, Any]], ks: Optional[List[int]] = None) -> Dict[str, Any]:
    """Aggregate per-trial pass booleans into reliability + pass^k for each k."""
    n = len(trials)
    c = sum(1 for t in trials if t.get("success"))
    ks = ks or sorted({1, min(2, n), min(5, n), n})
    return {
        "trials": n,
        "passes": c,
        "reliability": reliability(c, n),
        "pass_hat_k": {f"k={k}": pass_hat_k(n, c, k) for k in ks if k >= 1},
    }
