# pdf_parser.py
# ─────────────────────────────────────────────────────────────────────────────
# Reads Amarakosha PDF with strict preprocessing.
# Removes: headers, footers, translator notes, preface, bibliography,
#          introduction, references, OCR artifacts, English paragraphs.
# Keeps:   Sanskrit lexical content only.
# ─────────────────────────────────────────────────────────────────────────────

import re
import os
from dataclasses import dataclass, field

import pdfplumber

from config import (
    ALL_RELEVANT_KEYWORDS, MEDHYA_KEYWORDS, RASAYANA_KEYWORDS, HERB_KEYWORDS,
    HERB_DEVANAGARI_MARKERS, MEDHYA_DEVANAGARI_MARKERS, RASAYANA_DEVANAGARI_MARKERS,
)
from ocr_extractor import check_tesseract, extract_page_text
from validator import (
    validate_concept, validate_pdf_term, DEVANAGARI_RE, is_domain_relevant,
    line_passes_domain_filter, is_english_commentary, has_domain_devanagari_marker,
)

# ──────────────────────────────────────────────────────────────────────────────
# Data structure
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedEntry:
    terms:       list[str]
    synonyms:    list[str]
    description: str
    source_line: str
    format_type: str        # synonym_group | concept_desc | term_list
    page_num:    int  = 0
    domain:      str  = "general"


# ──────────────────────────────────────────────────────────────────────────────
# Section detection — identify and skip non-lexical sections
# ──────────────────────────────────────────────────────────────────────────────

# Page ranges or section titles that indicate non-lexical content to skip
NON_LEXICAL_SECTION_MARKERS = re.compile(
    r"^(preface|introduction|foreword|translator|bibliography|references|"
    r"index|table of contents|acknowledgement|about the|publisher|"
    r"printed|copyright|all rights|isbn|appendix|notes|editorial)",
    re.IGNORECASE
)

# Lines that are clearly non-lexical
NON_LEXICAL_LINE_PATTERNS = [
    r"^\s*\d+\s*$",                            # lone page numbers
    r"^\s*[-–—=*_]+\s*$",                      # separator lines
    r"\|\|\s*\d+[\.\d]*\s*\|\|",              # verse markers ||1.2.3||
    r"^\s*\d+[\.\-]\d+[\.\-]?\d*\s*$",        # standalone verse numbers
    r"(\.{4,})",                               # dotted leaders (TOC)
    r"^(chapter|kanda|varga|adhyaya)\s+\w",   # section headers
    r"https?://|www\.",                        # URLs
    r"©|copyright|all rights reserved",       # copyright
    r"\b(isbn|doi|vol\.|pp\.|ed\.|trans\.)\b",# bibliography
    r"^\s*[ivxlcdmIVXLCDM]+\s*$",            # Roman numerals alone
    r"\d{4}",                                  # years
]

NON_LEXICAL_COMPILED = [re.compile(p, re.IGNORECASE) for p in NON_LEXICAL_LINE_PATTERNS]

OCR_NOISE_PATTERNS = [
    r"^\s*[\(\[]",
    r"(omitted|dial\.|derivations|mss\.|mss\b)",
    r"^\s*\d+[\.\)]\s",
    r"प्र\.\s*\d",
    r"को\.\s*\d",
    r"^\s*[A-Za-z]{1,2}[\.,]",
    r"iti\s+[\w\u0900-\u097F]+\s*[\.\|]",
]

OCR_NOISE_COMPILED = [re.compile(p, re.IGNORECASE) for p in OCR_NOISE_PATTERNS]

# Lines that look like English sentences (not lexical entries)
SENTENCE_PATTERN = re.compile(
    r"\b(is|are|was|were|has|have|had|does|do|did|says|said|means|"
    r"refers|indicates|describes|states|translates|appears|found|"
    r"used|known|called|translated|composed|written|published)\b",
    re.IGNORECASE
)

# A line is "too English" if it has many common English words
COMMON_ENGLISH = {
    "the", "a", "an", "of", "in", "on", "to", "for", "and", "or",
    "but", "with", "from", "by", "as", "at", "its", "it", "this",
    "that", "which", "who", "where", "when", "how", "what",
}


def is_ocr_noise_line(line: str) -> bool:
    for pattern in OCR_NOISE_COMPILED:
        if pattern.search(line):
            return True
    return False


def is_non_lexical_line(line: str) -> bool:
    """Returns True if line should be discarded before parsing."""
    s = line.strip()

    if len(s) < 3:
        return True

    # Check compiled patterns
    for pattern in NON_LEXICAL_COMPILED:
        if pattern.search(s):
            return True

    # Contains a verb → likely a sentence, not a lexical entry
    if SENTENCE_PATTERN.search(s):
        return True

    # Check "too English": if >40% of words are common English words
    words = s.lower().split()
    if len(words) >= 5:
        english_count = sum(1 for w in words if w in COMMON_ENGLISH)
        if english_count / len(words) > 0.4:
            return True

    return False


def is_non_lexical_section(line: str) -> bool:
    """Returns True if this line signals the start of a non-lexical section."""
    return bool(NON_LEXICAL_SECTION_MARKERS.match(line.strip()))


