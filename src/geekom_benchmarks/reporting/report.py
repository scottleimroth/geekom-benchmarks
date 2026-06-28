"""ONE report generator. Reads canonical raw JSONL -> summaries -> standalone HTML.

It also folds in the legacy pre-framework results (results/benchmarks.json and
results/tool-calling/summary.json) as historical context so nothing is lost.
The HTML opens locally with no server and no JS framework.
"""
from __future__ import annotations

import csv
import html
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import load_hardware, load_models
from ..utils.io import iter_jsonl_files, local_stamp, paths, read_jsonl, write_json_atomic

EXTERNAL_SCORE_CATEGORIES = (
    "llama_bench",
    "lm_eval",
    "evalscope",
    "mlperf_client",
    "opencompass",
    "vllm",
    "bfcl",
    "tau_bench",
    "swe_bench",
    "ragas",
    "deepeval",
)

# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_all_raw(category: Optional[str] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for f in iter_jsonl_files(category):
        out.extend(read_jsonl(f))
    return out


def _load_env() -> Dict[str, Any]:
    p = paths()["summary"] / "environment_latest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _load_legacy() -> Dict[str, Any]:
    res = paths()["results"]
    legacy: Dict[str, Any] = {}
    bp = res / "benchmarks.json"
    if bp.exists():
        try:
            legacy["speed"] = json.loads(bp.read_text(encoding="utf-8"))
        except Exception:
            pass
    tp = res / "tool-calling" / "summary.json"
    if tp.exists():
        try:
            legacy["tool"] = json.loads(tp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return legacy


# --------------------------------------------------------------------------- #
# Summarization
# --------------------------------------------------------------------------- #
def _mean(xs: List[float]) -> Optional[float]:
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 2) if xs else None


def build_summary(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_cat[r.get("benchmark_category", "unknown")].append(r)

    summary: Dict[str, Any] = {"generated": local_stamp(), "categories": {}}

    # ---- speed ----
    speed = by_cat.get("speed", [])
    sp_by_model: Dict[str, Dict[str, Any]] = {}
    for r in speed:
        if not r.get("success"):
            continue
        m = r["model_display_name"]
        d = sp_by_model.setdefault(m, {"model": m, "tps": [], "ftl": [], "pp": [], "tg": [],
                                       "backend": None, "quant": None, "by_prompt": {}})
        if r.get("output_tokens_per_sec"):
            d["tps"].append(r["output_tokens_per_sec"])
        if r.get("first_token_latency_sec"):
            d["ftl"].append(r["first_token_latency_sec"])
        if r.get("pp_tokens_per_sec"):
            d["pp"].append(r["pp_tokens_per_sec"])
        if r.get("tg_tokens_per_sec"):
            d["tg"].append(r["tg_tokens_per_sec"])
        d["backend"] = d["backend"] or r.get("backend")
        d["quant"] = d["quant"] or r.get("quant")
        d["by_prompt"][r.get("prompt_id")] = r.get("output_tokens_per_sec")
    speed_rank = sorted(
        ({"model": m, "mean_tps": _mean(d["tps"]), "mean_ftl_sec": _mean(d["ftl"]),
          "mean_pp_tps": _mean(d["pp"]), "mean_tg_tps": _mean(d["tg"]),
          "backend": d["backend"], "quant": d["quant"], "by_prompt": d["by_prompt"]}
         for m, d in sp_by_model.items()),
        key=lambda x: (x["mean_tps"] is not None, x["mean_tps"] or 0), reverse=True,
    )
    summary["categories"]["speed"] = speed_rank

    # ---- tool reliability (model x mode) ----
    tool = by_cat.get("tool_reliability", [])
    tmap: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"pass": 0, "total": 0}))
    fails: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for r in tool:
        mode = (r.get("extra") or {}).get("mode", "?")
        m = r["model_display_name"]
        tmap[m][mode]["total"] += 1
        if r.get("success"):
            tmap[m][mode]["pass"] += 1
        else:
            cat = (r.get("extra") or {}).get("failure_category") or r.get("error_type") or "other"
            fails[m][mode][cat] += 1
    tool_rank = []
    for m, modes in tmap.items():
        row = {"model": m, "modes": {}, "fails": {k: dict(v) for k, v in fails[m].items()}}
        total_pass = total = 0
        for mode, sc in modes.items():
            row["modes"][mode] = f"{sc['pass']}/{sc['total']}"
            total_pass += sc["pass"]
            total += sc["total"]
        row["overall_pass_rate"] = round(total_pass / total, 3) if total else None
        tool_rank.append(row)
    tool_rank.sort(key=lambda x: x["overall_pass_rate"] or 0, reverse=True)
    summary["categories"]["tool_reliability"] = tool_rank

    # ---- generic score-based categories ----
    score_categories = (
        "structured_output",
        "coding",
        "vision",
        "long_context",
        "agent_workflow",
        *EXTERNAL_SCORE_CATEGORIES,
    )
    for cat in score_categories:
        recs = by_cat.get(cat, [])
        agg: Dict[str, Dict[str, Any]] = {}
        for r in recs:
            m = r["model_display_name"]
            d = agg.setdefault(m, {"model": m, "scores": [], "n": 0, "passed": 0, "skipped": 0})
            d["n"] += 1
            if r.get("error_type") == "skipped":
                d["skipped"] += 1
                continue
            task_id = str(r.get("task_id") or "")
            bench_name = str(r.get("benchmark_name") or "")
            extra_metric = str((r.get("extra") or {}).get("metric") or (r.get("extra") or {}).get("metric_key") or "")
            metric_text = f"{task_id} {bench_name} {extra_metric}".lower()
            perf_tokens = (
                "perf",
                "latency",
                "throughput",
                "token",
                "tok/s",
                "tps",
                "ttft",
                "time to first",
                "duration",
                "req_ps",
                "generated tokens",
                "input tokens",
            )
            is_perf_metric = task_id.startswith("perf:") or ":perf:" in bench_name or any(
                token in metric_text for token in perf_tokens
            )
            if r.get("score") is not None and not is_perf_metric:
                d["scores"].append(r["score"])
            if r.get("success"):
                d["passed"] += 1
        rank = sorted(
            ({"model": m, "mean_score": _mean(d["scores"]), "passed": d["passed"],
              "n": d["n"], "skipped": d["skipped"]} for m, d in agg.items()),
            key=lambda x: x["mean_score"] or -1, reverse=True,
        )
        summary["categories"][cat] = rank

    # ---- counts ----
    summary["counts"] = {c: len(rs) for c, rs in by_cat.items()}
    summary["runs"] = sorted({r.get("run_id") for r in records if r.get("run_id")})
    return summary


