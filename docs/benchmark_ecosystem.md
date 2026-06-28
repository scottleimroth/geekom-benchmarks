# Benchmark Ecosystem Position

Last updated: 2026-06-28

This repo is a personal umbrella harness for local-AI benchmarking on the operator's
GEEKOM A9 Max. It is not a canonical public benchmark suite and should not be
described as one.

Single-repo rule: the canonical benchmark repo is this `geekom-benchmarks`
checkout. Do not create or maintain a second benchmark framework elsewhere.
Codex workspace folders are scratch/handoff context only.

The job of this repo is to answer local operating questions:

- which local model to use for daily chat, coding, tools, vision, and
  agent workflows;
- how fast those models are on the Ryzen AI 9 HX 370 / Radeon 890M / Lemonade
  stack;
- which failures are caused by local runtime limits, missing models, or task
  design rather than model quality.

When a globally comparable number matters, run the real external benchmark tool
and import its exported artifact here. This repo then normalizes that result into
the same raw JSONL, summary JSON, CSV, and HTML report flow as the local probes.

## Local Taxonomy

The built-in runners use this local taxonomy:

| Local category | Script | Meaning |
| --- | --- | --- |
| `speed` | `scripts/run_benchmarks.py` | Single-stream output tok/s, first-token latency, and derived llama-bench-style pp/tg fields. |
| `tool_reliability` | `scripts/run_tool_reliability.py` | BFCL-lite two-tool dependent workflow across parallel, nopar, and strict staged modes. |
| `structured_output` | `scripts/run_structured.py` | JSON/schema/repair/no-prose checks. |
| `coding` | `scripts/run_coding_tasks.py` | Deterministic local code tasks with execution checks and safety checks. |
| `vision` | `scripts/run_vision_tasks.py` | Deterministic synthetic image/OCR/document/chart/UI tasks. |
| `long_context` | `scripts/run_longcontext.py` | Conservative needle retrieval checks. |
| `agent_workflow` | `scripts/run_agent_workflow.py` | tau-lite state/policy/workflow checks. |

These local categories are operational probes. They are useful for choosing
models on this machine, but they are not substitutes for official suites such as
SWE-bench, BFCL, tau-bench, lm-eval, or MLPerf.

## Canonical External Suite Support

Use `scripts/run_external_benchmarks.py` for external suite imports.

```powershell
python scripts\run_external_benchmarks.py --list-suites
```

Supported external categories:

| Canonical suite | Harness category | Mode | Notes |
| --- | --- | --- | --- |
| llama.cpp `llama-bench` | `llama_bench` | import-only | Import exported llama-bench JSON/CSV/JSONL artifacts. Built-in speed rows also derive pp/tg fields from Lemonade, but those are not ground-truth llama-bench timers. |
| EleutherAI lm-evaluation-harness | `lm_eval` | run+import or import-only | Can run an installed `lm_eval` against Lemonade, or import an existing output folder with `--lm-eval-path`. |
| EvalScope | `evalscope` | run+import or import-only | Can run an installed `evalscope` or import an existing output folder with `--evalscope-path`. |
| MLPerf Client | `mlperf_client` | import-only | MLPerf runs its own runtime stack; run it separately, then import exported JSON. |
| OpenCompass | `opencompass` | import-only | Import exported JSON/JSONL/CSV artifacts. |
| vLLM benchmarks | `vllm` | import-only | Import serving/concurrency/latency benchmark exports. |
| BFCL | `bfcl` | import-only | Import official BFCL result/score exports when available. Local `tool_reliability` remains BFCL-lite. |
| tau-bench | `tau_bench` | import-only | Import official tau-bench exports when available. Local `agent_workflow` remains tau-lite. |
| SWE-bench | `swe_bench` | import-only | Import official/EvalScope SWE-bench reports and reviews. Local `coding` remains a deterministic local coding tournament. |
| RAGAS | `ragas` | import-only | Import RAG app evaluation exports if a local RAG pipeline is added. |
| DeepEval | `deepeval` | import-only | Import LLM-as-judge/test-run exports if used by a local app or CI workflow. |

