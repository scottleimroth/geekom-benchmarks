"""Shared helpers for synthetic image generation (Pillow) + manifest items.

Determinism is the contract: no timestamps, no randomness, fixed fonts/sizes, so
re-running prepare_vision_assets.py yields byte-stable-enough images and a stable
manifest. Fonts come from matplotlib's bundled DejaVuSans (always present since
matplotlib is a dependency of the generators).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

_FONT_CACHE: Dict[Tuple[str, int], Any] = {}


def _font_path(bold: bool = False) -> Optional[str]:
    try:
        import matplotlib.font_manager as fm
        return fm.findfont("DejaVu Sans:bold" if bold else "DejaVu Sans")
    except Exception:
        return None


def load_font(size: int, bold: bool = False):
    key = (("bold" if bold else "regular"), size)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    path = _font_path(bold)
    try:
        font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def new_canvas(width: int, height: int, color: str = "white") -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), color)
    return img, ImageDraw.Draw(img)


def text(draw: ImageDraw.ImageDraw, xy, s: str, size: int = 22, fill: str = "black", bold: bool = False) -> None:
    draw.text(xy, s, font=load_font(size, bold=bold), fill=fill)


def manifest_item(
    *,
    asset_id: str,
    file_path: str,
    asset_type: str,
    question: str,
    expected_answer: str,
    scoring_method: str = "substring",
    accepted_answer_patterns: Optional[List[str]] = None,
    notes: str = "",
    source_type: str = "synthetic",
    license: str = "generated_by_repo",
    file_paths: Optional[List[str]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one manifest entry (one question against one or more images)."""
    item: Dict[str, Any] = {
        "asset_id": asset_id,
        "file_path": file_path,
        "asset_type": asset_type,
        "source_type": source_type,
        "license": license,
        "question": question,
        "expected_answer": expected_answer,
        "accepted_answer_patterns": accepted_answer_patterns or [],
        "scoring_method": scoring_method,
        "notes": notes,
    }
    if file_paths:
        item["file_paths"] = file_paths
    if extra:
        item["extra"] = extra
    return item
