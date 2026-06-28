# Bounded Live Validation Status

Date: 2026-06-26
Machine: configured GEEKOM host / configured GEEKOM host
Repo: `<repo-root>`
Endpoint: `http://127.0.0.1:13305/api/v1`

## Summary

The first bounded live validation of the unified GEEKOM benchmark framework completed successfully enough to validate the live pipeline end to end. The run exercised environment checks, a small speed smoke test, live vision input, structured output, the agent workflow runner, and report generation.

Start time: approximately 2026-06-26 11:18 Australia/Sydney
End time: approximately 2026-06-26 11:35 Australia/Sydney
Elapsed time: approximately 17 minutes

No results were committed or pushed.

## Preflight

- Confirmed host: `configured GEEKOM host`
- Confirmed repo: `<repo-root>`
- Confirmed branch state: `main...origin/main [ahead 3]`
- Confirmed expected local commits:
  - `b500907` Add deterministic vision benchmark assets
  - `b3ffd7c` Align benchmark framework with public benchmark ecosystem
  - `daa0b17` Refactor into unified benchmark framework (one schema, one runner, one report)
- Confirmed working tree was clean before benchmark commands.
- Confirmed AC sleep was disabled. Display timeout remained non-blocking for the run.
- Lemonade initially had to be awakened with `lemonade status`; after a short shaky startup, `scripts\check_environment.py` confirmed `/models` returned 14 models.

## Commands Run

```powershell
python scripts\check_environment.py
python scripts\run_benchmarks.py --models gemma-4-E2B-it --smoke
python scripts\run_vision_tasks.py --models "Qwen3-VL-8B-Instruct-GGUF"
python scripts\run_structured.py --models "Qwen3-30B-A3B,Nemotron-Cascade-2-30B-A3B"
python scripts\run_agent_workflow.py --models "Nemotron-Cascade-2-30B-A3B" --trials 5
python scripts\generate_report.py --open
```

## Results

Environment check: PASS

- Saved: `results\summary\environment_latest.json`
- Lemonade reachable.
- `/models` returned 14 models.
- All enabled catalog models present.
- GPU utilization quality: measured.
- NPU utilization quality: unsupported/null, as expected for the current llama.cpp Vulkan path.

Speed smoke: PASS

- Run ID: `speed_20260626-111841`
- Model: `gemma-4-E2B-it`
- Prompt: `short_fact`
- Observed console result: 33.81 output tok/s, 128 output tokens, 3.786s elapsed, first-token latency 0.209s.
- Latest aggregate report shows mean speed for this run/model as 35.05 tok/s, mean first-token latency 0.19s, backend `llamacpp:vulkan`, quant `Q4_K_M`.
- Raw: `results\raw\speed\speed_20260626-111841.jsonl`
- Summary: `results\summary\speed_20260626-111841.json`

Vision: PASS

- Run ID: `vision_20260626-112005`
- Model requested: `Qwen3-VL-8B-Instruct-GGUF`
- Reported model: `Qwen3-VL-8B`
- Lemonade accepted image input.
- Score: 13/13 passed, mean score 1.0.
- Covered OCR, invoice/document extraction, chart reading, UI screenshot reading, and image comparison.
- Raw: `results\raw\vision\vision_20260626-112005.jsonl`
- Summary: `results\summary\vision_20260626-112005.json`

Structured output: PARTIAL PASS

- Run ID: `structured_output_20260626-112544`
- `Qwen3-30B-A3B`: 4/5 passed, mean score 0.85.
- `Nemotron-Cascade-2-30B-A3B`: 4/5 passed, mean score 0.87.
- Qwen3 failed `extract_fields` with invalid JSON.
- Nemotron failed `repair_json` with invalid JSON.
- Raw: `results\raw\structured_output\structured_output_20260626-112544.jsonl`
- Summary: `results\summary\structured_output_20260626-112544.json`

Agent workflow: FAILING TASK/PROMPT PATH

