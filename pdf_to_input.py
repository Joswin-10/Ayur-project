# pdf_to_input.py
# ─────────────────────────────────────────────────────────────────────────────
# Converts a Sanskrit lexical PDF (Amarakosha, Nighantu, etc.)
# into data/input.txt which main.py reads.
#
# Usage:
#   python pdf_to_input.py --pdf amarakosha.pdf
#   python pdf_to_input.py --pdf nighantu.pdf --output data/input.txt
#
# What it does:
#   1. Extracts text page by page using pdfplumber
#   2. Cleans noise (page numbers, headers, broken words)
#   3. Detects and preserves the three input formats:
#        = separated synonyms  → kept as-is  (Amarakosha style)
#        term : description    → kept as-is  (Nighantu style)
#        plain terms           → kept as-is  (term lists)
#   4. Filters lines with no Ayurveda content
#   5. Writes clean data/input.txt ready for parser.py
# ─────────────────────────────────────────────────────────────────────────────

import re
import os
import argparse
import pdfplumber

from ocr_extractor import check_tesseract, extract_page_text

# ── Lines containing these keywords are likely Ayurveda content ───────────────
# Used to keep relevant lines when the PDF has mixed content.
AYURVEDA_KEYWORDS = {
    # Cognitive
    "medha", "smriti", "buddhi", "dhi", "prajna", "manas", "chitta",
    "mati", "dhriti", "viveka", "jnana",
    # Rasayana
    "rasayana", "ojas", "ayushya", "balya", "jeevaniya", "vayasthapana",
    "pushtikara", "ojovardhana",
    # Herbs
    "brahmi", "shankhapushpi", "mandukaparni", "guduchi", "yashtimadhu",
    "vacha", "ashwagandha", "bacopa", "centella", "tinospora",
    # Properties
    "rasa", "guna", "virya", "vipaka", "prabhava", "kalpana", "dravya",
    # Doshas
    "vata", "pitta", "kapha",
    # General Ayurveda markers
    "ayurveda", "medhya", "dhatu", "agni", "prana",
}

# ── Noise patterns to remove ──────────────────────────────────────────────────
NOISE_PATTERNS = [
    r"^\s*\d+\s*$",                    # page numbers
    r"(p\.\s*\d+.*){2,}",             # TOC entries
    r"\.{4,}",                         # dotted leaders
    r"^(chapter|section|index|copyright|isbn|publisher|printed)",
    r"^\s*[-–—]+\s*$",                # horizontal rules
]

# ── Synonym separator patterns (Amarakosha style) ─────────────────────────────
SYNONYM_LINE = re.compile(r"\w+\s*[=|/]\s*\w+")

# ── Description line (Nighantu style) ─────────────────────────────────────────
DESC_LINE = re.compile(r"^\w[\w\s]+\s*:\s*.{10,}")


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Extract raw text from PDF
# ──────────────────────────────────────────────────────────────────────────────

def extract_text(pdf_path: str, use_ocr: bool = False) -> list[str]:
    """Returns list of text lines from all pages."""
    all_lines = []

    if use_ocr:
        ok, msg = check_tesseract()
        if not ok:
            raise RuntimeError(msg)
        print(f"  OCR enabled — {msg}")

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"  PDF: {total} pages")
        ocr_count = 0
        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            text = extract_page_text(page, page_num, pdf_path, use_ocr)
            if not text:
                if not use_ocr:
                    print(f"  ⚠ Page {page_num}: no text (scanned image?) — use --ocr")
                continue
            if use_ocr and not (page.extract_text() or "").strip():
                ocr_count += 1
            all_lines.extend(text.split("\n"))
        if use_ocr:
            print(f"  OCR'd {ocr_count} page(s)")

    print(f"  Extracted {len(all_lines)} raw lines")
    return all_lines


# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Clean individual lines
# ──────────────────────────────────────────────────────────────────────────────

