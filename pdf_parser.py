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

from config import ALL_RELEVANT_KEYWORDS, MEDHYA_KEYWORDS, RASAYANA_KEYWORDS, HERB_KEYWORDS
from validator import validate_concept, DEVANAGARI_RE

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
    lower = text.lower()
    if any(k in lower for k in HERB_KEYWORDS):    return "herb"
    if any(k in lower for k in MEDHYA_KEYWORDS):  return "medhya"
    if any(k in lower for k in RASAYANA_KEYWORDS):return "rasayana"
    return "general"

def is_relevant(text: str) -> bool:
    lower = text.lower()
    # Accept if contains known keywords OR Devanagari
    return (any(k in lower for k in ALL_RELEVANT_KEYWORDS)
            or bool(DEVANAGARI_RE.search(text)))


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
    r"[,;=\/]|"
    r"\b(ca|cha|va|api|tatha|ityapi|ityeke|ityanye|paryayah|paryaya)\b",
    re.IGNORECASE
)

def extract_terms(text: str) -> list[str]:
    """Split on synonym separators, return validated terms only."""
    parts = TERM_SEPARATORS.split(text)
    terms = []
    skip_words = {"ca","cha","va","api","tatha","ityapi","ityeke","ityanye","paryayah","paryaya"}
    for p in parts:
        if p is None:
            continue
        t = re.sub(r"[^\w\s\u0900-\u097F]", "", p).strip()
        if t and t.lower() not in skip_words and len(t) > 1:
            valid, _ = validate_concept(t)
            if valid:
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

    def _extract_pdf_lines(self, pdf_path: str) -> list[tuple[int, str]]:
        page_lines = []
        with pdfplumber.open(pdf_path) as pdf:
            print(f"  PDF: {len(pdf.pages)} pages")
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    print(f"  ⚠ Page {i+1}: no text (scanned?)")
                    continue
                for line in text.split("\n"):
                    page_lines.append((i + 1, line))
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

    def _parse_line(self, line: str, page_num: int) -> ParsedEntry | None:
        cleaned = clean_line(line)

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

        relevant = is_relevant(cleaned)
        domain   = detect_domain(cleaned)
        fmt      = detect_format(cleaned)

        if fmt == "synonym_group":
            terms = extract_terms(cleaned)
            if len(terms) < 2:          # need at least 2 terms for a synonym group
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

            valid, reason = validate_concept(term)
            if not valid:
                return None

            syn_matches = re.findall(
                r"(?:synonym of|also called|=|paryaya)\s+([\w\u0900-\u097F\s]+)",
                desc, re.IGNORECASE
            )
            synonyms = []
            for m in syn_matches:
                t = m.strip()
                v, _ = validate_concept(t)
                if v:
                    synonyms.append(t)

            return ParsedEntry(
                terms=[term], synonyms=synonyms, description=desc,
                source_line=cleaned, format_type="concept_desc",
                page_num=page_num, domain=domain,
            )

        else:  # term_list
            # Only accept if relevant to Medhya/Rasayana domain
            if not relevant:
                return None
            terms = []
            for raw in cleaned.split():
                t = re.sub(r"[^\w\u0900-\u097F]", "", raw).strip()
                valid, _ = validate_concept(t)
                if valid and len(t) > 2:
                    terms.append(t)
            if not terms:
                return None
            return ParsedEntry(
                terms=terms, synonyms=[], description="",
                source_line=cleaned, format_type="term_list",
                page_num=page_num, domain=domain,
            )

    def parse(self, pdf_path: str, save_cleaned: bool = True) -> list[ParsedEntry]:
        print(f"\nParsing: {pdf_path}\n")

        raw_lines = self._extract_pdf_lines(pdf_path)
        merged    = self._merge_continuations(raw_lines)

        entries = []
        n_kept = n_skip = 0

        for page_num, line in merged:
            entry = self._parse_line(line, page_num)
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