## CLI Examples

List supported and planned suites:

```powershell
python scripts\run_external_benchmarks.py --list-suites
```

Import a llama-bench export:

```powershell
python scripts\run_external_benchmarks.py --suites llama-bench --llama-bench-path results\external\llama_bench
```

Run lm-eval against Lemonade, if `lm_eval` is installed:

```powershell
python scripts\run_external_benchmarks.py --suites lm_eval --run-external --models Qwen3-30B-A3B --lm-eval-tasks arc_easy,gsm8k
```

Import an existing BFCL export:

```powershell
python scripts\run_external_benchmarks.py --suites bfcl --bfcl-path results\external\bfcl
```

Dry-run an import without writing benchmark rows:

```powershell
python scripts\run_external_benchmarks.py --suites bfcl --bfcl-path results\external\bfcl --dry-run
```

Import multiple external exports:

```powershell
python scripts\run_external_benchmarks.py --suites llama-bench,bfcl,tau-bench --llama-bench-path results\external\llama_bench --bfcl-path results\external\bfcl --tau-bench-path results\external\tau_bench
```

After importing external rows, regenerate the normal report:

```powershell
python scripts\generate_report.py
```

## Honesty Rules

- Never present local `tool_reliability` as official BFCL. It is BFCL-lite.
- Never present local `agent_workflow` as official tau-bench. It is tau-lite.
- Never present local `coding` as SWE-bench. It is a deterministic local coding
  tournament.
- Do not fabricate NPU, power, GPU-layer, batch-size, flash-attention, model-hash,
  or direct llama-bench timer values. Leave unavailable values null and document
  why.
- Treat missing artifacts as `not run`, not failure of the model.
- Run model inference only on the configured GEEKOM benchmark host. Shared
  storage is fine for files, but it is not the benchmark compute target.

## 2026-06-27 Change Note

What changed:

- `scripts/run_external_benchmarks.py` now has an explicit external suite registry
  covering llama-bench, lm-eval, EvalScope, MLPerf Client, OpenCompass, vLLM,
  BFCL, tau-bench, RAGAS, and DeepEval.
- The runner accepts canonical aliases such as `llama.cpp`, `llama-bench`,
  `lm-evaluation-harness`, `mlperf-client`, and `tau-bench`.
- `--list-suites` reports supported versus planned suites.
- Import-only suites now require explicit artifact paths, so the harness does not
  silently imply that an external suite was run.
- `--dry-run` parses artifact paths and reports row counts without writing raw
  result rows.
- Report aggregation includes imported external categories alongside local
  categories.

Why:

The operator asked whether the benchmark coverage included the relevant standard tools.
The correct architecture is an umbrella/import harness, not a replacement for
those tools. This update makes that boundary visible in code and documentation.

Validation performed:

- `python -m compileall src scripts`
- `python scripts\run_external_benchmarks.py --list-suites`
- External import smoke checks using small local sample artifacts for multiple
  suite aliases.

Remaining constraints at the time:

- This 2026-06-27 note was the pre-canonical-run boundary. It was superseded by
  the 2026-06-27/28 external run notes below, which added official/imported
  BFCL, tau-bench, SWE-bench, MLPerf Client, EvalScope, and OpenCompass rows.
- Existing overnight results remain local-taxonomy results unless external rows
  are imported later.

## 2026-06-27 External Run Note

What changed:

- Official llama.cpp `llama-bench` artifacts were run on the GEEKOM from local
  GGUF files and imported into the canonical schema.
- EleutherAI `lm-eval` was installed into the repo-local `.venv` and run against
  Lemonade's OpenAI-compatible chat endpoint for the enabled API model set.