def clean_line(line: str) -> str:
    # Fix hyphenated line breaks
    line = re.sub(r"(\w)-\s+(\w)", r"\1\2", line)
    # Normalize whitespace
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()

def is_noise(line: str) -> bool:
    if len(line) < 3:
        return True
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, line, re.IGNORECASE):
            return True
    return False

def has_ayurveda_content(line: str) -> bool:
    """Keep line if it contains any known Ayurveda keyword."""
    lower = line.lower()
    return any(kw in lower for kw in AYURVEDA_KEYWORDS)

def is_synonym_group(line: str) -> bool:
    return bool(SYNONYM_LINE.search(line))

def is_desc_line(line: str) -> bool:
    return bool(DESC_LINE.match(line))


# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Merge continuation lines
# ──────────────────────────────────────────────────────────────────────────────

def merge_continuations(lines: list[str]) -> list[str]:
    """
    Some PDFs break long lines across two rows.
    If a line doesn't end with punctuation and the next starts lowercase,
    merge them.
    """
    merged = []
    i = 0
    while i < len(lines):
        line = lines[i]
        while (i + 1 < len(lines)
               and not re.search(r"[.;=|/:]$", line)
               and len(lines[i+1]) > 0
               and lines[i+1][0].islower()):
            i += 1
            line = line + " " + lines[i]
        merged.append(line)
        i += 1
    return merged


# ──────────────────────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────────────────────

def convert(pdf_path: str, output_path: str = "data/input.txt",
            strict_filter: bool = True, use_ocr: bool = False):
    """
    strict_filter=True  → only keep lines with known Ayurveda keywords
    strict_filter=False → keep all non-noise lines (use for dense lexical PDFs
                          where every line is relevant)
    """
    print(f"\nConverting: {pdf_path}\n")

    # 1. Extract
    raw_lines = extract_text(pdf_path, use_ocr=use_ocr)

    # 2. Clean
    cleaned = [clean_line(l) for l in raw_lines]

    # 3. Merge continuations
    cleaned = merge_continuations(cleaned)

    # 4. Filter
    kept    = []
    skipped = 0
    for line in cleaned:
        if is_noise(line):
            skipped += 1
            continue
        if strict_filter and not has_ayurveda_content(line):
            skipped += 1
            continue
        kept.append(line)

    print(f"  Kept    : {len(kept)} lines")
    print(f"  Skipped : {skipped} lines (noise or no Ayurveda content)")

    # 5. Group by detected format (add blank lines between format changes
    #    so the output is readable)
    output_lines = [
        f"# Converted from: {pdf_path}",
        f"# Lines: {len(kept)}",
        "",
    ]

    prev_fmt = None
    for line in kept:
        if is_synonym_group(line):
            fmt = "synonym"
        elif is_desc_line(line):
            fmt = "desc"
        else:
            fmt = "term"

        # Add blank line when format changes for readability
        if prev_fmt and fmt != prev_fmt:
            output_lines.append("")
        output_lines.append(line)
        prev_fmt = fmt

    # 6. Write
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\nDone → {output_path}")
    print(f"  Open this file and review before running main.py")
    print(f"\nNext step:")
    print(f"  python main.py --input {output_path} --neo4j --clear")


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert Amarakosha/Nighantu PDF to input.txt"
    )
    parser.add_argument("--pdf",    required=True,
                        help="Path to the Sanskrit lexical PDF")
    parser.add_argument("--output", default="data/input.txt",
                        help="Output path (default: data/input.txt)")
    parser.add_argument("--no-filter", action="store_true",
                        help="Keep all lines, skip Ayurveda keyword filter")
    parser.add_argument("--ocr", action="store_true",
                        help="OCR scanned/image PDF pages (requires Tesseract)")
    args = parser.parse_args()

    try:
        convert(
            pdf_path=args.pdf,
            output_path=args.output,
            strict_filter=not args.no_filter,
            use_ocr=args.ocr,
        )
    except RuntimeError as exc:
        print(f"\nError: {exc}")