# Local Model Quick Reference

Last updated: 2026-06-28

Use this as the simple daily guide for the operator's local Lemonade models on the
GEEKOM A9 Max. These recommendations are based on this repo's local benchmark
runs plus imported canonical-style results where available. They are operational
choices for this machine, not universal public leaderboard claims.

## What To Use

| Job | Use this model | Exact Lemonade ID | Why |
| --- | --- | --- | --- |
| Everyday chat, quick questions, light summaries | Gemma 4 E2B | `Gemma-4-E2B-it-GGUF` | Best small daily default: fast, stable, cheap to run, and good enough for routine local use. |
| Coding | Qwen3 Coder 30B A3B | `Qwen3-Coder-30B-A3B-Instruct-GGUF-Q4_K_M` | Best local coding default from the fair coding tournament; tied the top score and finished faster than `gpt-oss-20b`. |
| Coding fallback | gpt-oss 20B | `gpt-oss-20b-mxfp4-GGUF` | Also strong in the local coding tournament, but slower than Qwen3 Coder for the winning result. |
| Tool use and function-calling | Qwen3 30B A3B | `Qwen3-30B-A3B-GGUF` | Strong official BFCL-style bounded result; use strict staged tool orchestration for important work. |
| Autonomous agent workflows | Nemotron Cascade 30B A3B | `nvidia_Nemotron-Cascade-2-30B-A3B-GGUF-Q4_K_M` | Best conservative choice for multi-step/tool-heavy local agent work; passed the redesigned local agent sanity check. |
| Long context or careful reasoning | Nemotron Cascade 30B A3B | `nvidia_Nemotron-Cascade-2-30B-A3B-GGUF-Q4_K_M` | Strong local long-context/workflow behavior and good reliability. |
| Heavier reasoning alternative | Qwen3.6 35B A3B | `Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M` | Larger and slower, but useful when you want another strong reasoning model. |
| Vision and general image understanding | Qwen3 VL 8B | `Qwen3-VL-8B-Instruct-GGUF` | Primary vision model and strong OpenCompass ARC-Easy showing. |
| OCR/document reading | olmOCR 2 7B | `allenai_olmOCR-2-7B-1025-GGUF-Q4_K_M` | OCR-specialized model; use when document/image text extraction is the main task. |
| Cheap small assistant alternative | Gemma 4 E4B | `gemma-4-E4B-it-GGUF:UD-Q4_K_XL` | Useful if Gemma E2B is too small but you still want a compact model. |

## Simple Defaults

- Chat: `Gemma-4-E2B-it-GGUF`
- Coding: `Qwen3-Coder-30B-A3B-Instruct-GGUF-Q4_K_M`
- Tools/agents: `nvidia_Nemotron-Cascade-2-30B-A3B-GGUF-Q4_K_M`
- Vision: `Qwen3-VL-8B-Instruct-GGUF`
- OCR: `allenai_olmOCR-2-7B-1025-GGUF-Q4_K_M`

## Use With Caution Or Avoid

- `gemma-4-12b-it-GGUF-Q4_K_M`: do not use as a Lemonade API/vision model for
  now. It repeatedly failed to load, including after a fresh Lemonade download
  from `unsloth/gemma-4-12b-it-GGUF`.
- `gemma-4-12b-it-text-Q4_K_M`: text-only fallback is usable, but it is not a
  preferred daily default because it is slower and did not beat the recommended
  choices.
- `Qwen3.5-27B-GGUF:Q4_0`: keep only for comparison or special curiosity. It is
  slow on this hardware and not a routine default.
- `gemma-4-E4B-it-OBLITERATED-Q4_K_M`: uncensored finetune; not a default
  recommendation for normal work.

## Important Caveats

- Local `coding` results are not the same thing as full SWE-bench. Bounded
  SWE-bench Verified and Verified Mini runs were attempted with Qwen3 Coder and
  scored 0/1, so full SWE-bench ranking remains future work.
- Local `agent_workflow` is not official tau-bench. Official tau-bench was run
  only as a bounded check.
- Local `tool_reliability` is not official BFCL, though official BFCL-style
  bounded imports were added.
- Safety was not separately benchmarked. Treat safety as a prompt, policy, and
  tool-permission issue until a dedicated safety eval exists.

For detailed evidence, see:

- `results/summary/recommended_model_matrix_daily_20260627.md`
- `results/summary/canonical_remaining_status_20260627.md`
- `docs/benchmark_ecosystem.md`
