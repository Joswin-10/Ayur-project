# config.py
# ─────────────────────────────────────────────────────────────────────────────
# Amarakosha → Medhya Rasayana Knowledge Graph
# Central config: Neo4j, Groq, ontology seed, relationship vocab.
# ─────────────────────────────────────────────────────────────────────────────

import os

# ── Neo4j ─────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "Joswin123")

NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "amar")

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL   = "llama-3.3-70b-versatile"
GROQ_DELAY   = 6          # seconds between LLM calls (rate limit)

# ── Output ────────────────────────────────────────────────────────────────────
OUTPUT_DIR          = "output"
OUTPUT_TRIPLES_PATH = "output/triples.json"
OUTPUT_CLEANED_PATH = "output/cleaned_text.txt"

# ── OCR (scanned PDFs) ────────────────────────────────────────────────────────
OCR_LANG       = os.getenv("OCR_LANG", "san+eng")
OCR_DPI        = int(os.getenv("OCR_DPI", "300"))
OCR_CACHE_DIR  = os.path.join(OUTPUT_DIR, "ocr_cache")
TESSERACT_CMD  = os.getenv("TESSERACT_CMD", "")

# ── Graph extraction ──────────────────────────────────────────────────────────
MAX_GRAPH_HOPS = int(os.getenv("MAX_GRAPH_HOPS", "6"))
MAX_GRAPH_NODES = int(os.getenv("MAX_GRAPH_NODES", "1000"))

# ── Node labels ───────────────────────────────────────────────────────────────
LABEL_ROOT     = "RootConcept"
LABEL_CONCEPT  = "Concept"
LABEL_HERB     = "Herb"
LABEL_PROPERTY = "AyurvedicProperty"

ALLOWED_LABELS = {LABEL_ROOT, LABEL_CONCEPT, LABEL_HERB, LABEL_PROPERTY}

# ── Relationship types ────────────────────────────────────────────────────────
REL_SYNONYM_OF      = "SYNONYM_OF"
REL_ASSOCIATED_WITH = "ASSOCIATED_WITH"
REL_ANCHORED_TO     = "ANCHORED_TO"      # PDF root glue only (not semantic seed knowledge)
REL_RELATED_TO      = "RELATED_TO"
REL_PART_OF         = "PART_OF"
REL_TYPE_OF         = "TYPE_OF"
REL_SUPPORTS        = "SUPPORTS"
REL_ENHANCES        = "ENHANCES"
REL_HAS_PROPERTY    = "HAS_PROPERTY"

ALL_RELATIONS = {
    REL_SYNONYM_OF, REL_ASSOCIATED_WITH, REL_ANCHORED_TO, REL_RELATED_TO,
    REL_PART_OF, REL_TYPE_OF, REL_SUPPORTS,
    REL_ENHANCES, REL_HAS_PROPERTY,
}

# Extraction priority — synonym + subgroup first; secondary relations trimmed under node cap
PRIORITY_RELATIONS = {REL_SYNONYM_OF, REL_TYPE_OF, REL_PART_OF}
SECONDARY_RELATIONS = {
    REL_ANCHORED_TO, REL_RELATED_TO, REL_ASSOCIATED_WITH,
    REL_SUPPORTS, REL_ENHANCES, REL_HAS_PROPERTY,
}

# ── Root concepts ─────────────────────────────────────────────────────────────
ROOT_CONCEPTS = [
    {"name": "Medhya",          "description": "That which enhances cognition"},
    {"name": "Rasayana",        "description": "Rejuvenating class of Ayurvedic treatment"},
    {"name": "Medhya Rasayana", "description": "Cognitive rejuvenation — primary domain"},
]