def _recommendations(summary: Dict[str, Any]) -> Dict[str, str]:
    cats = summary["categories"]
    def top(catname, key="model"):
        rows = cats.get(catname) or []
        return rows[0][key] if rows else "—"
    speed_top = top("speed")
    tool_top = top("tool_reliability")
    coding_top = top("coding")
    vision_rows = [r for r in (cats.get("vision") or []) if (r.get("mean_score") is not None)]
    return {
        "daily_chat": speed_top,
        "coding": coding_top if (cats.get("coding")) else "Qwen3-Coder-30B-A3B (untested this run)",
        "tool_agent": tool_top if cats.get("tool_reliability") else "Nemotron-Cascade-2-30B-A3B",
        "reasoning": "Nemotron-Cascade-2-30B-A3B / Qwen3.6-35B-A3B",
        "vision": (vision_rows[0]["model"] if vision_rows else "Qwen3-VL-8B (untested this run)"),
        "fast_small": "gemma-4-E2B-it / gemma-4-E4B-it",
    }


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def write_summaries(summary: Dict[str, Any]) -> Dict[str, Path]:
    sp = paths()["summary"]
    stamp = summary.get("generated", local_stamp())
    out = {}
    out["json_latest"] = sp / "latest_summary.json"
    out["json_stamped"] = sp / f"summary_{stamp}.json"
    write_json_atomic(out["json_latest"], summary)
    write_json_atomic(out["json_stamped"], summary)

    # flat CSV of speed + tool for spreadsheet use
    csv_path = sp / "latest_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["category", "model", "metric", "value"])
        for row in summary["categories"].get("speed", []):
            w.writerow(["speed", row["model"], "mean_tps", row.get("mean_tps")])
            w.writerow(["speed", row["model"], "mean_ftl_sec", row.get("mean_ftl_sec")])
        for row in summary["categories"].get("tool_reliability", []):
            for mode, sc in row.get("modes", {}).items():
                w.writerow(["tool_reliability", row["model"], mode, sc])
        for cat in ("structured_output", "coding", "vision", "long_context", "agent_workflow",
                    *EXTERNAL_SCORE_CATEGORIES):
            for row in summary["categories"].get(cat, []):
                w.writerow([cat, row["model"], "mean_score", row.get("mean_score")])
    out["csv_latest"] = csv_path
    return out


