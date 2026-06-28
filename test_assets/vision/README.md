# Vision benchmark assets

This directory is **generated** by `scripts/prepare_vision_assets.py`. Do not hand-
curate it; re-run the script to recreate it deterministically.

## synthetic/  (the default test set)
Locally generated images with KNOWN ground truth — no external data, no licensing
concerns (`license: generated_by_repo`). Covers OCR text, a fake invoice, a bar
chart, a settings-UI mock, and a spot-the-difference pair. Questions and exact
expected answers live in `manifest.json`.

## standard_samples/  (optional, opt-in, NOT downloaded by default)
Reserved for small samples from public VLM datasets. **Policy:** never bulk-
download; never add a sample without recording dataset name, split, sample id,
source URL, and license in the manifest; if licensing/access is unclear, SKIP and
document why. See `docs/vision_benchmarks.md`.

Target datasets (descriptive only — see docs/vision_benchmarks.md for details):
- TextVQA (OCR/text-in-image QA)
- DocVQA (document QA)
- ChartQA (chart reasoning)
- OCRBench (OCR-oriented evaluation)
- ScreenSpot / ScreenSpot-Pro (GUI/screenshot grounding)
- MMMU / MathVista (multimodal reasoning)

## manifest.json
A list of `items`, each one question against one (or two) image(s), with:
`asset_id, file_path[, file_paths], asset_type, source_type, license, question,
expected_answer, accepted_answer_patterns, scoring_method, notes`.
The vision runner (`scripts/run_vision_tasks.py`) reads this file.
