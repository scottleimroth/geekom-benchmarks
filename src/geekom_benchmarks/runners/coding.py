"""Coding benchmark: deterministic, local, offline tasks with executable tests.

Safety model:
  - all execution happens in a throwaway workspace OUTSIDE the tracked repo:
    <repo>/../geekom-benchmarks.tmp/coding_<run_id>/<task>/ ; cwd is pinned there.
  - auto-graded tasks are pure functions (no file IO), so running model code is
    low-risk. The "detect dangerous file logic" task is graded by STATIC analysis
    of the model's output — we never execute destructive code.
  - a static safety scan flags dangerous tokens; if a pure-function task's code
    contains them, we refuse to execute and mark error_type=unsafe_operation.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..config import ModelSpec
from ..schemas.result import Category, ErrorType
from ..utils.io import REPO_ROOT, sanitize
from .base import BaseRunner

_FENCE = re.compile(r"```(?:python|py)?\s*(.*?)```", re.DOTALL)
_DANGEROUS = [
    "rmtree", "shutil.rmtree", "os.system", "subprocess", "socket",
    "eval(", "exec(", "__import__", "os.remove", "os.unlink", "Path.unlink",
    "open(", "requests", "urllib",
]


def extract_code(text: str) -> str:
    if not text:
        return ""
    blocks = _FENCE.findall(text)
    if blocks:
        return "\n\n".join(b.strip() for b in blocks)
    lines = text.strip().splitlines()
    for idx, line in enumerate(lines):
        if re.match(r"\s*(from\s+\S+\s+import\s+|import\s+\S+|def\s+\w+\s*\()", line):
            return "\n".join(lines[idx:]).strip()
    return text.strip()


def safety_scan(code: str) -> List[str]:
    return [tok for tok in _DANGEROUS if tok in code]


@dataclass
class CodingTask:
    id: str
    kind: str
    prompt: str
    test_src: str            # a self-contained test that imports solution and asserts
    allow_file_ops: bool = False  # if False, dangerous tokens => unsafe
    static_grader: Optional[Callable[[str], Dict[str, Any]]] = None  # for non-executed tasks


def _grade_safe_delete(code: str) -> Dict[str, Any]:
    """Static grade: a safe delete helper must guard dirs and never rmtree."""
    has_rmtree = "rmtree" in code
    guards_dir = bool(re.search(r"is_dir\(|isdir\(|is_file\(|isfile\(", code))
    guards_exists = bool(re.search(r"exists\(|isfile\(|is_file\(", code))
    iterates_given = "for " in code  # operates on the passed iterable, not a glob of a whole folder
    globs_folder = bool(re.search(r"glob\(|iterdir\(|listdir\(", code))
    passed = (not has_rmtree) and guards_dir and (not globs_folder)
    return {
        "passed": passed,
        "checks": {
            "no_rmtree": not has_rmtree,
            "guards_directory": guards_dir,
            "guards_existence": guards_exists,
            "no_whole_folder_glob": not globs_folder,
            "iterates_given_paths": iterates_given,
        },
    }


TASKS: List[CodingTask] = [
    CodingTask(
        id="fix_bug",
        kind="fix_python_bug",
        prompt=(
            "This function should return the average of a list of numbers but crashes "
            "on an empty list and uses integer division. Fix it. Return ONLY a Python "
            "code block defining `def average(nums):` that returns a float, and returns "
            "0.0 for an empty list.\n\n"
            "```python\ndef average(nums):\n    return sum(nums) // len(nums)\n```"
        ),
        test_src=(
            "from solution import average\n"
            "assert average([2,4]) == 3.0, average([2,4])\n"
            "assert average([]) == 0.0\n"
            "assert abs(average([1,2,2]) - 1.6666666666) < 1e-6\n"
            "print('OK')\n"
        ),
    ),
    CodingTask(
        id="refactor_dedupe",
        kind="refactor_preserve_behavior",
        prompt=(
            "Write a Python function `dedupe_preserve_order(items)` that removes "
            "duplicates while preserving first-seen order and works for any hashable "
            "items. Return ONLY a python code block."
        ),
        test_src=(
            "from solution import dedupe_preserve_order as d\n"
            "assert d([3,1,3,2,1]) == [3,1,2]\n"
            "assert d([]) == []\n"
            "assert d(['a','a','b']) == ['a','b']\n"
            "print('OK')\n"
        ),
    ),
    CodingTask(
        id="windows_path_repair",
        kind="windows_path_length_repair",
        prompt=(
            "Write a Python function `safe_filename(name, max_len=255)` for Windows. It "
            "must: strip characters illegal in Windows filenames (<>:\"/\\|?*), collapse "
            "whitespace to single underscores, and truncate the BASE name so the total "
            "length (base + extension) is <= max_len while PRESERVING the file extension. "
            "Return ONLY a python code block."
        ),
        test_src=(
            "from solution import safe_filename as f\n"
            "r = f('a'*300 + '.pdf', max_len=50)\n"
            "assert len(r) <= 50, len(r)\n"
            "assert r.endswith('.pdf'), r\n"
            "assert '/' not in f('a/b:c.txt') and ':' not in f('a/b:c.txt')\n"
            "assert f('hello world.txt').count(' ') == 0\n"
            "print('OK')\n"
        ),
    ),
    CodingTask(
        id="detect_unsafe_delete",
        kind="detect_dangerous_file_logic",
        prompt=(
            "Write a Python function `delete_files(paths)` that deletes ONLY the regular "
            "files whose paths are passed in. It MUST NOT delete directories, MUST NOT "
            "recursively delete folder trees, MUST skip anything that is a directory, and "
            "MUST only act on the exact paths given (never glob or scan a whole folder). "
            "Return ONLY a python code block."
        ),
        test_src="",  # graded statically, not executed
        allow_file_ops=True,
        static_grader=_grade_safe_delete,
    ),
]

TASKS_BY_ID = {t.id: t for t in TASKS}


class CodingRunner(BaseRunner):
    category = Category.CODING

    def __init__(self, client, **kw):
        super().__init__(client, **kw)
        self.workspace = (REPO_ROOT.parent / "geekom-benchmarks.tmp" / f"coding_{self.run_id}")

    def _run_test(self, taskdir: Path) -> Dict[str, Any]:
        try:
            proc = subprocess.run(
                [sys.executable, "test_solution.py"],
                cwd=str(taskdir), capture_output=True, text=True, timeout=30,
            )
            return {"passed": proc.returncode == 0 and "OK" in proc.stdout,
                    "returncode": proc.returncode,
                    "stdout": proc.stdout[-800:], "stderr": proc.stderr[-800:]}
        except subprocess.TimeoutExpired:
            return {"passed": False, "returncode": None, "stdout": "", "stderr": "timeout"}
        except Exception as e:
            return {"passed": False, "returncode": None, "stdout": "", "stderr": str(e)[:400]}

    def run_task(self, model: ModelSpec, task: CodingTask) -> Dict[str, Any]:
        res = self.new_result(model, benchmark_name=f"coding:{task.kind}",
                              task_id=task.id, prompt_id=task.id)
        with self.metrics_scope(full=False) as scope:
            chat = self.client.chat(model.id, [{"role": "user", "content": task.prompt}],
                                    max_tokens=1024, temperature=0.0)
        res.metrics_before, res.metrics_after = scope.before, scope.after
        res.elapsed_sec = round(chat.elapsed_sec, 3)
        res.prompt_tokens, res.completion_tokens = chat.prompt_tokens, chat.completion_tokens
        res.total_tokens, res.tokens_estimated = chat.total_tokens, chat.tokens_estimated
        if not chat.ok:
            res.success = False
            res.error_type = chat.error_type
            res.error_message = chat.error_message
            self.emit(res)
            return res.to_dict()

        code = extract_code(chat.content)
        flagged = safety_scan(code)
        res.extra = {"safety_flags": flagged}

        # ---- statically-graded task (no execution) ----
        if task.static_grader is not None:
            g = task.static_grader(code)
            res.success = bool(g["passed"])
            res.score = 1.0 if g["passed"] else 0.0
            res.error_type = ErrorType.NONE if g["passed"] else ErrorType.UNSAFE_OPERATION
            res.error_message = None if g["passed"] else "unsafe/insufficient guards"
            res.extra.update({"static_grade": g, "code_excerpt": code[:1200]})
            res.notes = "graded by static analysis (not executed)"
            self.emit(res)
            self.log(f"  [{task.id}] static {'PASS' if g['passed'] else 'FAIL'} {g['checks']}")
            return res.to_dict()

        # ---- executed pure-function task ----
        if not task.allow_file_ops and flagged:
            res.success = False
            res.error_type = ErrorType.UNSAFE_OPERATION
            res.error_message = f"refused to execute; dangerous tokens: {flagged}"
            res.extra.update({"code_excerpt": code[:1200]})
            self.emit(res)
            self.log(f"  [{task.id}] UNSAFE, not executed: {flagged}")
            return res.to_dict()

        taskdir = self.workspace / task.id
        taskdir.mkdir(parents=True, exist_ok=True)
        (taskdir / "solution.py").write_text(code, encoding="utf-8")
        (taskdir / "test_solution.py").write_text(task.test_src, encoding="utf-8")
        test = self._run_test(taskdir)
        res.success = bool(test["passed"])
        res.score = 1.0 if test["passed"] else 0.0
        res.error_type = ErrorType.NONE if test["passed"] else ErrorType.TEST_FAILED
        res.error_message = None if test["passed"] else (test.get("stderr") or "test failed")[:300]
        res.extra.update({"test": test, "workspace": str(taskdir).replace("\\", "/"),
                          "code_excerpt": code[:1200]})
        self.emit(res)
        self.log(f"  [{task.id}] {'PASS' if test['passed'] else 'FAIL'} rc={test['returncode']}")
        return res.to_dict()

    def run_model(self, model: ModelSpec, task_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        tasks = [TASKS_BY_ID[t] for t in task_ids] if task_ids else TASKS
        return [self.run_task(model, t) for t in tasks]
