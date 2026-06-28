"""Deterministic, locally-generated vision benchmark assets.

The whole point: you should never have to go hunting for screenshots. This
package generates a small, reproducible set of synthetic images (OCR text, a
fake invoice, a chart, a UI mock, and a spot-the-difference pair) plus a manifest
of questions with exact expected answers, so the vision benchmark has known
ground truth and no external/licensing dependencies.

Standard public-dataset samples (TextVQA/DocVQA/ChartQA/...) are scaffolded in
`standard.py` but NOT downloaded by default — see docs/vision_benchmarks.md.
"""

from . import synthetic, standard, scoring, common

__all__ = ["synthetic", "standard", "scoring", "common"]
