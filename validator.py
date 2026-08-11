# validator.py
# ─────────────────────────────────────────────────────────────────────────────
# Single source of truth for concept validation.
# Every candidate node/concept passes through here before entering the graph.
# ─────────────────────────────────────────────────────────────────────────────

import re

from config import (
    ALL_RELEVANT_KEYWORDS,
    DOMAIN_SUFFIXES,
    HERB_KEYWORDS,
    HERB_DEVANAGARI_MARKERS,
    MEDHYA_KEYWORDS,
    MEDHYA_DEVANAGARI_MARKERS,
    RASAYANA_KEYWORDS,
    RASAYANA_DEVANAGARI_MARKERS,
)

# ── Ontology whitelist ────────────────────────────────────────────────────────
# ONLY concepts matching or directly related to these survive extraction.

ONTOLOGY_WHITELIST = {
    # Root
    "Medhya", "Rasayana", "Medhya Rasayana",
    # Cognitive
    "Medha", "Smriti", "Buddhi", "Dhi", "Prajna", "Jnana",
    "Manas", "Mati", "Dhriti", "Chitta", "Viveka", "Dharana",
    # Rasayana
    "Ayushya", "Balya", "Ojas", "Ojovardhana", "Jeevaniya",
    "Vayasthapana", "Pushtikara", "Brimhana",
    # Herbs
    "Mandukaparni", "Brahmi", "Shankhapushpi", "Guduchi",
    "Yashtimadhu", "Vacha", "Ashwagandha",
    # Properties
    "Dravya", "Kalpana", "Rasa", "Guna", "Virya", "Vipaka", "Prabhava",
    # Doshas
    "Vata", "Pitta", "Kapha",
    # Tissues
    "Dhatu", "Majja", "Rakta", "Rasa", "Mamsa",
    # Vital principles
    "Agni", "Prana", "Tejas",
    # Gunas
    "Sattva", "Rajas", "Tamas",
}

WHITELIST_LOWER = {w.lower() for w in ONTOLOGY_WHITELIST}

# ── Known Sanskrit synonym terms from Amarakosha ──────────────────────────────
# These are accepted even if not in the whitelist above,
# because they are valid Sanskrit lexical terms.
KNOWN_SANSKRIT_TERMS = {
    # Smriti synonyms
    "smaran", "anusmriti", "dharana", "smarana",
    # Medha synonyms
    "medhakara", "medhavardhana", "medhajanana",
    # Buddhi synonyms
    "buddhivardhana", "buddhiprada",
    # Rasayana synonyms
    "vayasthapana", "jivaniya", "jeevaniya",
    # Herb synonyms
    "jalabrahmi", "mandukparni", "thankuni",
    "shankhpushpi", "sankhpushpi",
    "giloy", "gudduci", "amrita",
    "yashti", "mulethi",
    "vaca", "ashvagandha",
    # Action terms
    "vardhana", "vardhini", "prada", "kara", "janana",
    # Compound terms accepted
    "smritivardhana", "medhavardhana", "buddhivardhana",
    "ojovardhana", "smritiprada", "medhakara",
}

# ── Rejection rules ───────────────────────────────────────────────────────────

# English stopwords that signal non-ontology content
REJECT_STARTWORDS = {
    "the", "a", "an", "who", "which", "where", "when", "why",
    "for", "because", "thus", "therefore", "however", "although",
    "this", "that", "these", "those", "it", "its", "is", "are",
    "was", "were", "has", "have", "had", "been", "being",
    "and", "or", "but", "so", "yet", "if", "as", "at", "by",
    "of", "in", "on", "to", "from", "with", "into",
}

# Patterns that immediately disqualify a candidate
REJECT_PATTERNS = [
    r"\d{4}",                          # years like 1899, 2003
    r"https?://",                      # URLs
    r"www\.",                          # URLs
    r"p\.\s*\d+",                      # page references
    r"[.!?]{1}.*[.!?]",               # multiple sentence-ending punctuation
    r"\b(isbn|doi|vol|pp|ed|trans|ibid)\b",  # bibliography markers
    r"©|copyright",                    # copyright
    r"[<>\[\]{}\|\\]",                # special characters
]

REJECT_COMPILED = [re.compile(p, re.IGNORECASE) for p in REJECT_PATTERNS]

# Verbs that signal a sentence rather than a concept
ENGLISH_VERBS = {
    "is", "are", "was", "were", "has", "have", "had", "does", "do", "did",
    "says", "said", "means", "refers", "indicates", "describes", "states",
    "translates", "appears", "seems", "found", "used", "known", "called",
    "translated", "composed", "written", "published",
}

# Devanagari range
DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

