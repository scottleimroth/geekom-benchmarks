# Canonical Remaining Benchmark Status - 2026-06-27

## Execution Context

- Host: `configured GEEKOM host` / Windows 10 Pro 64-bit.
- Repo root: `<repo-root>`.
- Compute target: local Geekom Windows machine with Lemonade llama.cpp Vulkan.
- Lemonade endpoint: `http://127.0.0.1:13305/api/v1`.
- Docker Desktop: available, Linux engine 29.2.0.
- WSL: `Ubuntu` and `docker-desktop` running.
- Existing unrelated Python processes at preflight were not repo benchmark jobs.
- Existing Lemonade processes were left running.
- Existing uncommitted worktree changes and historical benchmark artifacts were preserved.

## Preflight Decisions

- Keep all work in this single repo; do not create a second benchmark repo.
- Treat `results/raw/external/evalscope/evalscope_20260627-150250` as an aborted diagnostic EvalScope run. It is not eligible for ranking/import.
- Keep `gemma-4-12b-it-text-Q4_K_M` as the text/API fallback until the vision-capable Gemma 12B entry is either fixed and validated or deliberately closed as blocked.
- Keep local `agent_workflow` separate from official tau-bench.

## Work Log

- 2026-06-27: Created this ledger before Gemma repair, agent workflow redesign, and remaining canonical benchmark execution.
- 2026-06-27: Diagnosed Gemma 12B. Main GGUF and `mmproj-BF16.gguf` were present locally; a new explicit `gemma-4-12b-it-vision-fixed-Q4_K_M` Lemonade entry still failed with `model_load_error` / `llama-server failed to start`. The text-only `gemma-4-12b-it-text-Q4_K_M` loaded and served API text successfully, so this is closed as a Lemonade vision recipe/runtime blocker rather than a missing download.
- 2026-06-27: Reworked local `agent_workflow` into a stateful tool environment with `read_record`, `get_paper_metadata`, and `write_record`; focused tests passed and Nemotron-Cascade live sanity passed 3/3 with reliability 1.0.
- 2026-06-27: EvalScope adapter/importer was hardened for `.venv` executable resolution, failure logging, and review JSONL imports. Clean EvalScope GSM8K smoke output imported successfully from `results/raw/external/evalscope/evalscope_20260627-172536`.
- 2026-06-27: User requested pause for local computer work. Stopped the active all-model EvalScope runner/subprocess and unloaded Lemonade. Partial all-model EvalScope output under `results/raw/external/evalscope/evalscope_20260627-172747` must be treated as paused/partial until inspected or rerun.
- 2026-06-27: Resumed and completed remaining bounded EvalScope GSM8K models in `results/raw/external/evalscope/evalscope_20260627-200218`; imported 245 additional rows. Combined with the pre-pause import, all enabled models now have bounded EvalScope GSM8K coverage.
- 2026-06-27: Installed official BFCL dependency `bfcl-eval==2025.10.27.1` plus missing transitive `soundfile`. This downgraded `.venv` `numpy` to 1.26.4 and `tenacity` to 8.5.0 per BFCL's pinned requirements; final verification must re-run repo checks.
- 2026-06-27: Ran BFCL-v4 bounded non-live subsets (`simple_python`, `multiple`, `parallel`, `irrelevance`, limit 1) for Qwen3-30B, Nemotron-Cascade, Qwen3.6-35B, gpt-oss-20b, and Qwen3-Coder under `results/raw/external/bfcl/bfcl_v4_non_live_20260627`; all returned code 0.
- 2026-06-27: Imported BFCL via the generic importer into `results/raw/bfcl/bfcl_20260627-202953.jsonl`, but inspection showed the generic importer over-parsed function names/subsets as model IDs. Treat that import as superseded/noisy until a BFCL-specific import cleanup is done.
- 2026-06-27: User requested another pause. Stopped at a safe post-BFCL boundary and unloaded Lemonade; no EvalScope/BFCL/tau/SWE/llama-server benchmark process remained.
- 2026-06-27: Added a BFCL-specific importer and replaced the noisy generic BFCL imports with `results/raw/bfcl/bfcl_20260627-223056.jsonl` containing 65 report-level rows.
- 2026-06-27: Ran official tau-bench through EvalScope on one bounded retail task with Nemotron-Cascade as the agent model and Gemma E2B as the user simulator; imported `results/raw/tau_bench/tau_bench_20260627-225847.jsonl`.
- 2026-06-27: Installed EvalScope SWE-bench support in WSL-local venv `<wsl-home>/geekom_swebench_wsl/.venv` because the Windows `swebench` package imports POSIX `resource`. `swe_bench_verified_mini` initially hit ModelScope CDN DNS failure, then bounded `swe_bench_verified` ran through Hugging Face/Docker. Its final normalized import is `results/raw/swe_bench/swe_bench_20260628-081231.jsonl`.
- 2026-06-28: Ran official MLPerf Client v1.6.1 Windows x64, Phi 3.5 Mini Instruct, AMD OrtGenAI-RyzenAI NPU+GPU config. Cached the official client/assets under `results/external/mlperf_client/v1.6.1/` and imported 24 MLPerf metric rows from `results/raw/external/mlperf_client/mlperf_client_20260627_phi35_ryzenai`.
- 2026-06-28: Attempted OpenCompass 0.5.2. The CLI did not reach usable output in the bounded startup window, so it was classified `blocked-with-evidence`; the package was removed and `httpx` restored to 0.28.1 so `pip check` passes.
- 2026-06-28: Classified vLLM as not applicable until a real vLLM server is provisioned. Classified RAGAS and DeepEval as app/RAG evaluation frameworks awaiting a deliberate local fixture.
- 2026-06-28: Regenerated `results/summary/latest_summary.*` and `results/reports/latest_report.html`; updated `docs/benchmark_ecosystem.md` and `results/summary/recommended_model_matrix_daily_20260627.md`.
- 2026-06-28: Retried OpenCompass properly in isolated scratch venv `%TEMP%\geekom_opencompass_scratch_20260628\.venv`. Added repo-local OpenCompass ARC-Easy dev fixture/cache under `results/external/opencompass/`, ran all 15 downloaded Lemonade model IDs on the full 567-example ARC-Easy dev set, and imported `results/raw/opencompass/opencompass_20260628-080149.jsonl` with 13 scored rows plus 2 Gemma vision-capable load-failure rows.
- 2026-06-28: Removed the earlier toy OpenCompass smoke import from canonical raw/summary outputs so it does not affect recommendations.
- 2026-06-28: Retried SWE-bench Verified Mini through EvalScope/WSL/Docker with `--dataset-hub huggingface` and explicit HF dataset ID `MariusHobbhahn/swe-bench-verified-mini`. The bounded one-instance run completed with EvalScope exit 0 and imported as `results/raw/swe_bench/swe_bench_20260628-081232.jsonl`.
- 2026-06-28: Normalized the SWE-bench importer so instance-review rows keep the exact Lemonade catalog model ID rather than the response GGUF filename; removed superseded noisy/status SWE-bench canonical imports.
- 2026-06-28: The operator tried a fresh Lemonade search/download using the full Hugging Face repo name `unsloth/gemma-4-12b-it-GGUF`; that fresh Lemonade-managed model also failed to load. Gemma 12B vision/API is therefore deliberately closed as a Lemonade/runtime compatibility blocker, while `gemma-4-12b-it-text-Q4_K_M` remains the text-only fallback.

