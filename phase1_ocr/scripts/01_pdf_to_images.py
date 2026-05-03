#!/usr/bin/env python3
"""Convert input PDF to per-page PNG at 300 DPI for OCR."""
from pathlib import Path
from pdf2image import convert_from_path

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "input" / "血壓原始檔.pdf"
OUT = ROOT / "pages"
OUT.mkdir(parents=True, exist_ok=True)

print(f"Converting {PDF.name} at 300 DPI...")
images = convert_from_path(str(PDF), dpi=300)
print(f"Total pages: {len(images)}")

for i, img in enumerate(images, 1):
    path = OUT / f"page_{i:02d}.png"
    img.save(path, "PNG")
    print(f"  saved {path.name} ({img.size[0]}x{img.size[1]})")

print(f"Done. Output: {OUT}")
