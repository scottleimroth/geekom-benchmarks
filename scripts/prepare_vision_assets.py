#!/usr/bin/env python3
"""Generate the deterministic synthetic vision test set + manifest.

Creates:
  test_assets/vision/
    manifest.json        - questions + exact expected answers + scoring methods
    synthetic/           - generated PNGs (OCR, invoice, chart, UI, compare pair)
    standard_samples/    - empty placeholder for OPTIONAL standard-dataset samples
    README.md            - what's here + dataset target documentation

Synthetic fixtures only by default — nothing is downloaded. Re-running is
deterministic (no timestamps/randomness), so the manifest + images are stable.

Usage:  python scripts/prepare_vision_assets.py
"""
import _bootstrap  # noqa: F401
import argparse

from geekom_benchmarks.utils.io import paths, write_json_atomic
from geekom_benchmarks.vision_assets import synthetic, standard

README = """# Vision benchmark assets

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
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="regenerate even if assets exist")
    args = ap.parse_args()

    vision_dir = paths()["test_assets"] / "vision"
    (vision_dir / "synthetic").mkdir(parents=True, exist_ok=True)
    (vision_dir / "standard_samples").mkdir(parents=True, exist_ok=True)

    print(f"Generating synthetic vision fixtures in {vision_dir / 'synthetic'} ...")
    items = synthetic.generate_all(vision_dir)

    # one image file per unique file_path referenced
    files = sorted({fp for it in items for fp in ([it["file_path"]] + it.get("file_paths", []))})
    manifest = {
        "schema_version": "1.0",
        "generator": "scripts/prepare_vision_assets.py",
        "default_source": "synthetic",
        "synthetic_image_count": len(files),
        "question_count": len(items),
        "items": items,
        "standard_targets": standard.list_targets(),
        "policy": "synthetic-only by default; standard samples require explicit opt-in "
                  "with full provenance (name/split/id/url/license) or are skipped.",
    }
    manifest_path = vision_dir / "manifest.json"
    write_json_atomic(manifest_path, manifest)
    (vision_dir / "README.md").write_text(README, encoding="utf-8")

    print(f"  images:    {len(files)}")
    for fp in files:
        print(f"    - {fp}")
    print(f"  questions: {len(items)}")
    print(f"  manifest:  {manifest_path}")
    print(f"  standard targets documented: {len(manifest['standard_targets'])} (none downloaded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
