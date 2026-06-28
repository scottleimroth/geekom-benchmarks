"""Deterministic synthetic vision fixtures + their manifest items.

Five fixtures, each with known ground truth:
  1. ocr_text   - clear receipt-style text (OCR)
  2. invoice    - a simple invoice/form (document QA)
  3. bar_chart  - matplotlib bar chart A=12,B=19,C=7 (chart reasoning)
  4. ui_mock    - a clean settings window with Save/Cancel/Apply (GUI grounding)
  5. compare    - two near-identical images with ONE controlled difference

generate_all(vision_dir) writes PNGs under <vision_dir>/synthetic/ and returns
the list of manifest items (file paths are relative to vision_dir).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .common import manifest_item, new_canvas, text


def _gen_ocr_text(syn: Path) -> List[Dict[str, Any]]:
    name = "ocr_text.png"
    img, d = new_canvas(640, 260, "white")
    d.rectangle([10, 10, 629, 249], outline="#cccccc", width=2)
    text(d, (40, 40), "RECEIPT", size=28, bold=True)
    text(d, (40, 100), "Order total: $47.83", size=30)
    text(d, (40, 150), "Reference: AX-2047", size=30)
    text(d, (40, 200), "Thank you for your purchase", size=18, fill="#666666")
    img.save(syn / name)
    fp = f"synthetic/{name}"
    return [
        manifest_item(asset_id="ocr_text", file_path=fp, asset_type="ocr_text",
                      question="What is the order total shown in the image?",
                      expected_answer="$47.83", scoring_method="regex_any",
                      accepted_answer_patterns=[r"\$?\s?47\.83"],
                      notes="OCR of a clear printed amount."),
        manifest_item(asset_id="ocr_text", file_path=fp, asset_type="ocr_text",
                      question="What is the reference code shown in the image?",
                      expected_answer="AX-2047", scoring_method="regex_any",
                      accepted_answer_patterns=[r"AX[\s-]?2047"],
                      notes="OCR of an alphanumeric code."),
    ]


def _gen_invoice(syn: Path) -> List[Dict[str, Any]]:
    name = "invoice.png"
    img, d = new_canvas(680, 460, "white")
    d.rectangle([0, 0, 679, 70], fill="#1f3b57")
    text(d, (30, 20), "INVOICE", size=34, fill="white", bold=True)
    rows = [
        ("Invoice #:", "INV-100245"),
        ("Date:", "2026-03-14"),
        ("Customer:", "Acme Robotics Ltd"),
        ("Subtotal:", "$1,180.00"),
        ("Tax (8.85%):", "$104.50"),
        ("Total:", "$1,284.50"),
    ]
    y = 120
    for label, val in rows:
        text(d, (40, y), label, size=24, fill="#333333")
        text(d, (330, y), val, size=24, bold=(label == "Total:"))
        y += 50
    img.save(syn / name)
    fp = f"synthetic/{name}"
    return [
        manifest_item(asset_id="invoice", file_path=fp, asset_type="document",
                      question="What is the invoice number?",
                      expected_answer="INV-100245", scoring_method="regex_any",
                      accepted_answer_patterns=[r"INV[\s-]?100245"], notes="Document field extraction."),
        manifest_item(asset_id="invoice", file_path=fp, asset_type="document",
                      question="What is the invoice date?",
                      expected_answer="2026-03-14", scoring_method="regex_any",
                      accepted_answer_patterns=[r"2026[-/]03[-/]14", r"March\s+14,?\s+2026"],
                      notes="Accepts ISO or written date."),
        manifest_item(asset_id="invoice", file_path=fp, asset_type="document",
                      question="What is the customer name?",
                      expected_answer="Acme Robotics Ltd", scoring_method="regex_any",
                      accepted_answer_patterns=[r"Acme\s+Robotics"], notes="Customer field."),
        manifest_item(asset_id="invoice", file_path=fp, asset_type="document",
                      question="What is the total amount due?",
                      expected_answer="$1,284.50", scoring_method="regex_any",
                      accepted_answer_patterns=[r"\$?\s?1,?284\.50"], notes="Total field (not subtotal)."),
    ]


def _gen_bar_chart(syn: Path) -> List[Dict[str, Any]]:
    name = "bar_chart.png"
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cats = ["A", "B", "C"]
    vals = [12, 19, 7]
    fig, ax = plt.subplots(figsize=(5.2, 3.6), dpi=120)
    bars = ax.bar(cats, vals, color=["#4c78a8", "#f58518", "#54a24b"])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.4, str(v), ha="center", fontsize=12)
    ax.set_title("Widgets by Category")
    ax.set_ylabel("Count")
    ax.set_ylim(0, 22)
    fig.tight_layout()
    fig.savefig(syn / name)
    plt.close(fig)
    fp = f"synthetic/{name}"
    return [
        manifest_item(asset_id="bar_chart", file_path=fp, asset_type="chart",
                      question="What is the value of bar B?",
                      expected_answer="19", scoring_method="numeric",
                      accepted_answer_patterns=[r"\b19\b"], notes="Labeled bar value."),
        manifest_item(asset_id="bar_chart", file_path=fp, asset_type="chart",
                      question="Which category has the highest value? Answer with the single letter.",
                      expected_answer="B", scoring_method="regex_any",
                      accepted_answer_patterns=[r"\bB\b"], notes="Argmax over A=12,B=19,C=7."),
        manifest_item(asset_id="bar_chart", file_path=fp, asset_type="chart",
                      question="How many bars are in the chart? Answer with a single integer.",
                      expected_answer="3", scoring_method="numeric",
                      accepted_answer_patterns=[r"\b3\b"], notes="Three categories A,B,C."),
    ]


def _gen_ui_mock(syn: Path) -> List[Dict[str, Any]]:
    name = "ui_settings.png"
    img, d = new_canvas(560, 380, "#f0f0f0")
    # title bar
    d.rectangle([0, 0, 559, 44], fill="#2d2d2d")
    text(d, (16, 10), "Settings", size=22, fill="white", bold=True)
    # body rows
    text(d, (30, 80), "Enable notifications", size=20)
    d.rectangle([400, 78, 470, 104], outline="#2d2d2d", width=2)
    text(d, (414, 80), "ON", size=18)
    text(d, (30, 140), "Dark mode", size=20)
    d.rectangle([400, 138, 470, 164], outline="#2d2d2d", width=2)
    text(d, (410, 140), "OFF", size=18)
    text(d, (30, 200), "Auto-update", size=20)
    # buttons
    buttons = [("Save", "#4c78a8", 70), ("Cancel", "#9e9e9e", 230), ("Apply", "#54a24b", 390)]
    for label, color, x in buttons:
        d.rectangle([x, 300, x + 130, 344], fill=color)
        text(d, (x + 30, 310), label, size=20, fill="white", bold=True)
    img.save(syn / name)
    fp = f"synthetic/{name}"
    return [
        manifest_item(asset_id="ui_settings", file_path=fp, asset_type="ui",
                      question="List the three buttons at the bottom of this window.",
                      expected_answer="Save, Cancel, Apply", scoring_method="contains_all",
                      accepted_answer_patterns=["Save", "Cancel", "Apply"],
                      notes="GUI grounding: all three button labels must appear."),
        manifest_item(asset_id="ui_settings", file_path=fp, asset_type="ui",
                      question="What is the title of this window?",
                      expected_answer="Settings", scoring_method="regex_any",
                      accepted_answer_patterns=[r"\bSettings\b"], notes="Window title."),
        manifest_item(asset_id="ui_settings", file_path=fp, asset_type="ui",
                      question="Which button would discard the changes? Answer with the button label.",
                      expected_answer="Cancel", scoring_method="regex_any",
                      accepted_answer_patterns=[r"\bCancel\b"], notes="Semantic GUI reasoning."),
    ]


def _gen_compare(syn: Path) -> List[Dict[str, Any]]:
    """Two images identical except one controlled difference: the status badge."""
    items: List[Dict[str, Any]] = []
    files = []
    for variant, (label, color) in {"a": ("ONLINE", "#54a24b"), "b": ("OFFLINE", "#d62728")}.items():
        name = f"compare_{variant}.png"
        img, d = new_canvas(420, 260, "white")
        d.rectangle([10, 10, 409, 249], outline="#cccccc", width=2)
        text(d, (30, 30), "Server Dashboard", size=24, bold=True)
        text(d, (30, 90), "Region: us-west-2", size=20, fill="#333333")
        text(d, (30, 130), "Uptime: 124 days", size=20, fill="#333333")
        # the ONLY difference: status badge color + text
        d.ellipse([30, 180, 60, 210], fill=color)
        text(d, (75, 182), f"Status: {label}", size=22, bold=True)
        img.save(syn / name)
        files.append(f"synthetic/{name}")
    items.append(
        manifest_item(asset_id="compare_status", file_path=files[0], file_paths=files,
                      asset_type="comparison",
                      question=("These two images are identical except for one element. "
                                "What is the difference between the first and second image?"),
                      expected_answer="The status changed from ONLINE (green) to OFFLINE (red).",
                      scoring_method="regex_any",
                      accepted_answer_patterns=[r"offline", r"\bred\b", r"status", r"colou?r"],
                      notes="Controlled diff: status badge ONLINE/green -> OFFLINE/red; "
                            "everything else identical. Passes if the changed element is identified.")
    )
    return items


_GENERATORS = [_gen_ocr_text, _gen_invoice, _gen_bar_chart, _gen_ui_mock, _gen_compare]


def generate_all(vision_dir: Path) -> List[Dict[str, Any]]:
    syn = vision_dir / "synthetic"
    syn.mkdir(parents=True, exist_ok=True)
    items: List[Dict[str, Any]] = []
    for gen in _GENERATORS:
        items.extend(gen(syn))
    return items
