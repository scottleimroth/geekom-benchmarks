# Overnight status â€” geekom-benchmarks framework build + staged validation

**Machine:** configured GEEKOM host (GEEKOM A9 Max) Â· **Repo:** `<repo-root>`
**Run window:** 2026-06-25 ~23:30 â†’ 2026-06-26 ~00:30
**Endpoint:** http://127.0.0.1:13305/api/v1 (Lemonade 10.6.0, llama.cpp Vulkan)
**Overall: ALL STAGED VALIDATION STEPS PASSED.** Full all-model suite intentionally NOT run.

---

## Completed steps

| # | Step | Result |
|---|------|--------|
| 0 | Pre-flight (hostname / Y: drive / writable / Lemonade) | PASS â€” configured GEEKOM host, Y: writable, Lemonade reachable (initial refusal was transient startup) |
| â€” | Framework build / refactor (18 phases) | DONE â€” package, 7 runners, one schema, one report generator |
| â€” | Preserve legacy results | DONE â€” `results/benchmarks.json`, `results/tool-calling/`, `data/` left in place; `.bak`/pycache moved to `results/archive/pre-framework-2026-06-25/` |
| â€” | Old scripts kept as shims | DONE â€” `benchmark.py`, `tool_call_reliability_modes.py` now forward to the new CLIs (originals archived) |
| 1 | Environment check | PASS (12/12 checks; GPU util **measured**, NPU **unsupported**=honest) |
| 2 | Smoke test (gemma-4-E2B-it, 1 prompt) | PASS â€” 35.7 tok/s; fixed first-token latency for thinking models mid-validation |
| 3 | Speed bench, large model (Nemotron-Cascade-2-30B-A3B) | PASS â€” 20.0 tok/s mean (short 19.5 / med 21.0 / long 18.0 / code 20.7 / agent 20.9); matches known-good ~21.2 |
| 4 | Tool reliability â€” Qwen3-30B-A3B + Nemotron, 20 trials Ã— 3 modes | PASS â€” **all 6 combos 20/20** |
| 5 | Coding task (Qwen3-Coder-30B-A3B, windows_path_repair) | PASS â€” model code executed in temp workspace, test rc=0 |
| 6 | Generate HTML report | PASS â€” `results/reports/latest_report.html` |

## Failed / skipped steps

- **No failures.** One issue found and fixed during validation (see below).
- **Intentionally NOT run** (per overnight instructions): full all-model speed sweep, structured-output, vision, long-context, agent-workflow, and the other coding tasks/models. Scaffolding for all of these is built and import-clean, just not executed.

## Issue found & fixed

- **First-token latency returned `null` for thinking models.** gemma-4 / Qwen3 stream
  `reasoning_content` deltas before final `content`; the stream parser only watched
  `content`, so with a low token cap the whole budget went to reasoning and no
  first-token time was recorded. **Fix:** `src/geekom_benchmarks/clients/lemonade.py`
  now counts the first token of *either* kind toward latency and captures reasoning
  text. Re-verified: ftl=0.17s (gemma), 0.54â€“4.69s (Nemotron). Throughput numbers were
  always correct (API usage counts reasoning tokens).

## Notable result (reported honestly, old data preserved)

- **Qwen3-30B-A3B scored 20/20 in ALL three tool modes this run** (parallel/nopar/strict),
  vs. the **preserved** earlier result of 12/20 (nopar) and 14/20 (parallel). The earlier
  data is untouched in `results/tool-calling/`. This is a genuine re-test improvement
  (likely newer model build / llama.cpp b9253 / Lemonade 10.6.0). Treat the strict-mode
  guidance as still-valid insurance, but loose-mode reliability has improved on this box.

---

## Commands run (validation)

```bat
python scripts\check_environment.py
python scripts\run_benchmarks.py --models gemma-4-E2B-it --smoke
python scripts\run_benchmarks.py --models Nemotron-Cascade-2-30B-A3B
python scripts\run_tool_reliability.py --models "Qwen3-30B-A3B,Nemotron-Cascade-2-30B-A3B" --trials 20
python scripts\run_coding_tasks.py --models Qwen3-Coder-30B-A3B --tasks windows_path_repair
python scripts\generate_report.py
```

## Files created / modified (high level)