_MEDHYA_ROOT_FRAGMENTS = tuple(sorted(MEDHYA_KEYWORDS | {"medhy", "smrit", "buddh", "prajn", "manas"}))
_RASAYANA_ROOT_FRAGMENTS = tuple(sorted(RASAYANA_KEYWORDS | {"rasayan", "ojas", "ayush", "balya"}))
_HERB_ROOT_FRAGMENTS = tuple(sorted(HERB_KEYWORDS))

SENTENCE_PATTERN = re.compile(
    r"\b(is|are|was|were|has|have|had|does|do|did|says|said|means|"
    r"refers|indicates|describes|states|translates|appears|found|"
    r"used|known|called|translated|composed|written|published)\b",
    re.IGNORECASE,
)


def has_domain_devanagari_marker(text: str) -> bool:
    return any(m in text for m in (
        MEDHYA_DEVANAGARI_MARKERS + RASAYANA_DEVANAGARI_MARKERS + HERB_DEVANAGARI_MARKERS
    ))


def is_english_commentary(line: str) -> bool:
    """Skip translator notes and English prose paragraphs."""
    words = re.findall(r"[A-Za-z]{3,}", line)
    dev_count = len(DEVANAGARI_RE.findall(line))
    if len(words) >= 8 and dev_count < 3:
        return True
    if SENTENCE_PATTERN.search(line) and len(words) >= 5 and dev_count < 2:
        return True
    if re.search(r"\b(Buddhist|philosophy|edition|manuscript|translator|preface)\b", line, re.I):
        return True
    return False


def line_passes_domain_filter(line: str) -> bool:
    if is_domain_relevant(line):
        return True
    if has_domain_devanagari_marker(line):
        return True
    return False


def is_domain_relevant(text: str) -> bool:
    """True if text is plausibly Medhya/Rasayana/herb/property related."""
    if not text or not text.strip():
        return False

    lower = text.lower()
    compact = re.sub(r"[^\w\u0900-\u097F]", "", lower)

    if any(k in lower for k in ALL_RELEVANT_KEYWORDS):
        return True

    for root in WHITELIST_LOWER:
        if len(root) > 3 and root in compact:
            return True

    if any(suf in compact for suf in DOMAIN_SUFFIXES):
        if any(r in compact for r in _MEDHYA_ROOT_FRAGMENTS + _RASAYANA_ROOT_FRAGMENTS):
            return True

    if any(r in compact for r in _HERB_ROOT_FRAGMENTS):
        return True

    return False


DEVANAGARI_STOP_TERMS = {
    "इति", "अत्र", "तु", "च", "वा", "हि", "एव", "सा", "सः", "तत्",
    "या", "कम्", "नाम", "नामानि", "स्य", "स्यात्", "भवति", "उक्त",
    "शब्द", "शब्दः", "द्वि", "त्रि", "चतु", "पञ्च",
}


def is_ocr_noise_term(name: str) -> bool:
    """Reject common OCR garbage while keeping Sanskrit lexical terms."""
    if name in DEVANAGARI_STOP_TERMS:
        return True

    if re.search(r"\d", name):
        return True

    letters = re.findall(r"[A-Za-z]", name)
    devanagari = DEVANAGARI_RE.findall(name)
    if letters and devanagari and len(name) < 20:
        return True

    if len(name) < 3:
        return True

    if re.fullmatch(r"[\W\d_]+", name):
        return True

    latin_ratio = len(letters) / max(len(name.replace(" ", "")), 1)
    if latin_ratio > 0.85 and not is_domain_relevant(name):
        return True

    if DEVANAGARI_RE.search(name) and len(name) > 22:
        return True

    return False


