# extractor.py
# ─────────────────────────────────────────────────────────────────────────────
# Converts ParsedEntry → triples.
# Every candidate node is validated before being added.
# Graph-distance filtering: concepts must be within 2 hops of Medhya/Rasayana.
# ─────────────────────────────────────────────────────────────────────────────

import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from pdf_parser import ParsedEntry
from validator  import validate_concept, ValidationReport, ONTOLOGY_WHITELIST
from config import (
    ROOT_CONCEPTS, SEED_CONCEPTS, SEED_HERBS, SEED_RELATIONSHIPS,
    SYNONYM_MAP, ALL_RELATIONS,
    LABEL_ROOT, LABEL_CONCEPT, LABEL_HERB, LABEL_PROPERTY,
    GROQ_API_KEY, GROQ_MODEL, GROQ_DELAY,
    REL_SYNONYM_OF, REL_ASSOCIATED_WITH, REL_RELATED_TO,
    REL_TYPE_OF, REL_SUPPORTS, REL_ENHANCES, REL_HAS_PROPERTY,
    MEDHYA_KEYWORDS, RASAYANA_KEYWORDS, HERB_KEYWORDS,
)

COGNITIVE_CONCEPTS = {c["name"] for c in SEED_CONCEPTS if c["category"] == "cognitive"}
RASAYANA_CONCEPTS  = {c["name"] for c in SEED_CONCEPTS if c["category"] == "rasayana"}
PROPERTY_CONCEPTS  = {c["name"] for c in SEED_CONCEPTS if c["category"] == "property"}
ROOT_NAMES         = {r["name"] for r in ROOT_CONCEPTS}
HERB_NAMES         = {h["name"] for h in SEED_HERBS}

# Max allowed hops from Medhya/Rasayana/Medhya Rasayana
MAX_HOPS = 2


@dataclass
class Triple:
    subject:    str
    relation:   str
    object:     str
    source:     str   = "rule"
    confidence: float = 1.0


@dataclass
class Node:
    name:        str
    label:       str
    category:    str = ""
    description: str = ""
    sanskrit:    str = ""
    latin:       str = ""
    source:      str = "seed"