- **New package:** `src/geekom_benchmarks/` â€” `config.py`, `clients/{base,lemonade}.py`,
  `schemas/result.py` (canonical schema v1.0.0), `metrics/windows.py`,
  `runners/{base,speed,tool_reliability,structured,coding,vision,longcontext,agent}.py`,
  `reporting/report.py`, `utils/io.py`.
- **New scripts:** `check_environment.py`, `run_benchmarks.py`, `run_tool_reliability.py`,
  `run_structured.py`, `run_coding_tasks.py`, `run_vision_tasks.py`, `run_longcontext.py`,
  `run_agent_workflow.py`, `collect_windows_metrics.py`, `generate_report.py`,
  `compare_runs.py`, `run_all.py`, `_bootstrap.py`.
- **New config:** `config/models.yaml` (13 models, 11 enabled, exact Lemonade ids),
  `config/tasks.yaml`, `config/hardware.yaml`.
- **New top-level:** `README.md` (rewritten), `requirements.txt`, `pyproject.toml`,
  `Run_All_Benchmarks.bat`.
- **Shimmed:** `scripts/benchmark.py`, `scripts/tool_call_reliability_modes.py`.
- **Preserved (unchanged):** `results/benchmarks.json`, `results/tool-calling/*`,
  `data/780m-leaderboard.json`. Archived: `results/archive/pre-framework-2026-06-25/`.
- **New results this run:**
  - `results/raw/speed/*.jsonl` (8 records, 4 runs incl. smoke)
  - `results/raw/tool_reliability/tool_reliability_20260625-235623.jsonl` (120 records)
  - `results/raw/coding/*.jsonl` (1 record)
  - `results/summary/{environment_latest.json, latest_summary.json/.csv, ...}`
  - `results/reports/latest_report.html` (+ timestamped)
- **Temp workspace (outside tracked repo):** `<repo-root>.tmp\coding_*` â€” safe to delete.

## Benchmark results summary (this validation run)

| Category | Result |
|---|---|
| Speed | Nemotron-Cascade-2-30B-A3B **20.0 tok/s** mean; gemma-4-E2B-it **35.5 tok/s** (only these 2 tested) |
| Tool reliability | Qwen3-30B-A3B **20/20/20**, Nemotron-Cascade **20/20/20** (parallel/nopar/strict) |
| Coding | Qwen3-Coder-30B-A3B windows_path_repair **PASS** (1/1) |
| NPU / hybrid backends | **Not used** â€” llama.cpp Vulkan runs on the iGPU; NPU util recorded `unsupported`, power `unsupported` (never faked) |

**Fastest model (tested):** gemma-4-E2B-it (small) / Nemotron-Cascade ~20 tok/s among large.
**Most reliable tool model:** tie â€” Qwen3-30B-A3B and Nemotron-Cascade both 60/60.
**Best coding model (tested):** Qwen3-Coder-30B-A3B (1/1; only task/model tested).

## Report path

`<repo-root>\results\reports\latest_report.html`
(open directly in a browser â€” no server needed)

---

## Next recommended command

Run the remaining categories on the two proven models first (keeps it bounded), then widen:

```bat
REM remaining categories, proven models only (safe, ~moderate length):
python scripts\run_structured.py --models "Qwen3-30B-A3B,Nemotron-Cascade-2-30B-A3B"
python scripts\run_coding_tasks.py --models Qwen3-Coder-30B-A3B
python scripts\run_agent_workflow.py --models "Qwen3-30B-A3B,Nemotron-Cascade-2-30B-A3B"
python scripts\run_vision_tasks.py --models Qwen3-VL-8B
python scripts\generate_report.py --open
```

Then, when ready for the full sweep (long; all enabled models, all categories):

```bat
Run_All_Benchmarks.bat
```

### Caveats for the next session
- Vision needs images in `test_assets\vision\` (chart.png, text_panel.png) or it emits
  honest SKIPPED rows. Add real screenshots before trusting vision scores.
- Speed recommendations in the report are partial â€” only 2 models were speed-tested here,
  so "daily_chat = gemma-4-E2B-it" is an artifact of limited data, not a verdict.
- Structured / long-context / agent runners are built and import-clean but UNTESTED
  against a live model â€” exercise them on one model before a full sweep.
