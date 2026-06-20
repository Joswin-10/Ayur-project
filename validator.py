# validator.py
# ─────────────────────────────────────────────────────────────────────────────
# Single source of truth for concept validation.
# Every candidate node/concept passes through here before entering the graph.
# ─────────────────────────────────────────────────────────────────────────────

import re

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

    # Accept Devanagari text (Sanskrit script)
    if DEVANAGARI_RE.search(name):
        return True, "devanagari"

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

    # Single English word — accept cautiously (may be transliteration)
    return True, "accepted"


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