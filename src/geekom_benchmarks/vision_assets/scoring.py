"""Scoring for vision answers against manifest ground truth.

Scoring methods (declared per manifest item):
  substring     - normalized expected_answer is a substring of the model output,
                  OR any accepted_answer_pattern (regex) matches. (default)
  regex_any     - pass if ANY accepted_answer_pattern matches (re.search, IGNORECASE)
  regex_all     - pass if ALL accepted_answer_patterns match
  contains_all  - pass if every accepted_answer_pattern is present as a
                  case-insensitive substring (good for "list the buttons")
  numeric       - the integer/decimal in expected_answer appears in the output

Returns (passed, detail) where detail explains which check fired.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def score_answer(output: str, item: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    method = item.get("scoring_method", "substring")
    expected = item.get("expected_answer", "")
    patterns = item.get("accepted_answer_patterns", []) or []
    out = output or ""
    out_n = _norm(out)

    def any_pattern() -> bool:
        return any(re.search(p, out, re.IGNORECASE) for p in patterns)

    def all_patterns() -> bool:
        return bool(patterns) and all(re.search(p, out, re.IGNORECASE) for p in patterns)

    if method == "regex_any":
        passed = any_pattern()
        return passed, {"method": method, "matched_pattern": passed}
    if method == "regex_all":
        passed = all_patterns()
        return passed, {"method": method, "all_patterns": passed}
    if method == "contains_all":
        missing = [p for p in patterns if _norm(p) not in out_n]
        return (not missing and bool(patterns)), {"method": method, "missing": missing}
    if method == "numeric":
        m = re.search(r"-?\d[\d,]*\.?\d*", expected)
        target = m.group(0).replace(",", "") if m else expected
        passed = bool(target) and re.search(rf"(?<!\d){re.escape(target)}(?!\d)", out.replace(",", "")) is not None
        return passed, {"method": method, "target": target}
    # default: substring OR any pattern
    passed = (_norm(expected) in out_n) or any_pattern()
    return passed, {"method": "substring", "expected_in_output": _norm(expected) in out_n,
                    "matched_pattern": any_pattern()}