# ──────────────────────────────────────────────────────────────────────────────
# Domain detection
# ──────────────────────────────────────────────────────────────────────────────

def detect_domain(text: str) -> str:
    if any(m in text for m in HERB_DEVANAGARI_MARKERS):
        return "herb"
    if any(k in text.lower() for k in HERB_KEYWORDS):
        return "herb"
    if any(m in text for m in MEDHYA_DEVANAGARI_MARKERS):
        return "medhya"
    if any(k in text.lower() for k in MEDHYA_KEYWORDS):
        return "medhya"
    if any(m in text for m in RASAYANA_DEVANAGARI_MARKERS):
        return "rasayana"
    if any(k in text.lower() for k in RASAYANA_KEYWORDS):
        return "rasayana"
    return "general"

def is_relevant(text: str) -> bool:
    return is_domain_relevant(text)


def entry_has_domain_terms(terms: list[str]) -> bool:
    return any(is_domain_relevant(t) for t in terms)


# ──────────────────────────────────────────────────────────────────────────────
# Line cleaning
# ──────────────────────────────────────────────────────────────────────────────

def clean_line(line: str) -> str:
    line = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", line)    # fix line-break hyphens
    line = re.sub(r"[\[\(]\d+[\.\d]*[\]\)]", "", line)    # remove [1.2] [3]
    line = re.sub(r"\|+", " ", line)                       # remove | markers
    line = re.sub(r"[ \t]+", " ", line)                    # normalize spaces
    return line.strip()


# ──────────────────────────────────────────────────────────────────────────────
# Format detection and term extraction
# ──────────────────────────────────────────────────────────────────────────────

TERM_SEPARATORS = re.compile(
    r"[,;=\/।॥\|·•]|"
    r"\b(ca|cha|va|api|tatha|ityapi|ityeke|ityanye|paryayah|paryaya|"
    r"namani|sabdah|ity|atha)\b",
    re.IGNORECASE
)

DEVANAGARI_TERM_RE = re.compile(r"[\u0900-\u097F]{2,25}")


def extract_devanagari_terms(text: str) -> list[str]:
    return list(dict.fromkeys(DEVANAGARI_TERM_RE.findall(text)))

def extract_terms(text: str, in_synonym_group: bool = False) -> list[str]:
    """Split on synonym separators, return validated terms only."""
    parts = TERM_SEPARATORS.split(text)
    terms = []
    skip_words = {
        "ca", "cha", "va", "api", "tatha", "ityapi", "ityeke", "ityanye",
        "paryayah", "paryaya", "namani", "sabdah", "ity", "atha",
    }
    domain = is_domain_relevant(text)
    for p in parts:
        if p is None:
            continue
        t = re.sub(r"[^\w\s\u0900-\u097F]", "", p).strip()
        if t and t.lower() not in skip_words and len(t) > 1:
            if validate_pdf_term(t, domain, in_synonym_group=in_synonym_group)[0]:
                terms.append(t)
    return terms

def detect_format(line: str) -> str:
    if TERM_SEPARATORS.search(line):
        return "synonym_group"
    if re.match(r"^\w[\w\s\u0900-\u097F]{2,30}\s*:\s*.{10,}", line):
        return "concept_desc"
    return "term_list"


# ──────────────────────────────────────────────────────────────────────────────
# Main parser
# ──────────────────────────────────────────────────────────────────────────────

