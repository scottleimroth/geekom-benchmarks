"""Scaffolding for OPTIONAL standard-VLM-dataset samples.

DEFAULT BEHAVIOR: nothing is downloaded. Synthetic fixtures are the default and
the only thing prepare_vision_assets.py creates unless a future opt-in flag is
added. This module only declares *where* small samples could come from and the
provenance rules they must satisfy.

POLICY (enforced by convention, see docs/vision_benchmarks.md):
  - Never bulk-download a dataset.
  - Never add a sample to the manifest without recording: dataset name, split,
    sample id, source URL, and license. If any of those is unclear -> SKIP and
    document the reason. Do not guess a license.
  - Respect each dataset's license/terms; many forbid redistribution, so samples
    may need to be fetched by the user locally rather than vendored into the repo.

Each registry entry is descriptive metadata only; `available=False` means we have
NOT verified a clean, license-compatible path to small samples yet.
"""
from __future__ import annotations

from typing import Any, Dict, List

# name -> descriptor. URLs are the canonical project/dataset pages.
STANDARD_DATASETS: List[Dict[str, Any]] = [
    {
        "name": "TextVQA",
        "task": "OCR / text-in-image VQA",
        "url": "https://textvqa.org/",
        "hf": "facebook/textvqa",
        "license": "CC BY 4.0 (verify per release)",
        "notes": "Reading text in natural images to answer questions.",
        "available": False,
        "skip_reason": "license/redistribution not yet verified for vendoring samples",
    },
    {
        "name": "DocVQA",
        "task": "Document VQA",
        "url": "https://www.docvqa.org/",
        "hf": "lmms-lab/DocVQA",
        "license": "research-use; registration may be required",
        "notes": "QA over scanned documents/forms.",
        "available": False,
        "skip_reason": "access/registration + redistribution terms unverified",
    },
    {
        "name": "ChartQA",
        "task": "Chart reasoning QA",
        "url": "https://github.com/vis-nlp/ChartQA",
        "hf": "HuggingFaceM4/ChartQA",
        "license": "GPL-3.0 / per-repo (verify)",
        "notes": "Questions over bar/line/pie charts.",
        "available": False,
        "skip_reason": "license verification pending",
    },
    {
        "name": "OCRBench",
        "task": "OCR-oriented evaluation",
        "url": "https://github.com/Yuliang-Liu/MultimodalOCR",
        "hf": "echo840/OCRBench",
        "license": "per-repo (verify)",
        "notes": "Aggregated OCR capability benchmark.",
        "available": False,
        "skip_reason": "license verification pending",
    },
    {
        "name": "ScreenSpot",
        "task": "GUI/screenshot grounding",
        "url": "https://github.com/njucckevin/SeeClick",
        "hf": "rootsautomation/ScreenSpot",
        "license": "per-repo (verify); ScreenSpot-Pro separate terms",
        "notes": "Locate UI elements from instructions (and ScreenSpot-Pro).",
        "available": False,
        "skip_reason": "license verification pending",
    },
    {
        "name": "MMMU",
        "task": "Multimodal reasoning (college-level)",
        "url": "https://mmmu-benchmark.github.io/",
        "hf": "MMMU/MMMU",
        "license": "Apache-2.0 / per-subject (verify)",
        "notes": "Broad multi-discipline multimodal reasoning.",
        "available": False,
        "skip_reason": "size + per-subject license verification pending",
    },
    {
        "name": "MathVista",
        "task": "Multimodal math reasoning",
        "url": "https://mathvista.github.io/",
        "hf": "AI4Math/MathVista",
        "license": "CC BY-SA 4.0 (verify)",
        "notes": "Visual math problem solving.",
        "available": False,
        "skip_reason": "license verification pending",
    },
]


def list_targets() -> List[Dict[str, Any]]:
    return list(STANDARD_DATASETS)


def fetch_samples(*args: Any, **kwargs: Any):
    """Intentionally not implemented — default is synthetic-only.

    A future implementation must: (1) take an explicit opt-in flag + dataset name
    + sample count, (2) download ONLY that many samples, (3) write each into the
    manifest with source_type='standard' and full provenance (dataset, split,
    sample id, url, license), (4) skip + log if license/access is unclear.
    """
    raise NotImplementedError(
        "Standard-dataset sampling is opt-in and not implemented. Default is "
        "synthetic fixtures only. See docs/vision_benchmarks.md for the policy."
    )
