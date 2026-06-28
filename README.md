# geekom-benchmarks

A **personal umbrella harness** for **local-AI benchmarking & agent-readiness**
on the **GEEKOM A9 Max** (AMD Ryzen AI 9 HX 370 Â· Radeon 890M Â· XDNA2 NPU Â· 32 GB
unified memory), running local models through **Lemonade** (llama.cpp, Vulkan).

> This repo is **not a canonical public benchmark**. It runs its own probes and
> *aligns with* the styles/metrics of public suites (llama-bench, BFCL, tau-bench,
> lm-evaluation-harness, EvalScope, MLPerf Client) via thin adapters. See
> **[docs/benchmark_ecosystem.md](docs/benchmark_ecosystem.md)** for exactly where
> it sits relative to each of those.

One runner base Â· one result schema Â· one report generator. Every run is
timestamped and preserved; nothing is overwritten.

For the plain-English daily model picker, see
**[LOCAL_MODEL_QUICK_REFERENCE.md](LOCAL_MODEL_QUICK_REFERENCE.md)**.

> The GEEKOM A9 Max is the **reference implementation**. The public repo does
> not record the private hostname; set `GEEKOM_BENCHMARK_HOSTNAME` locally if
> you want the environment check to enforce one. The architecture is
> adapter-based so NVIDIA / Apple Silicon / Ollama / LM Studio backends can be
> added later without touching the runners.

---

## Why benchmarks must run on the GEEKOM

The benchmark *code/results* may live on shared storage, but the **runner must
execute on the GEEKOM** because it is the machine with Lemonade, the Radeon 890M
iGPU, the Ryzen AI NPU, and the local GGUF models. **Never run model benchmarks
on the Pi or a storage-only host.** Set `GEEKOM_BENCHMARK_HOSTNAME` locally if
you want `scripts\check_environment.py` to enforce a private hostname.

This is the single canonical benchmark repo. Do not create parallel benchmark
repos or move active benchmark work into a Codex handoff folder; those folders are
scratch/context only.

---

## Hardware (reference)

| | |
|---|---|
| Host | GEEKOM A9 Max, Windows 11 Pro |
| CPU | AMD Ryzen AI 9 HX 370 (Strix Point, Zen5, 12C/24T) |
| iGPU | AMD Radeon 890M (16 CU, RDNA 3.5) â€” used by llama.cpp Vulkan |
| NPU | AMD Ryzen AI / XDNA2 (~50 TOPS) â€” **not** used by the GGUF runs |
| Memory | 32 GB LPDDR5X unified |
| Runtime | Lemonade Â· `http://127.0.0.1:13305/api/v1` |

Defined in `config/hardware.yaml`. Comparison baseline (Radeon 780M) in
`data/780m-leaderboard.json`.

---

## Setup

```bat
REM Python 3.9+ (tested on 3.11.9). From the repo root:
python -m pip install -r requirements.txt
```

Required packages: `requests`, `PyYAML`, `psutil`. Optional `Pillow` only to
regenerate vision test images.

### Start / check Lemonade

```bat
REM Lemonade should already be running and serving on port 13305.
lemonade status
curl http://127.0.0.1:13305/api/v1/models
```

If `lemonade status` says "running on port 13305" but a request is refused, give
it a moment after launch (the socket binds a beat after the status flag flips).

---

## Quick start

```bat
REM 1. Environment check (hostname, repo, Lemonade, models, GPU/NPU, metrics)
python scripts\check_environment.py

REM 2. Smoke test - one small model, one short prompt (fast)
python scripts\run_benchmarks.py --models gemma-4-E2B-it --smoke

REM 3. A real speed run
python scripts\run_benchmarks.py --models all

REM 4. Tool-calling reliability (the headline agent metric)
python scripts\run_tool_reliability.py --models Qwen3-30B-A3B,Nemotron-Cascade-2-30B-A3B --trials 20

REM 5. Coding tasks
python scripts\run_coding_tasks.py --models Qwen3-Coder-30B-A3B

REM 6. Build the HTML report
python scripts\generate_report.py --open
```

Run **everything** (long; all enabled models, all categories):

```bat
Run_All_Benchmarks.bat
```

---

## Benchmark categories

| Category | Script | What it measures |
|---|---|---|
| Speed | `run_benchmarks.py` | tok/s + first-token latency across short/medium/long/coding/agent prompts (warm-up excluded) |
| Tool reliability | `run_tool_reliability.py` | 2-tool multi-step task in **parallel / nopar / strict** modes |
| Structured output | `run_structured.py` | valid JSON, schema-conformance, enum, repair, no-prose |
| Coding | `run_coding_tasks.py` | deterministic local tasks with executable tests + safety scan |
| Vision | `run_vision_tasks.py` | image description / OCR (vision models only; else SKIPPED) |
| Long context | `run_longcontext.py` | needle retrieval at 4K/8K/16K (conservative, ctx-aware) |
| Agent workflow | `run_agent_workflow.py` | plan â†’ tool â†’ file-edit â†’ test â†’ verify |
| Report | `generate_report.py` | one HTML report from all raw results |

`scripts\run_all.py` orchestrates them (overnight-safe: a stage failure is logged
and the next stage still runs). `scripts\collect_windows_metrics.py` snapshots
RAM/CPU/GPU/NPU/temp/power on demand. `scripts\compare_runs.py` diffs two runs.

For benchmark ecosystem imports, use `scripts\run_external_benchmarks.py`:

