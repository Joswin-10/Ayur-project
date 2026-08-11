# ocr_extractor.py
# ─────────────────────────────────────────────────────────────────────────────
# OCR fallback for scanned/image-only PDF pages.
# Uses pdfplumber page rendering + Tesseract (Devanagari/Sanskrit).
# Caches per-page text under output/ocr_cache/ so re-runs are fast.
# ─────────────────────────────────────────────────────────────────────────────

import hashlib
import os
from pathlib import Path

from config import OCR_LANG, OCR_DPI, OCR_CACHE_DIR, TESSERACT_CMD

try:
    import pytesseract
except ImportError:
    pytesseract = None  # type: ignore


def _resolve_tesseract_cmd() -> str:
    cmd = TESSERACT_CMD.strip()
    if cmd:
        if os.path.isdir(cmd):
            cmd = os.path.join(cmd, "tesseract.exe")
        return cmd
    for path in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.isfile(path):
            return path
    return ""


def _configure_tesseract() -> None:
    if pytesseract is None:
        return
    cmd = _resolve_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def check_tesseract() -> tuple[bool, str]:
    """Verify pytesseract and Tesseract binary + language packs."""
    if pytesseract is None:
        import sys
        return False, (
            "pytesseract not found in this Python environment.\n"
            f"  Python: {sys.executable}\n"
            "  Fix: python -m pip install pytesseract Pillow\n"
            "  (use the same python/venv you run main.py with — not plain pip)"
        )

    _configure_tesseract()
    try:
        version = pytesseract.get_tesseract_version()
    except Exception as exc:
        return False, (
            "Tesseract OCR not found. Install it and add to PATH, or set TESSERACT_CMD.\n"
            "  Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            f"  Detail: {exc}"
        )

    try:
        langs = set(pytesseract.get_languages())
    except Exception as exc:
        return False, f"Could not list Tesseract languages: {exc}"

    needed = {"san", "hin", "eng"}
    if not (needed & langs):
        return False, (
            f"Tesseract {version} found but no Sanskrit/Devanagari pack.\n"
            "  Re-run the Tesseract installer and select 'Sanskrit' and/or 'Hindi'.\n"
            f"  Installed languages: {', '.join(sorted(langs))}"
        )

    devanagari = "san" if "san" in langs else "hin"
    return True, f"Tesseract {version}, using {devanagari}+eng (langs: {', '.join(sorted(langs))})"


def _cache_path(pdf_path: str, page_num: int) -> Path:
    stem = Path(pdf_path).stem
    digest = hashlib.md5(os.path.abspath(pdf_path).encode()).hexdigest()[:8]
    return Path(OCR_CACHE_DIR) / f"{stem}_{digest}" / f"page_{page_num:04d}.txt"


def _run_tesseract(pil_image) -> str:
    _configure_tesseract()
    primary = OCR_LANG
    fallbacks = [primary, "san+eng", "hin+eng", "san", "hin", "eng"]
    seen: set[str] = set()
    last_err: Exception | None = None

    for lang in fallbacks:
        if lang in seen:
            continue
        seen.add(lang)
        try:
            return pytesseract.image_to_string(pil_image, lang=lang)
        except Exception as exc:
            last_err = exc
            continue

    raise RuntimeError(
        f"Tesseract OCR failed for all language packs tried. Last error: {last_err}"
    )


def ocr_pdf_page(page, pdf_path: str, page_num: int, use_cache: bool = True) -> str:
    """Render a pdfplumber page and OCR it. Returns extracted text."""
    cache = _cache_path(pdf_path, page_num)
    if use_cache and cache.is_file():
        return cache.read_text(encoding="utf-8")

    pil_image = page.to_image(resolution=OCR_DPI).original
    text = _run_tesseract(pil_image)

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def extract_page_text(page, page_num: int, pdf_path: str, use_ocr: bool) -> str | None:
    """Try embedded text first; fall back to OCR when enabled."""
    text = page.extract_text()
    if text and text.strip():
        return text
    if not use_ocr:
        return None
    return ocr_pdf_page(page, pdf_path, page_num)