def _h(s: Any) -> str:
    return html.escape(str(s)) if s is not None else "—"


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    th = "".join(f"<th>{_h(h)}</th>" for h in headers)
    trs = ""
    for r in rows:
        tds = "".join(f"<td>{_h(c)}</td>" for c in r)
        trs += f"<tr>{tds}</tr>"
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def render_html(summary: Dict[str, Any], env: Dict[str, Any], legacy: Dict[str, Any]) -> str:
    hw = (load_hardware().get("profiles", {}) or {}).get("geekom_a9_max", {})
    models = load_models()
    cats = summary["categories"]
    recs = _recommendations(summary)

    enabled = [m for m in models if m.enabled]
    disabled = [m for m in models if not m.enabled]

    # available vs catalog: env may carry the live model list
    live_ids = set()
    for e in (env.get("checks") or []):
        if e.get("name") == "models" and isinstance(e.get("detail"), list):
            live_ids = set(e["detail"])
    missing = [m for m in enabled if live_ids and m.id not in live_ids]

    speed_rows = [[i + 1, r["model"], r.get("mean_tps"), r.get("mean_ftl_sec"),
                   r.get("mean_pp_tps"), r.get("mean_tg_tps"), r.get("backend"), r.get("quant")]
                  for i, r in enumerate(cats.get("speed", []))]
    tool_rows = []
    for i, r in enumerate(cats.get("tool_reliability", [])):
        modes = r.get("modes", {})
        tool_rows.append([i + 1, r["model"], modes.get("parallel", "—"),
                          modes.get("nopar", "—"), modes.get("strict", "—"),
                          r.get("overall_pass_rate")])

    def score_table(catname):
        return [[i + 1, r["model"], r.get("mean_score"), f"{r.get('passed')}/{r.get('n')}",
                 r.get("skipped")] for i, r in enumerate(cats.get(catname, []))]

    env_rows = [[e.get("name"), e.get("status"), e.get("message")]
                for e in (env.get("checks") or [])]

    model_rows = [[m.display_name, m.id, m.arch, m.param_size, ",".join(m.uses)]
                  for m in enabled]
    missing_rows = [[m.display_name, m.id, m.pull_command or f"lemonade-server pull {m.id}"]
                    for m in missing]

    css = """
    body{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#0f1216;color:#e6e6e6}
    .wrap{max-width:1100px;margin:0 auto;padding:24px}
    h1{font-size:24px;margin:0 0 4px} h2{margin-top:34px;border-bottom:1px solid #2a2f37;padding-bottom:6px}
    .sub{color:#9aa4b2;font-size:13px}
    table{border-collapse:collapse;width:100%;margin:10px 0;font-size:14px}
    th,td{border:1px solid #2a2f37;padding:6px 10px;text-align:left}
    th{background:#1a1f27} tr:nth-child(even) td{background:#151a21}
    .card{background:#161b22;border:1px solid #2a2f37;border-radius:8px;padding:14px 18px;margin:10px 0}
    .rec{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
    .rec .item{background:#161b22;border:1px solid #2a2f37;border-radius:8px;padding:10px 14px}
    .rec .k{color:#9aa4b2;font-size:12px;text-transform:uppercase}
    .rec .v{font-size:15px;font-weight:600;margin-top:3px}
    .warn{background:#2a1f12;border-color:#5a3} .warn li{margin:4px 0}
    code{background:#0b0e12;padding:1px 5px;border-radius:4px}
    .ok{color:#5dd39e} .fail{color:#ff6b6b} .warnflag{color:#ffd166}
    """

    def warn_class(status):
        s = str(status).upper()
        return "ok" if s == "PASS" else ("warnflag" if s == "WARN" else "fail")

    env_html = "".join(
        f"<tr><td>{_h(e.get('name'))}</td><td class='{warn_class(e.get('status'))}'>{_h(e.get('status'))}</td><td>{_h(e.get('message'))}</td></tr>"
        for e in (env.get("checks") or [])
    )

    rec_html = "".join(
        f"<div class='item'><div class='k'>{_h(k)}</div><div class='v'>{_h(v)}</div></div>"
        for k, v in recs.items()
    )

    legacy_speed = legacy.get("speed", [])
    legacy_rows = [[r.get("displayName"), r.get("quant"), r.get("tokSOut"), r.get("completionTokens")]
                   for r in legacy_speed]

    parts = [f"""<!doctype html><html><head><meta charset="utf-8">
<title>GEEKOM A9 Max — Local AI Benchmark Report</title><style>{css}</style></head>
<body><div class="wrap">
<h1>GEEKOM A9 Max — Local AI Benchmark Report</h1>
<div class="sub">Generated {_h(summary.get('generated'))} · runtime {_h(hw.get('runtime'))} · {_h(hw.get('endpoint'))}</div>
<div class="sub">A <b>personal umbrella harness</b> for local-AI on this hardware — it runs its own probes and aligns with public benchmark <i>styles</i> (llama-bench, BFCL, tau-bench, lm-eval). It is <b>not</b> a canonical public benchmark. See <code>docs/benchmark_ecosystem.md</code>.</div>

<h2>1. Hardware</h2>
<div class="card">
<b>{_h(hw.get('label'))}</b><br>
CPU: {_h(hw.get('cpu'))}<br>iGPU: {_h(hw.get('igpu'))}<br>NPU: {_h(hw.get('npu'))}<br>
Memory: {_h(hw.get('memory_gb'))} GB {_h(hw.get('memory_type'))}<br>
<span class="sub">{_h(hw.get('memory_note'))}</span>
</div>

<h2>2. Environment check</h2>
<table><thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead><tbody>{env_html or '<tr><td colspan=3>no environment_latest.json — run scripts/check_environment.py</td></tr>'}</tbody></table>

<h2>3. Available models (catalog, enabled)</h2>
{_table(['Display','Lemonade id','arch','params(B)','uses'], model_rows)}

<h2>4. Missing models & pull commands</h2>
{_table(['Display','id','suggested pull'], missing_rows) if missing_rows else "<div class='card'>All enabled catalog models were present in the live Lemonade model list (or the live list was unavailable).</div>"}

<h2>5. Speed ranking (output tok/s, warm-up excluded)</h2>
{_table(['#','Model','mean tok/s','mean ttft (s)','pp t/s*','tg t/s*','backend','quant'], speed_rows) if speed_rows else "<div class='card'>No speed results in raw/. Run scripts/run_benchmarks.py.</div>"}
<div class="sub">* llama-bench-compatible: pp t/s = prompt-processing (prefill, derived from ttft); tg t/s = token-generation (decode). gpu_layers/batch/ubatch/flash_attn/model_hash are not exposed by Lemonade and are recorded null. See <code>docs/benchmark_ecosystem.md</code>.</div>

<h2>6. Tool-calling reliability — BFCL-lite (passes / trials)</h2>
<div class="sub">Exposure modes: <b>parallel</b>, <b>nopar</b>=serial, <b>strict</b>=staged. Task class: multi_step_dependent (metadata→note value propagation). Outcomes use a BFCL-style taxonomy — see <code>docs/benchmark_ecosystem.md</code>.</div>
{_table(['#','Model','parallel','nopar (serial)','strict (staged)','overall'], tool_rows) if tool_rows else "<div class='card'>No tool results in raw/. Run scripts/run_tool_reliability.py.</div>"}

<h2>7. Structured output</h2>
{_table(['#','Model','mean score','passed','skipped'], score_table('structured_output')) if cats.get('structured_output') else "<div class='card'>Not run.</div>"}

<h2>8. Coding</h2>
{_table(['#','Model','mean score','passed','skipped'], score_table('coding')) if cats.get('coding') else "<div class='card'>Not run.</div>"}

<h2>9. Vision</h2>
{_table(['#','Model','mean score','passed','skipped'], score_table('vision')) if cats.get('vision') else "<div class='card'>Not run / skipped.</div>"}

<h2>10. Long context</h2>
{_table(['#','Model','mean score','passed','skipped'], score_table('long_context')) if cats.get('long_context') else "<div class='card'>Not run.</div>"}

<h2>11. Agent workflow</h2>
{_table(['#','Model','mean score','passed','skipped'], score_table('agent_workflow')) if cats.get('agent_workflow') else "<div class='card'>Not run.</div>"}

<h2>12. External suite imports</h2>
{_table(['#','Category','Model','mean score','passed','skipped'],
        [[
            i + 1,
            cat.replace("_", " "),
            r["model"],
            r.get("mean_score"),
            f"{r.get('passed')}/{r.get('n')}",
            r.get("skipped"),
        ] for cat in EXTERNAL_SCORE_CATEGORIES
          for i, r in enumerate(cats.get(cat, []))]) if any(cats.get(cat) for cat in EXTERNAL_SCORE_CATEGORIES) else "<div class='card'>No imported external suite results.</div>"}

<h2>13. Recommendations</h2>
<div class="rec">{rec_html}</div>

<h2>14. Known warnings</h2>
<ul class="card warn">
<li>Dense large models (e.g. Qwen3.5-27B ~4 tok/s) are <b>much slower</b> on this hardware than MoE models.</li>
<li>MoE models (Qwen3-30B-A3B, Nemotron-Cascade, Qwen3.6-35B) are the practical choice on the iGPU.</li>
<li><b>Qwen3-30B-A3B may require strict staged tool orchestration</b> — it degrades with both tools exposed at once (saves the wrong year).</li>
<li><b>Nemotron-Cascade-2-30B-A3B appears strongest for tool reliability</b> (passes loose and staged modes).</li>
<li><b>Do not expose the Lemonade API publicly</b> — it is an unauthenticated localhost endpoint.</li>
</ul>

<h2>15. Methodology notes</h2>
<ul class="card">
<li>Warm-up calls are excluded from all averages.</li>
<li>Token counts are API-reported where available; otherwise estimated and flagged <code>tokens_estimated=true</code>.</li>
<li>System metrics are recorded with quality flags; unavailable metrics are <code>null</code>, never fabricated (NPU/power are typically <code>unsupported</code> for Vulkan iGPU runs).</li>
<li>A 200-token warm probe is <b>not</b> directly comparable to a 512-token run unless explicitly labelled.</li>
<li>Strict staged tool-calling is a <b>first-class orchestration mode</b>, not a workaround.</li>
<li>This is an <b>umbrella harness</b>, not a canonical public benchmark. BFCL-lite/tau-lite are local, BFCL/tau-bench-<i>inspired</i> labels — not the official datasets/scorers. llama-bench fields are derived where the runtime exposes them, null otherwise.</li>
</ul>

<h2>16. Legacy results (pre-framework, preserved)</h2>
<div class="sub">From results/benchmarks.json — mixed methodology, kept for history.</div>
{_table(['Model','Quant','tok/s','completion tokens'], legacy_rows) if legacy_rows else "<div class='card'>none</div>"}

<div class="sub" style="margin-top:30px">Raw per-task records: results/raw/&lt;category&gt;/*.jsonl · Schema v{_h(summary.get('schema_version','1.0.0'))}</div>
</div></body></html>"""]
    return "".join(parts)