# ── Seed concepts ─────────────────────────────────────────────────────────────
SEED_CONCEPTS = [
    # Cognitive
    {"name": "Medha",        "category": "cognitive", "description": "Cognitive faculty — intellect/wisdom"},
    {"name": "Smriti",       "category": "cognitive", "description": "Memory and retention faculty"},
    {"name": "Buddhi",       "category": "cognitive", "description": "Higher intellect and discrimination"},
    {"name": "Dhi",          "category": "cognitive", "description": "Retentive faculty of the mind"},
    {"name": "Prajna",       "category": "cognitive", "description": "Wisdom from direct knowledge"},
    {"name": "Jnana",        "category": "cognitive", "description": "Knowledge"},
    {"name": "Manas",        "category": "cognitive", "description": "Mind — instrument of cognition"},
    {"name": "Mati",         "category": "cognitive", "description": "Comprehension"},
    {"name": "Dhriti",       "category": "cognitive", "description": "Mental stability and willpower"},
    {"name": "Chitta",       "category": "cognitive", "description": "Consciousness and memory substrate"},
    {"name": "Viveka",       "category": "cognitive", "description": "Discriminative wisdom"},
    {"name": "Dharana",      "category": "cognitive", "description": "Concentration and retention"},
    # Rasayana
    {"name": "Ojas",         "category": "rasayana",  "description": "Vital essence"},
    {"name": "Ayushya",      "category": "rasayana",  "description": "Life-span promoting"},
    {"name": "Balya",        "category": "rasayana",  "description": "Strength promoting"},
    {"name": "Ojovardhana",  "category": "rasayana",  "description": "Increases Ojas"},
    {"name": "Jeevaniya",    "category": "rasayana",  "description": "Life-sustaining"},
    {"name": "Vayasthapana", "category": "rasayana",  "description": "Age-stabilizing"},
    {"name": "Pushtikara",   "category": "rasayana",  "description": "Nourishing and tissue-building"},
    # Properties
    {"name": "Dravya",       "category": "property",  "description": "Substance"},
    {"name": "Kalpana",      "category": "property",  "description": "Pharmaceutical preparation"},
    {"name": "Rasa",         "category": "property",  "description": "Taste"},
    {"name": "Guna",         "category": "property",  "description": "Quality"},
    {"name": "Virya",        "category": "property",  "description": "Potency"},
    {"name": "Vipaka",       "category": "property",  "description": "Post-digestive effect"},
    {"name": "Prabhava",     "category": "property",  "description": "Specific unexplained action"},
]

# ── Seed herbs ────────────────────────────────────────────────────────────────
SEED_HERBS = [
    {
        "name": "Brahmi",        "latin": "Bacopa monnieri",
        "sanskrit": "ब्राह्मी", "category": "medhya_herb",
        "description": "Primary Medhya Rasayana — enhances Smriti and Medha",
        "synonyms": ["Bacopa", "Jalabrahmi", "Brahmi"],
    },
    {
        "name": "Mandukaparni",  "latin": "Centella asiatica",
        "sanskrit": "माण्डूकपर्णी", "category": "medhya_herb",
        "description": "Medhya Rasayana — enhances Medha and Buddhi",
        "synonyms": ["Mandukparni", "Thankuni", "Gotu kola"],
    },
    {
        "name": "Shankhapushpi", "latin": "Convolvulus pluricaulis",
        "sanskrit": "शङ्खपुष्पी", "category": "medhya_herb",
        "description": "Medhya Rasayana — enhances Medha and Smriti",
        "synonyms": ["Shankhpushpi", "Sankhpushpi"],
    },
    {
        "name": "Guduchi",       "latin": "Tinospora cordifolia",
        "sanskrit": "गुडूची",   "category": "medhya_herb",
        "description": "Rasayana — promotes Ojas, balances all doshas",
        "synonyms": ["Giloy", "Gudduci", "Amrita"],
    },
    {
        "name": "Yashtimadhu",   "latin": "Glycyrrhiza glabra",
        "sanskrit": "यष्टिमधु", "category": "medhya_herb",
        "description": "Medhya and Rasayana — supports Ojas",
        "synonyms": ["Yashti", "Licorice", "Mulethi"],
    },
    {
        "name": "Vacha",         "latin": "Acorus calamus",
        "sanskrit": "वचा",      "category": "medhya_herb",
        "description": "Medhya — enhances Smriti and speech",
        "synonyms": ["Vaca", "Sweet flag", "Calamus"],
    },
    {
        "name": "Ashwagandha",   "latin": "Withania somnifera",
        "sanskrit": "अश्वगन्धा","category": "rasayana_herb",
        "description": "Balya and Rasayana — enhances Ojas and strength",
        "synonyms": ["Ashvagandha", "Withania", "Winter cherry"],
    },
]

