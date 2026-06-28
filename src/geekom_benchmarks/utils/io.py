"""Filesystem helpers, run-id generation, and the canonical results layout.

Everything in the framework writes through here so paths and naming stay
consistent. The repo root is discovered relative to this file, so the suite
works no matter what the current working directory is (Y:\\, a UNC path, etc.).
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List

# src/geekom_benchmarks/utils/io.py -> repo root is three parents up from the
# package dir (.../src/geekom_benchmarks -> .../src -> repo root).
REPO_ROOT = Path(__file__).resolve().parents[3]


def paths() -> Dict[str, Path]:
    """Return the canonical results/log/config directories, creating them."""
    p = {
        "root": REPO_ROOT,
        "config": REPO_ROOT / "config",
        "results": REPO_ROOT / "results",
        "raw": REPO_ROOT / "results" / "raw",
        "summary": REPO_ROOT / "results" / "summary",
        "reports": REPO_ROOT / "results" / "reports",
        "archive": REPO_ROOT / "results" / "archive",
        "logs": REPO_ROOT / "logs",
        "test_assets": REPO_ROOT / "test_assets",
    }
    for key in ("raw", "summary", "reports", "logs"):
        p[key].mkdir(parents=True, exist_ok=True)
    return p


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp, e.g. 2026-06-25T13:04:55Z."""
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def local_stamp() -> str:
    """Compact local timestamp for filenames, e.g. 20260625-230455."""
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def new_run_id(category: str) -> str:
    """A run id is `<category>_<localstamp>` — sortable and human-readable."""
    return f"{sanitize(category)}_{local_stamp()}"


def sanitize(name: str) -> str:
    """Make a model id / name safe for a filename."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("_")


def append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_json_atomic(path: Path, obj: Any, indent: int = 2) -> None:
    """Write JSON atomically (temp file + replace) so readers never see half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=indent)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def iter_jsonl_files(category: str | None = None) -> Iterator[Path]:
    """Yield every raw result JSONL file, optionally filtered by category dir."""
    raw = paths()["raw"]
    base = raw / category if category else raw
    if not base.exists():
        return
    yield from sorted(base.rglob("*.jsonl"))


def save_raw_response(category: str, run_id: str, label: str, payload: Any) -> str:
    """Persist a raw model response under results/raw/<category>/responses/.

    Returns a repo-relative path string suitable for the result schema's
    `raw_response_path` field.
    """
    p = paths()["raw"] / sanitize(category) / "responses"
    p.mkdir(parents=True, exist_ok=True)
    fname = f"{sanitize(run_id)}__{sanitize(label)}.json"
    fpath = p / fname
    write_json_atomic(fpath, payload)
    try:
        return str(fpath.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(fpath)
