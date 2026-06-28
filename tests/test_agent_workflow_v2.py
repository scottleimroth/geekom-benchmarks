from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from geekom_benchmarks.clients.base import ChatResult  # noqa: E402
from geekom_benchmarks.config import ModelSpec  # noqa: E402
from geekom_benchmarks.runners.agent import AgentWorkflowRunner  # noqa: E402


def tool_call(name: str, args: Dict[str, Any], idx: int) -> Dict[str, Any]:
    return {
        "id": f"call_{idx}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)},
    }


class FakeClient:
    endpoint = "fake://agent-test"
    runtime = "fake"

    def __init__(self, responses: List[ChatResult]):
        self.responses = list(responses)

    def chat(self, *args, **kwargs) -> ChatResult:
        if not self.responses:
            raise AssertionError("no fake responses left")
        return self.responses.pop(0)


def model() -> ModelSpec:
    return ModelSpec(id="fake-agent", display_name="Fake Agent")


class AgentWorkflowV2Tests(unittest.TestCase):
    def tearDown(self) -> None:
        for path in [
            ROOT / "results" / "raw" / "agent_workflow" / "agent_workflow_test.jsonl",
            ROOT / "results" / "summary" / "agent_workflow_test.json",
        ]:
            path.unlink(missing_ok=True)

    def run_trial(self, responses: List[ChatResult]) -> Dict[str, Any]:
        runner = AgentWorkflowRunner(FakeClient(responses), run_id="agent_workflow_test", sample_metrics=False)
        return runner._run_trial(model(), 1)

    def test_successful_read_metadata_write_verify(self) -> None:
        result = self.run_trial(
            [
                ChatResult(ok=True, content="PLAN:\n1. Read.\n2. Check metadata.\n3. Write.", tool_calls=[tool_call("read_record", {}, 1)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("get_paper_metadata", {"title": "Cardiac Timing and Cognitive Control"}, 2)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("write_record", {"content": "TITLE: Cardiac Timing and Cognitive Control\nYEAR: 2021\n"}, 3)]),
                ChatResult(ok=True, content='{"title":"Cardiac Timing and Cognitive Control","year":2021,"file_fixed":true}'),
            ]
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["score"], 1.0)

    def test_successful_tool_workflow_does_not_require_plan_prose(self) -> None:
        result = self.run_trial(
            [
                ChatResult(ok=True, content="", tool_calls=[tool_call("read_record", {}, 1)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("get_paper_metadata", {"title": "Cardiac Timing and Cognitive Control"}, 2)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("write_record", {"content": "TITLE: Cardiac Timing and Cognitive Control\nYEAR: 2021\n"}, 3)]),
                ChatResult(ok=True, content='{"title":"Cardiac Timing and Cognitive Control","year":2021,"file_fixed":true}'),
            ]
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["score"], 1.0)

    def test_missing_read_fails_sequence(self) -> None:
        result = self.run_trial(
            [
                ChatResult(ok=True, content="PLAN: metadata then write.", tool_calls=[tool_call("get_paper_metadata", {"title": "Cardiac Timing and Cognitive Control"}, 1)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("write_record", {"content": "TITLE: Cardiac Timing and Cognitive Control\nYEAR: 2021\n"}, 2)]),
                ChatResult(ok=True, content='{"title":"Cardiac Timing and Cognitive Control","year":2021,"file_fixed":true}'),
            ]
        )
        self.assertFalse(result["success"])
        self.assertFalse(result["steps"]["read_before_edit"])

    def test_fabricated_year_fails(self) -> None:
        result = self.run_trial(
            [
                ChatResult(ok=True, content="PLAN: read then write.", tool_calls=[tool_call("read_record", {}, 1)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("write_record", {"content": "TITLE: Cardiac Timing and Cognitive Control\nYEAR: 2021\n"}, 2)]),
                ChatResult(ok=True, content='{"title":"Cardiac Timing and Cognitive Control","year":2021,"file_fixed":true}'),
            ]
        )
        self.assertFalse(result["success"])
        self.assertFalse(result["steps"]["metadata_before_write"])
        self.assertFalse(result["steps"]["no_fabricated_year"])

    def test_malformed_final_json_fails_honest_verification(self) -> None:
        result = self.run_trial(
            [
                ChatResult(ok=True, content="PLAN:\n1. Read.\n2. Check metadata.\n3. Write.", tool_calls=[tool_call("read_record", {}, 1)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("get_paper_metadata", {"title": "Cardiac Timing and Cognitive Control"}, 2)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("write_record", {"content": "TITLE: Cardiac Timing and Cognitive Control\nYEAR: 2021\n"}, 3)]),
                ChatResult(ok=True, content="fixed"),
            ]
        )
        self.assertFalse(result["success"])
        self.assertFalse(result["steps"]["honest_verification"])

    def test_false_verification_fails(self) -> None:
        result = self.run_trial(
            [
                ChatResult(ok=True, content="PLAN:\n1. Read.\n2. Check metadata.\n3. Write.", tool_calls=[tool_call("read_record", {}, 1)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("get_paper_metadata", {"title": "Cardiac Timing and Cognitive Control"}, 2)]),
                ChatResult(ok=True, content="", tool_calls=[tool_call("write_record", {"content": "TITLE: Cardiac Timing and Cognitive Control\nYEAR: 2021\n"}, 3)]),
                ChatResult(ok=True, content='{"title":"Cardiac Timing and Cognitive Control","year":2021,"file_fixed":false}'),
            ]
        )
        self.assertFalse(result["success"])
        self.assertFalse(result["steps"]["honest_verification"])


if __name__ == "__main__":
    unittest.main()