## Final Status

Completed. All remaining benchmark families from the approved plan are either `completed`, `blocked-with-evidence`, or `not-applicable-by-definition` in the single repo.

Completed/imported:

- EvalScope bounded GSM8K for the enabled local API model set.
- BFCL-v4 bounded non-live subsets for the selected local model set.
- Official tau-bench bounded retail task.
- Bounded SWE-bench Verified through EvalScope/WSL/Docker.
- Bounded SWE-bench Verified Mini through EvalScope/WSL/Docker with an explicit Hugging Face dataset override.
- Official MLPerf Client v1.6.1 Windows x64 Phi 3.5 RyzenAI NPU+GPU run.
- OpenCompass ARC-Easy dev for all downloaded Lemonade model IDs.

Classified:

- vLLM: `not-applicable-by-definition` for the current Lemonade/llama.cpp stack.
- RAGAS and DeepEval: `not-applicable-by-definition` until a RAG/app fixture exists.
- Gemma 12B vision-capable Lemonade API IDs: `blocked-with-evidence` by `model_load_error`; text-only Gemma 12B remains usable for API text suites.

Validation:

- `python -m compileall src scripts tests`
- `python -m unittest discover -s tests -p "test_agent_workflow_v2.py"`
- `python -m pip check`
- Dry-run imports for BFCL, tau-bench, SWE-bench, MLPerf Client, and OpenCompass.
- `python scripts\generate_report.py`
