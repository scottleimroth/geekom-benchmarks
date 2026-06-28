#!/usr/bin/env python3
"""Phase 2 environment check. Verifies machine, repo, Python, packages, Lemonade,
endpoint, models, GPU/NPU visibility, and metric collectability. Writes
results/summary/environment_latest.json (+ timestamped). PASS/WARN/FAIL summary.

Usage:  python scripts/check_environment.py
"""
import _bootstrap  # noqa: F401
import argparse
import importlib
import os
import platform
import socket
import sys

from geekom_benchmarks.config import DEFAULT_ENDPOINT, load_hardware, load_models
from geekom_benchmarks.clients import LemonadeClient
from geekom_benchmarks.metrics.windows import sample
from geekom_benchmarks.utils.io import REPO_ROOT, local_stamp, paths, write_json_atomic

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = ap.parse_args()

    checks = []

    def add(name, status, message, detail=None):
        checks.append({"name": name, "status": status, "message": message, "detail": detail})

    hw = (load_hardware().get("profiles", {}) or {}).get("geekom_a9_max", {})

    # 1. hostname
    host = socket.gethostname()
    exp = os.environ.get("GEEKOM_BENCHMARK_HOSTNAME") or hw.get("expected_hostname") or ""
    if exp:
        add("hostname", PASS if host.upper() == exp.upper() else WARN,
            "hostname matches configured target" if host.upper() == exp.upper() else "hostname differs from configured target",
            "configured")
    else:
        add("hostname", WARN, "hostname check disabled; set GEEKOM_BENCHMARK_HOSTNAME locally", "not-recorded")

    # 2. repo path
    rp = str(REPO_ROOT)
    add("repo_path", PASS if "geekom-benchmarks" in rp.replace("\\", "/") else WARN,
        "repo root basename check passed" if "geekom-benchmarks" in rp.replace("\\", "/") else "repo root basename unexpected",
        "repo-local")

    # 3. writable
    try:
        t = paths()["logs"] / ".env_write_test"
        t.write_text("ok", encoding="utf-8")
        t.unlink()
        add("repo_writable", PASS, "repo is writable")
    except Exception as e:
        add("repo_writable", FAIL, f"repo not writable: {e}")

    # 4. python
    pv = platform.python_version()
    ok_py = sys.version_info[:2] >= (3, 9)
    add("python", PASS if ok_py else FAIL, f"Python {pv}", pv)

    # 5. packages
    missing = []
    for mod in ("yaml", "requests", "psutil"):
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(mod)
    add("packages", PASS if not missing else FAIL,
        "all required packages present" if not missing else f"missing: {missing}", missing)

    # 6/7/8. Lemonade reachable + endpoint + models
    client = LemonadeClient(args.endpoint)
    live_ids = []
    try:
        data = client.list_models()
        live_ids = [m.get("id") for m in data]
        add("lemonade_reachable", PASS, f"reachable at {args.endpoint}")
        add("endpoint_openai_compatible", PASS, f"/models returned {len(live_ids)} models")
        add("models", PASS, f"{len(live_ids)} models loaded", live_ids)
    except Exception as e:
        add("lemonade_reachable", FAIL, f"NOT reachable at {args.endpoint}: {e}")
        add("endpoint_openai_compatible", FAIL, "could not query /models")
        add("models", FAIL, "no model list", [])

    # cross-check catalog vs live
    if live_ids:
        catalog = [m for m in load_models() if m.enabled]
        miss = [m.id for m in catalog if m.id not in live_ids]
        add("catalog_vs_live", PASS if not miss else WARN,
            "all enabled catalog models present" if not miss else f"enabled but not loaded: {miss}", miss)

    # 9/10/11. GPU / NPU / metrics
    metrics = sample(full=True)
    gpu = metrics.get("gpu_util", {})
    add("gpu_visible", PASS if gpu.get("quality") == "measured" else WARN,
        f"GPU util quality={gpu.get('quality')} ({gpu.get('reason') or 'ok'})", gpu)
    npu = metrics.get("npu_util", {})
    add("npu_visible", WARN if npu.get("quality") in ("measured", "unreliable") else PASS,
        f"NPU util quality={npu.get('quality')} ({npu.get('reason') or 'ok'})", npu)
    ram = metrics.get("ram_total", {})
    add("metrics_collectable", PASS if ram.get("quality") == "measured" else WARN,
        f"RAM/CPU metrics quality={ram.get('quality')}", {k: v.get("quality") for k, v in metrics.items()})

    # summary
    n_fail = sum(1 for c in checks if c["status"] == FAIL)
    n_warn = sum(1 for c in checks if c["status"] == WARN)
    overall = FAIL if n_fail else (WARN if n_warn else PASS)

    env = {
        "timestamp": local_stamp(),
        "overall": overall,
        "hostname": os.environ.get("GEEKOM_BENCH_PUBLIC_HOST_LABEL", "local-geekom"),
        "os": f"{platform.system()} {platform.release()}",
        "repo_path": "repo-local",
        "endpoint": args.endpoint,
        "python": pv,
        "checks": checks,
        "metrics_sample": metrics,
        "counts": {"pass": len(checks) - n_warn - n_fail, "warn": n_warn, "fail": n_fail},
    }
    sp = paths()["summary"]
    write_json_atomic(sp / "environment_latest.json", env)
    write_json_atomic(sp / f"environment_{env['timestamp']}.json", env)

    print(f"\n=== Environment check: {overall} ===")
    for c in checks:
        print(f"  [{c['status']:4}] {c['name']:26} {c['message']}")
    print(f"\nSaved: {sp / 'environment_latest.json'}")
    return 0 if overall != FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
