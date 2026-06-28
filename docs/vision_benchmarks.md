# Vision benchmarks

The vision benchmark answers: *can the configured local VLM read text, parse a
document, reason over a chart, ground a UI, and spot a controlled difference?* —
using a **deterministic, locally-generated** test set so there's known ground
truth and zero external/licensing dependencies.

## Default: synthetic fixtures (no downloads)

`python scripts/prepare_vision_assets.py` generates everything under
`test_assets/vision/synthetic/` and writes `test_assets/vision/manifest.json`:

| asset_id | type | what it tests | example question → expected |
|---|---|---|---|
| `ocr_text` | ocr_text | OCR of printed text | "order total?" → `$47.83`; "reference?" → `AX-2047` |
| `invoice` | document | document field extraction | invoice #/date/customer/total |
| `bar_chart` | chart | chart value reading + reasoning | "value of bar B?" → `19` (A=12,B=19,C=7) |
| `ui_settings` | ui | GUI grounding | "list the buttons" → Save/Cancel/Apply |
| `compare_*` | comparison | spot the controlled difference | status ONLINE/green → OFFLINE/red |

All synthetic assets carry `source_type: synthetic`, `license: generated_by_repo`.
Scoring uses per-item `scoring_method` (`regex_any`, `numeric`, `contains_all`,
`substring`) against `expected_answer` / `accepted_answer_patterns`.

## How the runner uses it

`scripts/run_vision_tasks.py`:
1. reads `test_assets/vision/manifest.json`,
2. sends image(s) to the selected vision model **only** via the OpenAI-compatible
   `image_url` (base64 data-URL) content — i.e. only if the endpoint accepts image
   input,
3. scores the answer against the manifest,
4. writes unified result-schema rows (`benchmark_category="vision"`),
5. writes **SKIPPED** rows (with a reason) if the model isn't vision-capable, the
   asset is missing, or the endpoint rejects image input — it never fakes a pass.

## Optional: standard public datasets (opt-in, not downloaded)

For broader, comparable coverage you may later add **small** samples from public
VLM benchmarks. These are scaffolded in `src/geekom_benchmarks/vision_assets/standard.py`
but **nothing is downloaded by default**.

| Dataset | Use | Page |
|---|---|---|
| **TextVQA** | OCR / text-in-image QA | https://textvqa.org/ |
| **DocVQA** | document QA | https://www.docvqa.org/ |
| **ChartQA** | chart reasoning | https://github.com/vis-nlp/ChartQA |
| **OCRBench** | OCR-oriented evaluation | https://github.com/Yuliang-Liu/MultimodalOCR |
| **ScreenSpot / ScreenSpot-Pro** | GUI/screenshot grounding | https://github.com/njucckevin/SeeClick |
| **MMMU** | multimodal reasoning | https://mmmu-benchmark.github.io/ |
| **MathVista** | multimodal math reasoning | https://mathvista.github.io/ |

### Policy (must follow)
- **Do not bulk-download.** Take only the few samples you need.
- **Provenance is mandatory.** Every standard sample added to the manifest must
  record: dataset **name**, **split**, **sample id**, source **URL**, and
  **license**. No exceptions.
- **If license or access is unclear, SKIP it and document the reason.** Do not
  guess a license. Many of these datasets restrict redistribution — prefer having
  the user fetch samples locally over vendoring them into the repo.
- The default, and the only thing CI/automation should rely on, is the synthetic
  set.

## Notes & limitations
- Synthetic images are intentionally simple/clean; they test capability presence,
  not robustness to noisy real-world inputs. Use the standard datasets above for
  that, under the policy.
- Whether Lemonade actually accepts image input depends on the loaded model
  (needs an `mmproj`/vision projector). If it doesn't, the runner records SKIPPED
  with the endpoint's error — that's a real signal, not a failure to hide.
