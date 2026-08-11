# extractor.py
# ─────────────────────────────────────────────────────────────────────────────
# Converts ParsedEntry → triples.
# Every candidate node is validated before being added.
# Graph-distance filtering: concepts must be within MAX_GRAPH_HOPS of roots.
# ─────────────────────────────────────────────────────────────────────────────

import json
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from pdf_parser import ParsedEntry
from validator import (
    validate_concept, validate_pdf_term, ValidationReport, is_domain_relevant,
    has_domain_devanagari_marker, has_strong_domain_signal,
)
from config import (
    ROOT_CONCEPTS, SEED_CONCEPTS, SEED_HERBS, SEED_RELATIONSHIPS,
    SYNONYM_MAP, ALL_RELATIONS, MAX_GRAPH_HOPS,
    LABEL_ROOT, LABEL_CONCEPT, LABEL_HERB, LABEL_PROPERTY,
    GROQ_API_KEY, GROQ_MODEL, GROQ_DELAY,
    REL_SYNONYM_OF, REL_ASSOCIATED_WITH,
    REL_TYPE_OF, REL_PART_OF,
    PRIORITY_RELATIONS, SECONDARY_RELATIONS,
    MEDHYA_KEYWORDS, RASAYANA_KEYWORDS, HERB_KEYWORDS,
    MEDHYA_DEVANAGARI_MARKERS, RASAYANA_DEVANAGARI_MARKERS, HERB_DEVANAGARI_MARKERS,
    MAX_GRAPH_NODES,
)