def has_strong_domain_signal(text: str) -> bool:
    """Stricter than is_domain_relevant — avoids substring false positives."""
    if not text:
        return False
    if text in ONTOLOGY_WHITELIST or text.lower() in WHITELIST_LOWER:
        return True
    if text.lower() in KNOWN_SANSKRIT_TERMS:
        return True
    lower = text.lower()
    for kw in ALL_RELEVANT_KEYWORDS:
        if len(kw) >= 4 and re.search(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", lower):
            return True
    return any(m in text for m in (
        MEDHYA_DEVANAGARI_MARKERS + RASAYANA_DEVANAGARI_MARKERS + HERB_DEVANAGARI_MARKERS
    ))


# ── Validation function ───────────────────────────────────────────────────────

def validate_concept(name: str) -> tuple[bool, str]:
    """
    Returns (is_valid, rejection_reason).
    is_valid=True  → safe to add to graph.
    is_valid=False → rejection_reason explains why.
    """
    if not name or not name.strip():
        return False, "empty"

    name = name.strip()

    # ── Rule 1: Length ──────────────────────────────────────────────────────
    if len(name) > 50:
        return False, f"too long ({len(name)} chars)"

    words = name.split()
    if len(words) > 4:
        return False, f"too many words ({len(words)})"

    # ── Rule 2: Reject patterns ─────────────────────────────────────────────
    for pattern in REJECT_COMPILED:
        if pattern.search(name):
            return False, f"matches reject pattern: {pattern.pattern[:30]}"

    # ── Rule 3: Starts with stopword ────────────────────────────────────────
    if words[0].lower() in REJECT_STARTWORDS:
        return False, f"starts with stopword: '{words[0]}'"

    # ── Rule 4: Contains verb → likely a sentence ───────────────────────────
    word_set = {w.lower() for w in words}
    verb_hits = word_set & ENGLISH_VERBS
    if verb_hits:
        return False, f"contains verb: {verb_hits}"

    # ── Rule 5: Punctuation suggesting a sentence ───────────────────────────
    if re.search(r"[.!?;]", name):
        return False, "contains sentence punctuation"

    # ── Rule 6: Pure number or mostly numeric ───────────────────────────────
    if re.fullmatch(r"[\d\s\-]+", name):
        return False, "numeric only"

    # ── Rule 7: Whitelist check ─────────────────────────────────────────────
    # Accept if in ontology whitelist
    if name in ONTOLOGY_WHITELIST or name.lower() in WHITELIST_LOWER:
        return True, "whitelist"

    # Accept known Sanskrit terms
    if name.lower() in KNOWN_SANSKRIT_TERMS:
        return True, "known_sanskrit"

    # Accept Devanagari text only when domain-relevant (avoids OCR junk nodes)
    if DEVANAGARI_RE.search(name):
        if is_domain_relevant(name):
            return True, "devanagari_domain"
        return False, "devanagari_not_domain"

    # ── Rule 8: Medhya-proximity check ─────────────────────────────────────
    # Accept compound Sanskrit terms that contain whitelist roots
    name_lower = name.lower()
    for root in WHITELIST_LOWER:
        if root in name_lower and len(root) > 3:
            return True, f"contains_root:{root}"

    # ── Rule 9: Reject if purely English and not in whitelist ───────────────
    # A concept with ALL English words that isn't whitelisted is likely noise
    all_ascii = all(ord(c) < 128 for c in name.replace(" ", ""))
    if all_ascii and len(words) > 1:
        # Multi-word English phrase not in whitelist → reject
        return False, "multi-word English phrase not in ontology"

    # Single transliterated word — keep only if domain-relevant
    if is_domain_relevant(name):
        return True, "domain_relevant"

    return False, "not_domain_relevant"


def validate_pdf_term(
    name: str,
    entry_is_domain: bool = False,
    in_synonym_group: bool = False,
) -> tuple[bool, str]:
    """Stricter validation for PDF-extracted terms."""
    if is_ocr_noise_term(name):
        return False, "ocr_noise"

    if in_synonym_group and entry_is_domain and DEVANAGARI_RE.search(name):
        if 2 <= len(name) <= 22 and not re.search(r"\d", name):
            if name not in DEVANAGARI_STOP_TERMS:
                return True, "synonym_group_devanagari"

    if entry_is_domain and DEVANAGARI_RE.search(name):
        if 2 <= len(name) <= 22 and not re.search(r"\d", name):
            if has_strong_domain_signal(name) or len(name) <= 12:
                return True, "entry_domain_devanagari"

    valid, reason = validate_concept(name)
    if not valid:
        return False, reason

    if entry_is_domain or reason in {"whitelist", "known_sanskrit"}:
        return True, reason

    if reason.startswith("contains_root:"):
        return True, reason

    if is_domain_relevant(name):
        return True, reason

    return False, "not_domain_relevant"


class ValidationReport:
    """Tracks accept/reject counts and reasons for reporting."""

    def __init__(self):
        self.accepted: list[str]             = []
        self.rejected: list[tuple[str, str]] = []   # (name, reason)

    def record(self, name: str, valid: bool, reason: str):
        if valid:
            self.accepted.append(name)
        else:
            self.rejected.append((name, reason))

    def print_report(self):
        print(f"\n── Validation Report ───────────────────────────────────────")
        print(f"  Accepted : {len(self.accepted)}")
        print(f"  Rejected : {len(self.rejected)}")

        if self.rejected:
            # Group by reason
            from collections import Counter
            reason_counts = Counter(r for _, r in self.rejected)
            print(f"\n  Rejection reasons:")
            for reason, count in reason_counts.most_common():
                print(f"    {reason:<45}: {count}")

            print(f"\n  Sample rejected (first 15):")
            for name, reason in self.rejected[:15]:
                print(f"    '{name[:60]}' → {reason}")

        print(f"────────────────────────────────────────────────────────────")