class AmarakoshaParser:

    def __init__(self):
        self.entries: list[ParsedEntry] = []
        self._in_non_lexical_section    = False

    def _extract_pdf_lines(self, pdf_path: str, use_ocr: bool = False) -> list[tuple[int, str]]:
        page_lines = []
        ocr_count = 0

        if use_ocr:
            ok, msg = check_tesseract()
            if not ok:
                raise RuntimeError(msg)
            print(f"  OCR enabled — {msg}")

        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            print(f"  PDF: {total} pages")
            for i, page in enumerate(pdf.pages):
                page_num = i + 1
                text = extract_page_text(page, page_num, pdf_path, use_ocr)
                if not text:
                    if not use_ocr:
                        print(f"  ⚠ Page {page_num}: no text (scanned?) — use --ocr")
                    continue
                if use_ocr and not (page.extract_text() or "").strip():
                    ocr_count += 1
                    if page_num == 1 or page_num % 25 == 0 or page_num == total:
                        print(f"  OCR progress: page {page_num}/{total}")
                for line in text.split("\n"):
                    page_lines.append((page_num, line))

        if use_ocr:
            print(f"  OCR'd {ocr_count} page(s)")
        print(f"  Raw lines: {len(page_lines)}")
        return page_lines

    def _merge_continuations(self, lines: list[tuple[int,str]]) -> list[tuple[int,str]]:
        merged = []
        i = 0
        while i < len(lines):
            page, line = lines[i]
            while (i + 1 < len(lines)
                   and not re.search(r"[.;|=]$", line.strip())
                   and len(lines[i+1][1]) > 0
                   and lines[i+1][1][0].islower()):
                i += 1
                line = line.strip() + " " + lines[i][1].strip()
            merged.append((page, line))
            i += 1
        return merged

    def _parse_line(self, line: str, page_num: int,
                    parse_all_lines: bool = False) -> ParsedEntry | None:
        cleaned = clean_line(line)

        if is_ocr_noise_line(cleaned) or is_english_commentary(cleaned):
            return None

        if not parse_all_lines and not line_passes_domain_filter(cleaned):
            return None

        entry_domain = parse_all_lines or line_passes_domain_filter(cleaned)

        # Section-level filter
        if is_non_lexical_section(cleaned):
            self._in_non_lexical_section = True
            return None

        # Resume lexical section when Devanagari or known term appears
        if self._in_non_lexical_section:
            if DEVANAGARI_RE.search(cleaned) or is_relevant(cleaned):
                self._in_non_lexical_section = False
            else:
                return None

        # Line-level filter
        if is_non_lexical_line(cleaned):
            return None

        relevant = is_domain_relevant(cleaned) or has_domain_devanagari_marker(cleaned)
        domain   = detect_domain(cleaned)
        fmt      = detect_format(cleaned)

        if fmt == "synonym_group":
            terms = list(dict.fromkeys(
                extract_terms(cleaned, in_synonym_group=True)
                + extract_devanagari_terms(cleaned)
            ))
            terms = [
                t for t in terms
                if validate_pdf_term(t, entry_domain, in_synonym_group=True)[0]
            ]
            if len(terms) < 2:
                return None
            return ParsedEntry(
                terms=terms, synonyms=terms, description="",
                source_line=cleaned, format_type="synonym_group",
                page_num=page_num, domain=domain,
            )

        elif fmt == "concept_desc":
            parts = cleaned.split(":", 1)
            term  = parts[0].strip()
            desc  = parts[1].strip() if len(parts) > 1 else ""

            valid, reason = validate_pdf_term(term, entry_domain)
            if not valid:
                return None

            syn_matches = re.findall(
                r"(?:synonym of|also called|=|paryaya)\s+([\w\u0900-\u097F\s]+)",
                desc, re.IGNORECASE
            )
            synonyms = []
            for m in syn_matches:
                t = m.strip()
                if validate_pdf_term(t, entry_domain)[0]:
                    synonyms.append(t)

            for dt in extract_devanagari_terms(desc):
                if validate_pdf_term(dt, entry_domain)[0]:
                    synonyms.append(dt)

            return ParsedEntry(
                terms=[term], synonyms=synonyms, description=desc,
                source_line=cleaned, format_type="concept_desc",
                page_num=page_num, domain=domain,
            )

        else:  # term_list — also harvest Devanagari tokens from domain lines
            terms = list(dict.fromkeys(
                extract_devanagari_terms(cleaned)
                + [
                    re.sub(r"[^\w\u0900-\u097F]", "", raw).strip()
                    for raw in cleaned.split()
                ]
            ))
            terms = [
                t for t in terms
                if t and validate_pdf_term(t, entry_domain, in_synonym_group=True)[0]
                and len(t) > 1
            ]
            if len(terms) >= 2:
                return ParsedEntry(
                    terms=terms, synonyms=terms, description="",
                    source_line=cleaned, format_type="synonym_group",
                    page_num=page_num, domain=domain,
                )
            if len(terms) == 1:
                return ParsedEntry(
                    terms=terms, synonyms=[], description="",
                    source_line=cleaned, format_type="term_list",
                    page_num=page_num, domain=domain,
                )
            return None

    def parse(self, pdf_path: str, save_cleaned: bool = True,
              use_ocr: bool = False, parse_all_lines: bool = False) -> list[ParsedEntry]:
        print(f"\nParsing: {pdf_path}\n")

        raw_lines = self._extract_pdf_lines(pdf_path, use_ocr=use_ocr)
        merged    = self._merge_continuations(raw_lines)

        entries = []
        n_kept = n_skip = 0

        for page_num, line in merged:
            entry = self._parse_line(line, page_num, parse_all_lines=parse_all_lines)
            if entry:
                entries.append(entry)
                n_kept += 1
            else:
                n_skip += 1

        # Save cleaned output for inspection
        if save_cleaned:
            from config import OUTPUT_CLEANED_PATH
            os.makedirs(os.path.dirname(OUTPUT_CLEANED_PATH), exist_ok=True)
            with open(OUTPUT_CLEANED_PATH, "w", encoding="utf-8") as f:
                for e in entries:
                    f.write(f"[p{e.page_num}][{e.format_type}][{e.domain}] {e.source_line}\n")
            print(f"  Saved cleaned entries → {OUTPUT_CLEANED_PATH}")

        print(f"\n  Entries kept    : {n_kept}")
        print(f"  Lines discarded : {n_skip}")

        from collections import Counter
        domains = Counter(e.domain for e in entries)
        fmts    = Counter(e.format_type for e in entries)
        for domain, count in domains.most_common():
            print(f"    domain={domain:<12}: {count}")
        for fmt, count in fmts.most_common():
            print(f"    format={fmt:<16}: {count}")

        self.entries = entries
        return entries