def generate() -> Dict[str, Path]:
    records = load_all_raw()
    summary = build_summary(records)
    env = _load_env()
    legacy = _load_legacy()
    summary["schema_version"] = "1.0.0"
    summary["recommendations"] = _recommendations(summary)
    out = write_summaries(summary)
    htmls = render_html(summary, env, legacy)
    stamp = summary["generated"]
    rp = paths()["reports"]
    latest = rp / "latest_report.html"
    stamped = rp / f"report_{stamp}.html"
    latest.write_text(htmls, encoding="utf-8")
    stamped.write_text(htmls, encoding="utf-8")
    out["html_latest"] = latest
    out["html_stamped"] = stamped
    return out


def compare_runs(run_a: str, run_b: str) -> Dict[str, Any]:
    """Compare two run_ids (speed tok/s + tool pass-rate deltas)."""
    records = load_all_raw()
    def agg(run_id):
        recs = [r for r in records if r.get("run_id") == run_id]
        speed = {}
        for r in recs:
            if r.get("benchmark_category") == "speed" and r.get("success"):
                speed.setdefault(r["model_display_name"], []).append(r.get("output_tokens_per_sec"))
        speed = {k: _mean(v) for k, v in speed.items()}
        return {"speed": speed, "n": len(recs)}
    a, b = agg(run_a), agg(run_b)
    deltas = {}
    for m in set(a["speed"]) | set(b["speed"]):
        va, vb = a["speed"].get(m), b["speed"].get(m)
        if va is not None and vb is not None:
            deltas[m] = round(vb - va, 2)
    return {"run_a": run_a, "run_b": run_b, "a": a, "b": b, "speed_delta_tps": deltas}