- `scripts/run_external_benchmarks.py` now accepts pass-through arguments for
  `lm-eval` and EvalScope so bounded official runs can use native flags such as
  `--limit` and `--apply_chat_template`.
- `config/models.yaml` disables the vision-capable `gemma-4-12b-it-GGUF-Q4_K_M`
  for API suites after Lemonade returned `model_load_error`; the text-only
  `gemma-4-12b-it-text-Q4_K_M` entry is enabled for text/API benchmarks instead.

Why:

The operator requested the remaining canonical benchmarks be moved from plan to
implementation in this single repo, while keeping compute on the GEEKOM and not
cutting corners. The Gemma 12B catalog adjustment prevents future API sweeps
from repeatedly failing on a model recipe that still has valid direct GGUF
coverage via llama-bench.

Validation performed:

- `llama-bench` import produced 24 canonical rows from 12 local GGUF models.
- `lm-eval` imported rows for all API-runnable enabled text/chat models using
  `gsm8k_cot_zeroshot` with `--limit 1`, `--confirm_run_unsafe_code`, and
  `--apply_chat_template`.
- Direct Lemonade probe confirmed `gemma-4-12b-it-GGUF-Q4_K_M` failed with
  `model_load_error`, while `gemma-4-12b-it-text-Q4_K_M` loaded successfully.

Remaining constraints:

- The user asked to pause after the `lm-eval` model batch on 2026-06-27.
- EvalScope, BFCL, tau-bench, SWE-bench, OpenCompass, MLPerf Client, vLLM,
  RAGAS, and DeepEval remain at the next implementation/run stage.
- EvalScope `gsm8k` download through ModelScope failed DNS resolution for
  `cdn-lfs-cn-1.modelscope.cn`; retry with an alternate dataset hub/cache path
  before treating EvalScope as model-failed.

## 2026-06-28 Canonical Remaining Completion Note

What changed:

- `agent_workflow` was redesigned into a stateful local tool environment with
  `read_record`, `get_paper_metadata`, and `write_record`; tests now clean up
  their temporary canonical rows so report generation is not polluted by fake
  test models.
- Gemma 12B vision/API loading was diagnosed with explicit Lemonade checkpoints.
  Main GGUF and `mmproj-BF16.gguf` were present, but the fixed vision entry still
  failed `model_load_error`; the text-only Gemma 12B entry remains the deliberate
  text/API fallback.
- EvalScope GSM8K, BFCL-v4 non-live subsets, official tau-bench retail, bounded
  SWE-bench Verified, and MLPerf Client v1.6.1 were run/imported into canonical
  rows.
- SWE-bench uses a WSL-local helper venv at
  `<wsl-home>/geekom_swebench_wsl/.venv` because the Windows `swebench` package
  imports POSIX-only `resource`.
- MLPerf Client v1.6.1 Windows x64 and downloaded benchmark assets are cached
  under `results/external/mlperf_client/v1.6.1/`.
- `scripts/run_external_benchmarks.py` now has dedicated BFCL, tau-bench, and
  SWE-bench importers, plus `scripts/record_external_status.py` for
  `blocked-with-evidence` and `not-applicable-by-definition` rows.
- OpenCompass was attempted in the shared `.venv`, but CLI startup did not reach
  usable output in the bounded window; it was removed and `httpx` restored so
  `pip check` passes.

Why:

The operator asked for the remaining canonical benchmark plan to move from planning to
implementation, with no duplicate repo and no fake substitutions for external
benchmark families.

Validation performed:

- `python -m compileall src scripts tests`
- `python -m unittest discover -s tests -p "test_agent_workflow_v2.py"`
- `python -m pip check`
- Dry-run imports for BFCL, tau-bench, SWE-bench, and MLPerf Client before final
  report regeneration.
- `python scripts\generate_report.py`

Remaining constraints:

- OpenCompass and SWE-bench Verified Mini were retried successfully on
  2026-06-28; see the follow-up change note below.
