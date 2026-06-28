# Recommended Model Matrix (Daily Reference)

Date: 2026-06-28
Repo: `<repo-root>`
Source: local full-suite/tournament runs plus canonical imports through MLPerf Client, EvalScope, BFCL, tau-bench, SWE-bench, and OpenCompass.

| Use case | Recommended model | Confidence | Why |
| --- | --- | --- | --- |
| Daily chat / fast general use | `gemma-4-E2B-it` | High | Fastest stable daily model in local speed and broad local checks; good structured/vision/long-context behavior for its size. |
| Tooling / function calls | `Qwen3-30B-A3B` or `Nemotron-Cascade-2-30B-A3B` | High | Both are strong locally; official BFCL-v4 bounded non-live import scored both at 0.9. Use strict staged orchestration for important actions. |
| Agent workflow | `Nemotron-Cascade-2-30B-A3B` | Medium | Redesigned local agent workflow v2 sanity passed 3/3. Official tau-bench bounded retail ran separately and scored 0/1, so keep agent recommendations conservative. |
| Coding default | `Qwen3-Coder-30B-A3B` | High | Fair dedicated coding tournament winner: tied `gpt-oss-20b` at 4/4 but completed much faster. SWE-bench Verified and Verified Mini bounded runs were attempted with this model and scored 0/1 on each. |
| Coding secondary | `gpt-oss-20b` | Medium | Also passed 4/4 in the fair coding tournament, but was materially slower than Qwen3-Coder. |
| Vision / OCR | `Qwen3-VL-8B` | High | Purpose-built vision model; led the completed local vision set. `gemma-4-E2B-it` and `olmOCR-2-7B` remain useful compact/OCR alternatives. |
| Long context / careful reasoning | `Nemotron-Cascade-2-30B-A3B` or `Qwen3.6-35B-A3B` | Medium | Strong local long-context behavior; Nemotron is the more conservative pick where tools/workflow matter. |
| Safety | Not separately measured | Low | No standalone safety benchmark was run. Treat safety as prompt/tooling policy until a dedicated safety eval is added. |

Operational notes:

- `gemma-4-12b-it-text-Q4_K_M` is usable for text/API categories.
- The vision-capable Gemma 12B Lemonade entry remains blocked by `model_load_error` even after explicit main/mmproj checkpoint repair.
- Local `coding` is not SWE-bench; local `agent_workflow` is not tau-bench; local `tool_reliability` is not official BFCL.
- OpenCompass ARC-Easy dev completed for all downloaded Lemonade model IDs. It is one general MCQ benchmark, not a replacement for the local domain-specific categories.
- Top OpenCompass ARC-Easy dev scores were `olmOCR-2-7B` 91.01, `Qwen3-VL-8B` 76.90, `Gemma-4-E2B-it` 27.87, `gemma-4-E4B-OBLITERATED` 27.34, and `Qwen3.6-35B-A3B` 24.87. Treat the OCR/VL showing as ARC-Easy-specific rather than a broad daily-chat recommendation by itself.
- vLLM/RAGAS/DeepEval are not applicable without the required server/app fixtures.