# ── Seed relationships (classical knowledge, always inserted) ─────────────────
SEED_RELATIONSHIPS = [
    # Root hierarchy
    ("Medhya Rasayana", REL_TYPE_OF,         "Rasayana"),
    ("Medhya Rasayana", REL_ASSOCIATED_WITH,  "Medhya"),
    # Cognitive → Medhya (subgroup + association)
    ("Medha",   REL_PART_OF,         "Medhya"),
    ("Smriti",  REL_PART_OF,         "Medhya"),
    ("Buddhi",  REL_PART_OF,         "Medhya"),
    ("Dhi",     REL_PART_OF,         "Medhya"),
    ("Prajna",  REL_PART_OF,         "Medhya"),
    ("Manas",   REL_PART_OF,         "Medhya"),
    ("Dhriti",  REL_PART_OF,         "Medhya"),
    ("Chitta",  REL_PART_OF,         "Medhya"),
    ("Mati",    REL_PART_OF,         "Medhya"),
    ("Viveka",  REL_PART_OF,         "Medhya"),
    ("Dharana", REL_PART_OF,         "Medhya"),
    ("Jnana",   REL_PART_OF,         "Medhya"),
    ("Medhya", REL_ASSOCIATED_WITH, "Medha"),
    ("Medhya", REL_ASSOCIATED_WITH, "Smriti"),
    ("Medhya", REL_ASSOCIATED_WITH, "Buddhi"),
    ("Medhya", REL_ASSOCIATED_WITH, "Dhi"),
    ("Medhya", REL_ASSOCIATED_WITH, "Prajna"),
    ("Medhya", REL_ASSOCIATED_WITH, "Manas"),
    ("Medhya", REL_ASSOCIATED_WITH, "Dhriti"),
    ("Medhya", REL_ASSOCIATED_WITH, "Chitta"),
    # Cognitive synonyms
    ("Medha",  REL_SYNONYM_OF, "Buddhi"),
    ("Medha",  REL_SYNONYM_OF, "Prajna"),
    ("Buddhi", REL_SYNONYM_OF, "Dhi"),
    ("Smriti", REL_RELATED_TO, "Chitta"),
    ("Smriti", REL_RELATED_TO, "Manas"),
    ("Smriti", REL_RELATED_TO, "Dharana"),
    ("Viveka", REL_RELATED_TO, "Buddhi"),
    # Rasayana subgroups
    ("Ojas",         REL_PART_OF,         "Rasayana"),
    ("Ayushya",      REL_PART_OF,         "Rasayana"),
    ("Balya",        REL_PART_OF,         "Rasayana"),
    ("Vayasthapana", REL_PART_OF,         "Rasayana"),
    ("Jeevaniya",    REL_PART_OF,         "Rasayana"),
    ("Pushtikara",   REL_PART_OF,         "Rasayana"),
    ("Ojovardhana",  REL_PART_OF,         "Rasayana"),
    ("Rasayana",    REL_ASSOCIATED_WITH, "Ojas"),
    ("Rasayana",    REL_ASSOCIATED_WITH, "Ayushya"),
    ("Rasayana",    REL_ASSOCIATED_WITH, "Balya"),
    ("Rasayana",    REL_ASSOCIATED_WITH, "Vayasthapana"),
    ("Ojovardhana", REL_RELATED_TO,      "Ojas"),
    ("Pushtikara",  REL_SUPPORTS,        "Ojas"),
    # Herbs → Medhya Rasayana
    ("Brahmi",        REL_TYPE_OF,    "Medhya Rasayana"),
    ("Mandukaparni",  REL_TYPE_OF,    "Medhya Rasayana"),
    ("Shankhapushpi", REL_TYPE_OF,    "Medhya Rasayana"),
    ("Guduchi",       REL_TYPE_OF,    "Medhya Rasayana"),
    ("Yashtimadhu",   REL_TYPE_OF,    "Medhya Rasayana"),
    ("Vacha",         REL_TYPE_OF,    "Medhya Rasayana"),
    ("Ashwagandha",   REL_TYPE_OF,    "Rasayana"),
    # Herb → cognitive effects
    ("Brahmi",        REL_ENHANCES, "Smriti"),
    ("Brahmi",        REL_ENHANCES, "Medha"),
    ("Shankhapushpi", REL_ENHANCES, "Medha"),
    ("Shankhapushpi", REL_ENHANCES, "Smriti"),
    ("Mandukaparni",  REL_ENHANCES, "Medha"),
    ("Mandukaparni",  REL_ENHANCES, "Buddhi"),
    ("Vacha",         REL_ENHANCES, "Smriti"),
    ("Yashtimadhu",   REL_SUPPORTS, "Ojas"),
    ("Guduchi",       REL_SUPPORTS, "Ojas"),
    ("Ashwagandha",   REL_ENHANCES, "Ojas"),
    # Properties
    ("Dravya", REL_HAS_PROPERTY, "Rasa"),
    ("Dravya", REL_HAS_PROPERTY, "Guna"),
    ("Dravya", REL_HAS_PROPERTY, "Virya"),
    ("Dravya", REL_HAS_PROPERTY, "Vipaka"),
    ("Dravya", REL_HAS_PROPERTY, "Prabhava"),
]