class MedhyaExtractor:

    def __init__(self, use_llm: bool = False):
        self.use_llm       = use_llm and bool(GROQ_API_KEY)
        self.nodes:        list[Node]   = []
        self.triples:      list[Triple] = []
        self._node_index:  set[str]     = set()
        self._triple_set:  set[tuple]   = set()
        self.report        = ValidationReport()

        if self.use_llm:
            from groq import Groq
            self._groq = Groq(api_key=GROQ_API_KEY)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def resolve_canonical(self, name: str) -> str:
        return SYNONYM_MAP.get(name.strip().lower(), name.strip().title())

    def resolve_label(self, name: str) -> str:
        if name in ROOT_NAMES:         return LABEL_ROOT
        if name in HERB_NAMES:         return LABEL_HERB
        if name in PROPERTY_CONCEPTS:  return LABEL_PROPERTY
        return LABEL_CONCEPT

    def add_node(self, node: Node) -> bool:
        """Validates before adding. Returns True if added."""
        valid, reason = validate_concept(node.name)
        self.report.record(node.name, valid, reason)
        if valid and node.name not in self._node_index:
            self.nodes.append(node)
            self._node_index.add(node.name)
            return True
        return False

    def add_triple(self, triple: Triple):
        key = (triple.subject, triple.relation, triple.object)
        if key not in self._triple_set:
            self.triples.append(triple)
            self._triple_set.add(key)

    # ── Seed loading ──────────────────────────────────────────────────────────

    def load_seeds(self):
        """Seed nodes bypass validation — they are trusted ontology."""
        for r in ROOT_CONCEPTS:
            node = Node(r["name"], LABEL_ROOT, "root", r["description"], source="seed")
            if node.name not in self._node_index:
                self.nodes.append(node)
                self._node_index.add(node.name)

        for c in SEED_CONCEPTS:
            node = Node(c["name"], self.resolve_label(c["name"]),
                        c["category"], c["description"], source="seed")
            if node.name not in self._node_index:
                self.nodes.append(node)
                self._node_index.add(node.name)

        for h in SEED_HERBS:
            node = Node(h["name"], LABEL_HERB, h["category"],
                        h["description"], h.get("sanskrit",""), h.get("latin",""),
                        source="seed")
            if node.name not in self._node_index:
                self.nodes.append(node)
                self._node_index.add(node.name)
            for syn in h.get("synonyms", []):
                if syn != h["name"]:
                    syn_node = Node(syn, LABEL_HERB, h["category"], source="seed")
                    if syn not in self._node_index:
                        self.nodes.append(syn_node)
                        self._node_index.add(syn)
                    self.add_triple(Triple(syn, REL_SYNONYM_OF, h["name"], "seed"))

        for subj, rel, obj in SEED_RELATIONSHIPS:
            self.add_triple(Triple(subj, rel, obj, "seed"))

        print(f"  Seeds: {len(self.nodes)} nodes, {len(self.triples)} triples")

    # ── Rule-based extraction ─────────────────────────────────────────────────

    def extract_rules(self, entry: ParsedEntry) -> list[Triple]:
        triples = []

        if entry.format_type == "synonym_group":
            terms = [self.resolve_canonical(t) for t in entry.synonyms]
            # Only keep terms that pass validation
            terms = [t for t in terms if validate_concept(t)[0]]

            if len(terms) < 2:
                return []

            # SYNONYM_OF chain — Amarakosha primary relation
            for i in range(len(terms) - 1):
                triples.append(Triple(terms[i], REL_SYNONYM_OF, terms[i+1], "rule"))

            # Anchor to domain root ONLY if strong evidence
            if entry.domain == "medhya" or any(t in COGNITIVE_CONCEPTS for t in terms):
                for t in terms:
                    if t not in ROOT_NAMES:
                        triples.append(Triple("Medhya", REL_ASSOCIATED_WITH, t, "rule"))

            if entry.domain == "rasayana" or any(t in RASAYANA_CONCEPTS for t in terms):
                for t in terms:
                    if t not in ROOT_NAMES:
                        triples.append(Triple("Rasayana", REL_ASSOCIATED_WITH, t, "rule"))

            if entry.domain == "herb" or any(t in HERB_NAMES for t in terms):
                for t in terms:
                    if t in HERB_NAMES:
                        triples.append(Triple(t, REL_TYPE_OF, "Medhya Rasayana", "rule"))

        elif entry.format_type == "concept_desc":
            if not entry.terms:
                return []
            term = self.resolve_canonical(entry.terms[0])
            if not validate_concept(term)[0]:
                return []

            desc_lower = entry.description.lower()

            for syn in entry.synonyms:
                canon = self.resolve_canonical(syn)
                if validate_concept(canon)[0]:
                    triples.append(Triple(term, REL_SYNONYM_OF, canon, "rule"))

            if any(k in desc_lower for k in MEDHYA_KEYWORDS):
                triples.append(Triple("Medhya", REL_ASSOCIATED_WITH, term, "rule"))
            if any(k in desc_lower for k in RASAYANA_KEYWORDS):
                triples.append(Triple("Rasayana", REL_ASSOCIATED_WITH, term, "rule"))

            for concept in COGNITIVE_CONCEPTS:
                if concept.lower() in desc_lower and term in HERB_NAMES:
                    triples.append(Triple(term, REL_ENHANCES, concept, "rule"))

        elif entry.format_type == "term_list":
            for raw in entry.terms:
                term = self.resolve_canonical(raw)
                if not validate_concept(term)[0]:
                    continue
                if term in COGNITIVE_CONCEPTS:
                    triples.append(Triple("Medhya", REL_ASSOCIATED_WITH, term, "rule"))
                if term in RASAYANA_CONCEPTS:
                    triples.append(Triple("Rasayana", REL_ASSOCIATED_WITH, term, "rule"))
                if term in HERB_NAMES:
                    triples.append(Triple(term, REL_TYPE_OF, "Medhya Rasayana", "rule"))

        return triples

    # ── Graph-distance filter ─────────────────────────────────────────────────

    def filter_by_graph_distance(self):
        """
        Remove any node that is more than MAX_HOPS away from
        Medhya, Rasayana, or Medhya Rasayana.
        Uses BFS on the current triple set.
        """
        # Build adjacency (undirected for distance calc)
        adj = defaultdict(set)
        for t in self.triples:
            adj[t.subject].add(t.object)
            adj[t.object].add(t.subject)

        roots = {"Medhya", "Rasayana", "Medhya Rasayana"}
        reachable = set()

        # BFS from all root nodes
        queue = deque()
        for root in roots:
            queue.append((root, 0))
            reachable.add(root)

        while queue:
            node, dist = queue.popleft()
            if dist >= MAX_HOPS:
                continue
            for neighbor in adj.get(node, []):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    queue.append((neighbor, dist + 1))

        # Always keep seed ontology nodes regardless of distance
        seed_names = {n.name for n in self.nodes if n.source == "seed"}
        reachable |= seed_names

        # Filter nodes
        before = len(self.nodes)
        self.nodes = [n for n in self.nodes if n.name in reachable]
        self._node_index = {n.name for n in self.nodes}

        # Filter triples — both endpoints must be reachable
        self.triples = [
            t for t in self.triples
            if t.subject in reachable and t.object in reachable
        ]
        self._triple_set = {(t.subject, t.relation, t.object) for t in self.triples}

        removed = before - len(self.nodes)
        print(f"  Graph-distance filter: removed {removed} nodes beyond {MAX_HOPS} hops")
        print(f"  Remaining: {len(self.nodes)} nodes, {len(self.triples)} triples")

    # ── Register node from entry ──────────────────────────────────────────────

    def register_nodes(self, entry: ParsedEntry):
        for raw in entry.terms:
            name = self.resolve_canonical(raw)
            if name and name not in self._node_index:
                self.add_node(Node(
                    name=name,
                    label=self.resolve_label(name),
                    category=entry.domain,
                    description=entry.description,
                    source="amarakosha",
                ))

    # ── LLM extraction ────────────────────────────────────────────────────────

    def extract_llm(self, entry: ParsedEntry) -> list[Triple]:
        if not self.use_llm:
            return []
        prompt = f"""Amarakosha Sanskrit lexical entry:
"{entry.source_line}"

Extract ONLY Sanskrit term relationships. Ontology: Medhya, Rasayana, 
cognitive concepts, Medhya Rasayana herbs.

Allowed relations: SYNONYM_OF, ASSOCIATED_WITH, RELATED_TO, TYPE_OF, ENHANCES, SUPPORTS

Return JSON array only. Empty array [] if nothing valid found.
[{{"subject":"X","relation":"REL","object":"Y"}}]"""
        try:
            resp = self._groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role":"user","content":prompt}],
                temperature=0.1, max_tokens=300,
            )
            raw = re.sub(r"^```json|^```|```$","",
                         resp.choices[0].message.content.strip()).strip()
            data = json.loads(raw)
            triples = []
            for item in data:
                if all(k in item for k in ["subject","relation","object"]):
                    s, r, o = item["subject"], item["relation"], item["object"]
                    if r in ALL_RELATIONS and validate_concept(s)[0] and validate_concept(o)[0]:
                        triples.append(Triple(s, r, o, "llm", 0.80))
            time.sleep(GROQ_DELAY)
            return triples
        except Exception as e:
            print(f"  LLM error: {e}")
            return []

    # ── Main ─────────────────────────────────────────────────────────────────

    def extract_all(self, entries: list[ParsedEntry]):
        self.load_seeds()

        rule_count = llm_count = 0

        for entry in entries:
            self.register_nodes(entry)
            rule_triples = self.extract_rules(entry)
            for t in rule_triples:
                self.add_triple(t)
            rule_count += len(rule_triples)

            if not rule_triples and self.use_llm:
                llm_triples = self.extract_llm(entry)
                for t in llm_triples:
                    self.add_triple(t)
                llm_count += len(llm_triples)

        print(f"  Before distance filter: {len(self.nodes)} nodes, {len(self.triples)} triples")
        self.filter_by_graph_distance()

        self.report.print_report()
        print(f"  Rule triples : {rule_count}  |  LLM triples: {llm_count}")

    def export_json(self, path: str):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "nodes": [
                    {"name":n.name,"label":n.label,"category":n.category,
                     "description":n.description,"sanskrit":n.sanskrit,
                     "latin":n.latin,"source":n.source}
                    for n in self.nodes
                ],
                "triples": [
                    {"subject":t.subject,"relation":t.relation,
                     "object":t.object,"source":t.source,"confidence":t.confidence}
                    for t in self.triples
                ],
            }, f, indent=2, ensure_ascii=False)
        print(f"  Exported → {path}")