- Run ID: `agent_workflow_20260626-112923`
- Model: `Nemotron-Cascade-2-30B-A3B`
- Trials: 5
- Passed: 0/5
- Mean score: 0.16
- Reliability: 0.0
- Pass^k: `k=1` 0.0, `k=2` 0.0, `k=5` 0.0.
- Policy checks: `tool_before_edit` 0/5, `no_fabricated_year` 0/5, `preserve_title` 0/5, `honest_verification` 0/5.
- Trial 1 scored 0.0. Trials 2-5 each scored 0.2 by reaching tool use only.
- This validates that the runner and scoring path execute, but the current agent workflow task/prompt/model path is not usable for recommendation scoring without inspection.
- Raw: `results\raw\agent_workflow\agent_workflow_20260626-112923.jsonl`
- Summary: `results\summary\agent_workflow_20260626-112923.json`

Report generation: PASS

- Latest JSON: `results\summary\latest_summary.json`
- Stamped JSON: `results\summary\summary_20260626-113551.json`
- Latest CSV: `results\summary\latest_summary.csv`
- Latest HTML: `results\reports\latest_report.html`
- Stamped HTML: `results\reports\report_20260626-113551.html`

## Operational Notes

- The bounded validation was intentionally not a full all-model sweep.
- Do not treat the agent workflow result as a model-quality conclusion yet. It may indicate a prompt/task/scoring mismatch, not simply weak model capability.
- Do not fabricate unavailable NPU, power, GPU-layer, batch-size, or model-hash metrics. Keep unsupported values null with reasons.
- Continue to run destructive/code-execution benchmark tasks only under `<repo-root>.tmp\`.
- Do not commit result files unless explicitly requested.
- Do not push the three local framework commits unless explicitly requested.

## Recommended Next Step

Before the longer idle/overnight run, inspect the agent workflow raw outputs and task prompts to determine why Nemotron only reached tool use and failed planning/edit/test/verification checks. After that, prepare the longer benchmark run with the dedicated coding-model tournament included.

## Follow-up Prep on 2026-06-26

After the bounded validation, the agent workflow failure was inspected before any long run was started.

Findings:

- The original agent workflow transcripts showed Nemotron usually called `get_paper_metadata`, but often put JSON/tool-result examples before the corrected `record.txt` block.
- The runner selected the first fenced code block in the combined transcript, which could be a JSON example rather than the corrected file body.
- Some Lemonade blocking responses can report generated tokens while placing text in `reasoning_content`; the blocking client previously ignored that fallback.
- A forced-tool staging experiment was tried in one-trial validation runs, but it did not improve the Lemonade/Nemotron path and was not kept.

Changes made:

- `src\geekom_benchmarks\runners\agent.py` now chooses a fenced block containing both `TITLE:` and `YEAR:` when scoring the emitted corrected file.
- `src\geekom_benchmarks\runners\agent.py` detects the plan step across the combined transcript, not only the first assistant message.
- `src\geekom_benchmarks\runners\agent.py` gives a clearer final-turn instruction to output the corrected file block and verification JSON after any tool result.
- `src\geekom_benchmarks\clients\lemonade.py` now falls back to `reasoning_content` when `message.content` is empty in blocking responses.

Validation performed:

- `python -m compileall src scripts` passed after the prep changes.
- Several one-trial agent checks were run during diagnosis:
  - `agent_workflow_20260626-125100`: improved plan/tool scoring, but no file edit.
  - `agent_workflow_20260626-125239`: showed a prose/fake tool-call pattern.
  - `agent_workflow_20260626-125424`: showed the forced-tool experiment was not useful.
  - `agent_workflow_20260626-125607`: confirmed the path still needs a clean recheck after reverting the forced-tool experiment.

Remaining constraint:

- Do not treat agent workflow scores from these diagnostic one-trial runs as model-quality results. Before the overnight run, rerun a small `--trials 1` or `--trials 3` sanity check with the final runner state, then include the agent workflow in the long run only if the transcript/scoring behavior is sane.