COGNITIVE_CONCEPTS = {c["name"] for c in SEED_CONCEPTS if c["category"] == "cognitive"}
RASAYANA_CONCEPTS  = {c["name"] for c in SEED_CONCEPTS if c["category"] == "rasayana"}
PROPERTY_CONCEPTS  = {c["name"] for c in SEED_CONCEPTS if c["category"] == "property"}
ROOT_NAMES         = {r["name"] for r in ROOT_CONCEPTS}
HERB_NAMES         = {h["name"] for h in SEED_HERBS}


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
        lower = name.lower()
        if any(k in lower for k in HERB_KEYWORDS):
            return LABEL_HERB
        return LABEL_CONCEPT

    def _entry_is_domain(self, entry: ParsedEntry) -> bool:
        return (
            entry.domain in {"medhya", "rasayana", "herb"}
            or is_domain_relevant(entry.source_line)
            or has_domain_devanagari_marker(entry.source_line)
        )

    def _keyword_in_term(self, keyword: str, term: str) -> bool:
        if any(ord(c) > 127 for c in keyword):
            return keyword in term
        return bool(re.search(
            r"(?<![a-z])" + re.escape(keyword.lower()) + r"(?![a-z])",
            term.lower(),
        ))

    def _has_medhya_signal(self, term: str) -> bool:
        if term in COGNITIVE_CONCEPTS:
            return True
        if any(self._keyword_in_term(k, term) for k in MEDHYA_KEYWORDS if len(k) >= 4):
            return True
        return any(m in term for m in MEDHYA_DEVANAGARI_MARKERS)

    def _has_rasayana_signal(self, term: str) -> bool:
        if term in RASAYANA_CONCEPTS:
            return True
        if any(self._keyword_in_term(k, term) for k in RASAYANA_KEYWORDS if len(k) >= 4):
            return True
        return any(m in term for m in RASAYANA_DEVANAGARI_MARKERS)

    def _has_herb_signal(self, term: str) -> bool:
        if term in HERB_NAMES:
            return True
        if any(self._keyword_in_term(k, term) for k in HERB_KEYWORDS if len(k) >= 4):
            return True
        return any(m in term for m in HERB_DEVANAGARI_MARKERS)

    def _pick_anchor_term(self, terms: list[str]) -> str | None:
        """First term with explicit domain signal, else first term if group qualifies."""
        for t in terms:
            if self._has_medhya_signal(t) or self._has_rasayana_signal(t) or self._has_herb_signal(t):
                return t
        return None

    def _add_synonym_group(self, terms: list[str], triples: list[Triple]):
        """
        Rich synonym mesh: star-to-head (bidirectional) + chain links.
        Amarakosha lists are equivalence classes — more edges = better coverage.
        """
        if len(terms) < 2:
            return

        head = terms[0]
        for t in terms[1:]:
            if t == head:
                continue
            triples.append(Triple(t, REL_SYNONYM_OF, head, "rule"))
            triples.append(Triple(head, REL_SYNONYM_OF, t, "rule"))

        for i in range(len(terms) - 1):
            a, b = terms[i], terms[i + 1]
            if a != b:
                triples.append(Triple(a, REL_SYNONYM_OF, b, "rule"))

    def _assign_subgroup(self, terms: list[str], triples: list[Triple]):
        """Link domain terms to Medhya/Rasayana subgroups via TYPE_OF and PART_OF."""
        if not terms:
            return

        anchor = self._pick_anchor_term(terms)
        if not anchor or anchor in ROOT_NAMES:
            return

        if self._has_herb_signal(anchor):
            triples.append(Triple(anchor, REL_TYPE_OF, "Medhya Rasayana", "rule"))
            return

        if self._has_medhya_signal(anchor):
            triples.append(Triple(anchor, REL_TYPE_OF, "Medhya", "rule"))
            triples.append(Triple(anchor, REL_PART_OF, "Medhya", "rule"))
            return

        if self._has_rasayana_signal(anchor):
            triples.append(Triple(anchor, REL_TYPE_OF, "Rasayana", "rule"))
            triples.append(Triple(anchor, REL_PART_OF, "Rasayana", "rule"))

    def add_node(self, node: Node, entry_is_domain: bool = False) -> bool:
        """Validates before adding. Returns True if added."""
        if node.source == "seed":
            valid, reason = True, "seed"
        elif node.source == "amarakosha":
            valid, reason = validate_pdf_term(node.name, entry_is_domain)
        else:
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

    def _valid_pdf_term(
        self, term: str, entry_domain: bool, in_synonym_group: bool = False,
    ) -> bool:
        return validate_pdf_term(term, entry_domain, in_synonym_group=in_synonym_group)[0]

    # ── Rule-based extraction ─────────────────────────────────────────────────

    def extract_rules(self, entry: ParsedEntry) -> list[Triple]:
        triples = []
        entry_domain = self._entry_is_domain(entry)

        if entry.format_type == "synonym_group":
            terms = [self.resolve_canonical(t) for t in entry.synonyms]
            terms = [
                t for t in terms
                if self._valid_pdf_term(t, entry_domain, in_synonym_group=True)
            ]

            if len(terms) < 2:
                return []

            self._add_synonym_group(terms, triples)
            self._assign_subgroup(terms, triples)

        elif entry.format_type == "concept_desc":
            if not entry.terms:
                return []
            term = self.resolve_canonical(entry.terms[0])
            if not self._valid_pdf_term(term, entry_domain):
                return []

            for syn in entry.synonyms:
                canon = self.resolve_canonical(syn)
                if self._valid_pdf_term(canon, entry_domain, in_synonym_group=True):
                    triples.append(Triple(term, REL_SYNONYM_OF, canon, "rule"))
                    triples.append(Triple(canon, REL_SYNONYM_OF, term, "rule"))

            all_terms = [term] + [self.resolve_canonical(s) for s in entry.synonyms]
            all_terms = list(dict.fromkeys(all_terms))
            self._assign_subgroup(all_terms, triples)

        elif entry.format_type == "term_list":
            terms = []
            for raw in entry.terms:
                term = self.resolve_canonical(raw)
                if self._valid_pdf_term(term, entry_domain, in_synonym_group=True):
                    terms.append(term)

            if len(terms) >= 2:
                self._add_synonym_group(terms, triples)
            self._assign_subgroup(terms, triples)

        return triples

    # ── Graph-distance filter ─────────────────────────────────────────────────

    def filter_by_graph_distance(self):
        """
        Remove any node that is more than MAX_GRAPH_HOPS away from
        Medhya, Rasayana, or Medhya Rasayana.
        """
        adj = defaultdict(set)
        for t in self.triples:
            adj[t.subject].add(t.object)
            adj[t.object].add(t.subject)

        roots = {"Medhya", "Rasayana", "Medhya Rasayana"}
        reachable = set()

        queue = deque()
        for root in roots:
            queue.append((root, 0))
            reachable.add(root)

        while queue:
            node, dist = queue.popleft()
            if dist >= MAX_GRAPH_HOPS:
                continue
            for neighbor in adj.get(node, []):
                if neighbor not in reachable:
                    reachable.add(neighbor)
                    queue.append((neighbor, dist + 1))

        seed_names = {n.name for n in self.nodes if n.source == "seed"}
        reachable |= seed_names

        before = len(self.nodes)
        self.nodes = [n for n in self.nodes if n.name in reachable]
        self._node_index = {n.name for n in self.nodes}

        self.triples = [
            t for t in self.triples
            if t.subject in reachable and t.object in reachable
        ]
        self._triple_set = {(t.subject, t.relation, t.object) for t in self.triples}

        removed = before - len(self.nodes)
        print(f"  Graph-distance filter: removed {removed} nodes beyond {MAX_GRAPH_HOPS} hops")
        print(f"  Remaining: {len(self.nodes)} nodes, {len(self.triples)} triples")

    def prune_to_target(self, max_total: int = MAX_GRAPH_NODES):
        """Keep seeds + priority-relation nodes; trim secondary triples if over cap."""
        if len(self.nodes) <= max_total:
            self._trim_secondary_triples()
            return

        adj = defaultdict(set)
        priority_nodes: set[str] = set()
        for t in self.triples:
            adj[t.subject].add(t.object)
            adj[t.object].add(t.subject)
            if t.relation in PRIORITY_RELATIONS:
                priority_nodes.add(t.subject)
                priority_nodes.add(t.object)

        roots = {"Medhya", "Rasayana", "Medhya Rasayana"}
        dist: dict[str, int] = {}
        queue = deque((r, 0) for r in roots)
        for r in roots:
            dist[r] = 0

        while queue:
            node, d = queue.popleft()
            for nb in adj.get(node, []):
                if nb not in dist:
                    dist[nb] = d + 1
                    queue.append((nb, d + 1))

        def score(node: Node) -> tuple:
            hop = dist.get(node.name, 50)
            bonus = 0
            if node.name in priority_nodes:
                bonus -= 20
            if self._has_medhya_signal(node.name):
                bonus -= 3
            if self._has_rasayana_signal(node.name):
                bonus -= 3
            if self._has_herb_signal(node.name):
                bonus -= 2
            return (hop + bonus, len(node.name), node.name)

        seeds     = [n for n in self.nodes if n.source == "seed"]
        seed_names = {n.name for n in seeds}
        keep_names = seed_names | priority_nodes

        pdf_nodes = sorted(
            [n for n in self.nodes if n.source != "seed" and n.name not in keep_names],
            key=score,
        )
        budget = max(max_total - len(keep_names), 0)
        keep_names |= {n.name for n in pdf_nodes[:budget]}

        before = len(self.nodes)
        self.nodes = [n for n in self.nodes if n.name in keep_names]
        self._node_index = {n.name for n in self.nodes}
        self.triples = [
            t for t in self.triples
            if t.subject in keep_names and t.object in keep_names
        ]
        self._triple_set = {(t.subject, t.relation, t.object) for t in self.triples}
        self._trim_secondary_triples()
        print(
            f"  Quality prune: kept {len(self.nodes)} nodes "
            f"(cap {max_total}, removed {before - len(self.nodes)})"
        )

    def _trim_secondary_triples(self):
        """Drop secondary PDF triples when graph is large; keep seeds untouched."""
        pdf_secondary = [
            t for t in self.triples
            if t.source != "seed" and t.relation in SECONDARY_RELATIONS
        ]
        if not pdf_secondary:
            return

        priority_count = sum(1 for t in self.triples if t.relation in PRIORITY_RELATIONS)
        if priority_count < 200:
            return

        before = len(self.triples)
        self.triples = [
            t for t in self.triples
            if t.source == "seed" or t.relation not in SECONDARY_RELATIONS
        ]
        self._triple_set = {(t.subject, t.relation, t.object) for t in self.triples}
        removed = before - len(self.triples)
        if removed:
            print(f"  Trimmed {removed} secondary PDF triples (kept synonym/subgroup first)")

    # ── Register node from entry ──────────────────────────────────────────────

    def register_nodes(self, entry: ParsedEntry):
        entry_domain = self._entry_is_domain(entry)
        in_group = entry.format_type in {"synonym_group", "term_list"}
        names = list(dict.fromkeys(
            [self.resolve_canonical(t) for t in entry.terms]
            + [self.resolve_canonical(s) for s in entry.synonyms]
        ))
        for name in names:
            if name and name not in self._node_index:
                if not self._valid_pdf_term(name, entry_domain, in_synonym_group=in_group):
                    continue
                self.add_node(Node(
                    name=name,
                    label=self.resolve_label(name),
                    category=entry.domain,
                    description=entry.description,
                    source="amarakosha",
                ), entry_is_domain=entry_domain)

    # ── LLM extraction ────────────────────────────────────────────────────────

    def extract_llm(self, entry: ParsedEntry) -> list[Triple]:
        if not self.use_llm:
            return []
        prompt = f"""Amarakosha Sanskrit lexical entry:
"{entry.source_line}"

Extract ONLY Sanskrit term relationships. Ontology: Medhya, Rasayana, 
cognitive concepts, Medhya Rasayana herbs.

Allowed relations: SYNONYM_OF, TYPE_OF, PART_OF (preferred), ASSOCIATED_WITH, RELATED_TO

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
                    if r in ALL_RELATIONS and validate_pdf_term(s, True)[0] and validate_pdf_term(o, True)[0]:
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
        self.prune_to_target()

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
