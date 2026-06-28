# Full Suite Overnight Status (2026-06-26)

Date: 2026-06-26
Machine: configured GEEKOM host / configured GEEKOM host
Repo: `<repo-root>`
Endpoint: `http://127.0.0.1:13305/api/v1`

## Summary

Completed run: `run_all.py --models all --trials 20` on all configured categories.

Start (approx): 2026-06-26 2:16 PM AEST
End (approx): 2026-06-26 9:01 PM AEST
Output artifact set:

- `results\summary\latest_summary.json` (run id `20260626-210202`)
- `results\summary\summary_20260626-210202.json`
- `results\summary\latest_summary.csv`
- `results\reports\latest_report.html`
- `results\reports\report_20260626-210202.html`
- Staged stage summaries:
  - `results\summary\long_context_20260626-195041.json`
  - `results\summary\agent_workflow_20260626-204815.json`
  - `results\summary\vision_20260626-192425.json`
  - `results\summary\coding_20260626-184949.json`

## Commands Executed

```powershell
python scripts\run_all.py --models all --trials 20
```

## Validation Summary (all-category sweep)

- Environment remained healthy through the run (endpoint reachable, endpoint model inventory unchanged from check).
- Speed: 11 models (64 runs total in final summary) completed.
- Tool reliability: 780 runs total, including parallel/nopar/strict modes.
- Structured output: 65 runs total.
- Coding: 89 runs total across 11 models.
- Vision: 65 runs total (including skipped entries for failed model-load cases).
- Long context: 99 runs total.
- Agent workflow: 26 runs total.

Notable outcomes:

- `gemma-4-12b-it` failed to load for all API-backed stages (`api_error model_load_error`, `llama-server failed to start`), so its vision/structured/long-context/tool-workflow results are either failed/skipped.
- `olmOCR-2-7B` passed all vision tasks and all long-context tasks, and had a full 4/4 pass coding score in this run.
- Tool reliability remained perfect (`overall_pass_rate = 1.0`) on most models where evaluation executed; `gemma-4-12b-it` and `olmOCR-2-7B` had mode-specific structural/API issues as noted in the latest summary.
- Agent workflow quality remained low overall and is not yet suitable for production model ranking without another workflow/task redesign.

## Coding Recommendation

From this full-suite run, the top coding recommendation is:

- `olmOCR-2-7B` (4/4 coding tasks passed, mean score 1.0)

Keep in mind this is based on the local deterministic coding harness and can shift with task mix.

## Standards/Benchmark Alignment

These runs use the local benchmark taxonomy and scoring logic in this repo:

- Speed: local prompt-class speed profile aligned to common token-throughput conventions (llama-bench-style prompt families), not an official external benchmark submission.
- Tool reliability: BFCL-lite-style reliability pattern (parallel/nopar/strict modes and policy fail buckets).
- Structured output: schema/JSON extraction and grading harness, not a direct external structured benchmark.
- Agent workflow: tau/lab-style agent workflow with tool-use/edit/verify checkpoints.
- Coding: deterministic local tasks (`fix_bug`, `refactor_dedupe`, `windows_path_repair`, `detect_unsafe_delete`) with runtime execution checks and static guard checks; not a replacement for full SWE-bench.

## Validation Performed

- Confirmed report artifacts and run summaries were generated and stamped.
- Confirmed `latest_summary.json` and `latest_report.html` contain the all-category run id `20260626-210202`.

## Remaining Operational Constraints

- `gemma-4-12b-it` remains unusable in this environment until model download/load is resolved for a desktop-triggered artifact path.
- Agent workflow remains low-quality in this benchmark configuration; do not use its scores for model selection yet.
- No commits were made or pushed in this run.
