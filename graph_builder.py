# graph_builder.py
# ─────────────────────────────────────────────────────────────────────────────
# Final assembly and validation before Neo4j insertion.
# Last line of defense — rejects any node that slipped through extractor.
# ─────────────────────────────────────────────────────────────────────────────

from collections import defaultdict
from extractor import Node, Triple, MedhyaExtractor
from validator import validate_concept, ValidationReport
from config    import LABEL_CONCEPT, ALL_RELATIONS


class GraphBuilder:

    def __init__(self, extractor: MedhyaExtractor):
        self.extractor    = extractor
        self.nodes:       dict[str, Node]  = {}
        self.triples:     list[Triple]     = []
        self._triple_set: set[tuple]       = set()
        self.report       = ValidationReport()

    def build(self):
        print("\n  GraphBuilder: final validation pass...")

        accepted_nodes = 0
        rejected_nodes = 0

        for node in self.extractor.nodes:
            # Seed nodes always pass
            if node.source == "seed":
                self.nodes[node.name] = node
                accepted_nodes += 1
                continue

            valid, reason = validate_concept(node.name)
            self.report.record(node.name, valid, reason)

            if valid:
                self.nodes[node.name] = node
                accepted_nodes += 1
            else:
                rejected_nodes += 1

        # Only add triples where BOTH endpoints passed validation
        accepted_rels = 0
        rejected_rels = 0

        for triple in self.extractor.triples:
            key = (triple.subject, triple.relation, triple.object)
            if key in self._triple_set:
                continue
            if triple.relation not in ALL_RELATIONS:
                rejected_rels += 1
                continue
            if triple.subject not in self.nodes or triple.object not in self.nodes:
                rejected_rels += 1
                continue

            self.triples.append(triple)
            self._triple_set.add(key)
            accepted_rels += 1

        print(f"  Nodes   → accepted: {accepted_nodes}  rejected: {rejected_nodes}")
        print(f"  Triples → accepted: {accepted_rels}  rejected: {rejected_rels}")

        self.report.print_report()

    def summary(self):
        print("\n── Final Graph Summary ─────────────────────────────────────")

        by_label = defaultdict(int)
        for n in self.nodes.values():
            by_label[n.label] += 1
        for label, count in sorted(by_label.items()):
            print(f"  {label:<24}: {count} nodes")

        print()
        by_rel = defaultdict(int)
        for t in self.triples:
            by_rel[t.relation] += 1
        for rel, count in sorted(by_rel.items(), key=lambda x: -x[1]):
            print(f"  {rel:<24}: {count} triples")

        print()
        by_source = defaultdict(int)
        for t in self.triples:
            by_source[t.source] += 1
        for src, count in sorted(by_source.items()):
            print(f"  source={src:<14}: {count} triples")

        print("────────────────────────────────────────────────────────────")

    def get_nodes(self)   -> list[Node]:   return list(self.nodes.values())
    def get_triples(self) -> list[Triple]: return self.triples