- `llama_bench`, `lm_eval`, `evalscope`, `mlperf_client`, `opencompass`, `vllm`,
  `bfcl`, `tau_bench`, `ragas`, `deepeval`
- `lm_eval` and `evalscope` can run an installed external CLI or import existing
  exports; the others are import-only.
- `swe_bench` is planned only. Run official SWE-bench separately and import
  exports later; the local coding tournament is not SWE-bench.

```bat
python scripts\run_external_benchmarks.py --list-suites
python scripts\run_external_benchmarks.py --suites bfcl --bfcl-path results\external\bfcl --dry-run
```

---

## How results are stored

```
results/
  raw/<category>/<run_id>.jsonl     # one canonical record per task/trial (never overwritten)
  raw/<category>/responses/         # raw model responses referenced by raw_response_path
  summary/                          # environment_latest.json, latest_summary.json/.csv, per-run summaries
  reports/                          # latest_report.html + report_<timestamp>.html
  archive/                          # preserved pre-framework artifacts
  benchmarks.json, tool-calling/    # legacy results (preserved, folded into the report)
logs/
```

**One schema** (`src/geekom_benchmarks/schemas/result.py`, v1.0.0) is used by
every category. Summaries and reports are *derived* from the raw JSONL â€” runners
never invent their own output format.

### Destructive test workspaces (deliberate, outside the repo)

The coding and agent benchmarks **execute model-generated code** and edit files.
To keep that strictly away from real data **and** away from the tracked repo,
those runners write only to a **sibling temp directory**, never inside the repo:

```
<repo-root>.tmp\coding_<run_id>\<task>\
<repo-root>.tmp\agent_<run_id>\
```

This is intentional: `geekom-benchmarks.tmp` is a sibling of the repo
(`REPO_ROOT.parent / "geekom-benchmarks.tmp"`), so destructive artifacts can
never be accidentally committed and are safe to delete at any time. Execution is
further bounded by a 30 s timeout, a static safety scan, and cwd pinned to the
task dir. Nothing destructive is ever written inside `<repo-root>`
itself (the tool benchmark's `results/raw/.../scratch/` notes are create-only and
gitignored). See `config/hardware.yaml` â†’ `safety` for the declared paths.

---

## Interpreting results (key findings to date)

- **MoE >> dense on this hardware.** Memory bandwidth is the binding constraint;
  a 30B MoE (~3B active) behaves like a small model for decode. Dense
  **Qwen3.5-27B (~4 tok/s)** is *not* a default choice.
- **Speed leaders:** gpt-oss-20b ~22.6, Nemotron-Cascade ~21.2, Qwen3.6-35B ~18.4,
  Qwen3-30B-A3B ~28 (warm probe â€” *labelled*, not directly comparable to 512-tok runs).
- **Tool reliability:** **Nemotron-Cascade-2-30B-A3B** is the agentic champion
  (60/60 across parallel/nopar/strict). **Qwen3-30B-A3B** is fast but only
  reliable under **strict staged orchestration** (20/20 strict; 12â€“14/20 loose â€”
  it saves the *wrong year*, not malformed JSON).
- **Strict staged tool-calling is a first-class orchestration mode**, not a hack.

Recommendations are regenerated into the HTML report each run.

---

## Known limitations

- **NPU / power are not measured for these runs.** llama.cpp Vulkan uses the
  iGPU, not the XDNA2 NPU; Windows exposes no stable NPU perf counter that maps
  to these runs, and no documented AMD APU package-power API. These metrics are
  recorded as `null` with quality `unsupported` â€” **never fabricated**.
- GPU utilization/memory come from Windows perf counters (may need a normal user
  session; flagged `unreliable` where committedâ‰ resident).
- Token counts are API-reported where available, otherwise estimated and flagged
  `tokens_estimated=true`.
- Do **not** expose the Lemonade API publicly â€” it is an unauthenticated
  localhost endpoint.

---

## Adding a new model

Append to `config/models.yaml` with the **exact Lemonade id** (verify with
`curl .../v1/models`):

```yaml
  - id: <exact-lemonade-id>
    display_name: My-Model
    family: ...
    param_size: 8
    arch: moe            # or dense
    quant: Q4_K_M
    context_window: 131072
    uses: [daily_chat, tool_agent]   # drives which benchmarks include it
    enabled: true
```

Disabled models keep a `skip_reason` (and `pull_command` if inferable).

## Adding a new benchmark task

- **Prompt-only** task (speed/structured/long-context/vision): add it under the
  relevant section of `config/tasks.yaml`.
- **Coding** task (needs a test): add a `CodingTask` to
  `src/geekom_benchmarks/runners/coding.py` (a self-contained `test_src`, or a
  `static_grader` for non-executed safety checks).
- A **new category**: subclass `BaseRunner`, emit `BenchmarkResult` records, and
  add a ranking block to `reporting/report.py`. Do **not** create a parallel
  output format.

---

## Repo layout

```
config/        models.yaml Â· tasks.yaml Â· hardware.yaml
scripts/       thin CLIs (check_environment, run_*, generate_report, run_all, compare_runs)
src/geekom_benchmarks/
  clients/     OpenAI-compatible adapter (LemonadeClient) behind a neutral base
  metrics/     Windows metrics w/ quality flags
  runners/     one BaseRunner + 7 category runners
  reporting/   the single report generator
  schemas/     the one canonical result schema
  utils/       paths, run-ids, JSONL/atomic IO
results/       raw/ summary/ reports/ archive/  (+ preserved legacy files)
test_assets/   vision/ coding/
Run_All_Benchmarks.bat
```