# ── Amarakosha-specific: known synonym group markers ─────────────────────────
# These words in Amarakosha signal that listed terms are synonyms.
AMAR_SYNONYM_MARKERS = [
    "ityapi", "ityeke", "ityanye", "api", "ca", "cha",
    "paryayah", "paryaya", "namani", "sabdah",
]

# ── Keywords that signal Medhya/cognitive relevance ──────────────────────────
MEDHYA_KEYWORDS = {
    "medha", "smriti", "buddhi", "dhi", "prajna", "manas", "chitta",
    "mati", "dhriti", "viveka", "jnana", "dharana", "medhya",
    "smaran", "dharan", "chetana", "bodha", "buddhi", "prajna",
    "medhavardhana", "smritivardhana", "buddhivardhana", "smritiprada",
    "medhakara", "medhajanana", "anusmriti",
}

RASAYANA_KEYWORDS = {
    "rasayana", "ojas", "ayushya", "balya", "jeevaniya",
    "vayasthapana", "pushtikara", "ojovardhana", "brimhana",
    "jivaniya", "vrishya", "ayushya", "balya", "jeevan",
}

HERB_KEYWORDS = {
    "brahmi", "shankhapushpi", "mandukaparni", "guduchi", "yashtimadhu",
    "vacha", "ashwagandha", "bacopa", "centella", "tinospora",
    "mandukparni", "shankhpushpi", "jalabrahmi", "giloy", "gotu",
    "mulethi", "licorice", "ashvagandha", "thankuni", "amrita",
}

PROPERTY_KEYWORDS = {
    "rasa", "guna", "virya", "vipaka", "prabhava", "kalpana", "dravya",
    "swarasa", "churna", "kalka", "kwatha", "avaleha",
}

DOMAIN_SUFFIXES = {
    "vardhana", "vardhini", "vardhani", "prada", "kara", "janana",
    "vardhan", "pradayini",
}

MEDHYA_DEVANAGARI_MARKERS = (
    "मेधा", "मेध", "स्मृति", "स्मृ", "बुद्धि", "बुद्ध", "प्रज्ञा", "प्रज्ञ",
    "मनस", "धीः", "धीय", "संवित", "संकल्प", "चेतना", "बोध",
)

RASAYANA_DEVANAGARI_MARKERS = (
    "रसायन", "ओज", "आयुष", "बल्य", "जीवन", "वयः", "पुष्ट",
)

HERB_DEVANAGARI_MARKERS = (
    "ब्राह्म", "शङ्ख", "माण्डूक", "गुडूच", "वचा", "अश्वगन्ध",
    "यष्टि", "मन्थ", "तुलसी", "नाग",
)

ALL_RELEVANT_KEYWORDS = (
    MEDHYA_KEYWORDS | RASAYANA_KEYWORDS | HERB_KEYWORDS | PROPERTY_KEYWORDS
)

# ── Synonym map for normalization ─────────────────────────────────────────────
SYNONYM_MAP = {}
for h in SEED_HERBS:
    for syn in h.get("synonyms", []):
        SYNONYM_MAP[syn.lower()] = h["name"]

# Add concept synonyms
SYNONYM_MAP.update({
    "smaran":      "Smriti",
    "dharana":     "Smriti",
    "anusmriti":   "Smriti",
    "prajna":      "Prajna",
    "mati":        "Mati",
    "dhi":         "Dhi",
    "buddhi":      "Buddhi",
    "medha":       "Medha",
    "jnana":       "Jnana",
    "chitta":      "Chitta",
    "manas":       "Manas",
})