- vLLM is `not-applicable-by-definition` until a real vLLM server is provisioned.
- RAGAS and DeepEval are `not-applicable-by-definition` until there is a
  deliberate local RAG/app fixture.

## 2026-06-28 OpenCompass And SWE-Bench Retry Note

What changed:

- OpenCompass 0.5.2 was installed in an isolated scratch venv at
  `%TEMP%\geekom_opencompass_scratch_20260628\.venv` instead of the shared repo
  `.venv`.
- The OpenCompass ARC-Easy dev fixture was added under
  `results/external/opencompass/`, with a repo-local ARC cache populated from
  Hugging Face `allenai/ai2_arc` after the default OpenCompass Aliyun dataset
  download failed DNS resolution.
- A full OpenCompass ARC-Easy dev run was executed for all 15 downloaded
  Lemonade model IDs, including non-default duplicates and the Gemma 12B legacy,
  text-only, and repaired vision IDs. The run lives at
  `results/raw/external/opencompass/opencompass_arc_easy_all_models_20260628-044332`
  and was imported as `results/raw/opencompass/opencompass_20260628-080149.jsonl`.
- `scripts/run_external_benchmarks.py` now imports OpenCompass summary matrices
  with per-model rows, exact Lemonade model ID mapping, and explicit failed rows
  for non-numeric OpenCompass columns.
- The earlier toy OpenCompass smoke import was removed from canonical raw/summary
  results so it cannot pollute model recommendations.
- SWE-bench Verified Mini was retried through EvalScope/WSL/Docker using
  `--dataset-hub huggingface` and explicit dataset ID
  `MariusHobbhahn/swe-bench-verified-mini`, because EvalScope's default
  `evalscope/swe-bench-verified-mini` ID exists on ModelScope but not on
  Hugging Face. The successful bounded mini run lives at
  `results/raw/external/swe_bench/swe_bench_verified_mini_hf_20260628-080642`
  and was imported as `results/raw/swe_bench/swe_bench_20260628-081232.jsonl`.
- The earlier SWE-bench Verified import was regenerated as
  `results/raw/swe_bench/swe_bench_20260628-081231.jsonl` after the importer was
  normalized to keep instance-review rows under the exact Lemonade catalog model
  ID instead of the response GGUF filename.

Why:

The operator asked to retry failed benchmark families properly, especially OpenCompass
and SWE-bench, without shortcuts. The prior OpenCompass row was only a bounded
startup failure, not a model-performance result; the prior SWE-bench mini blocker
was a dataset-hub path issue, not a model result.

Validation performed:

- OpenCompass dry-run partitioned 15 model tasks against 567 ARC-Easy dev
  examples before the full run.
- OpenCompass completed with 13 scored model rows and 2 failed Gemma 12B
  vision-capable API rows.
- SWE-bench Verified Mini completed one Docker-reviewed mini instance with
  EvalScope exit 0.
- Dry-run imports: OpenCompass 15 rows, SWE-bench Verified Mini 10 rows.

Remaining constraints:

- `gemma-4-12b-it-GGUF-Q4_K_M` and
  `gemma-4-12b-it-vision-fixed-Q4_K_M` still fail Lemonade API loading with
  `model_load_error` / `llama-server failed to start`. The text-only
  `gemma-4-12b-it-text-Q4_K_M` entry remains the deliberate API fallback.
- The operator also tried a fresh Lemonade search/download using the full Hugging Face
  repo name `unsloth/gemma-4-12b-it-GGUF`; that fresh model also failed to load.
  Treat the Gemma 12B vision/API path as deliberately closed until Lemonade or
  the underlying llama.cpp recipe changes.
- OpenCompass ARC-Easy is one general multiple-choice benchmark. It is useful
  canonical coverage, but it should not replace the local speed, coding, tool,
  vision, and workflow-specific recommendations.
- SWE-bench Verified and Verified Mini coverage is still bounded to one instance
  each for resource control; both scored 0.0 on the tested Qwen3-Coder run.
