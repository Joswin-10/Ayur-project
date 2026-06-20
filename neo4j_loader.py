# neo4j_loader.py
# ─────────────────────────────────────────────────────────────────────────────
# Loads the graph into Neo4j using MERGE — never creates duplicates.
# ─────────────────────────────────────────────────────────────────────────────

from neo4j import GraphDatabase
from extractor import Node, Triple
from config import (
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    NEO4J_DATABASE,
    ALLOWED_LABELS
)

BATCH_SIZE = 500


class Neo4jLoader:

    def __init__(self):
        self.driver = GraphDatabase.driver(
            NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
        )
        print(f"  Neo4j connected → {NEO4J_URI}")

    def close(self):
        self.driver.close()

    def safe_label(self, label: str) -> str:
        return label if label in ALLOWED_LABELS else "Concept"

    # ── Schema ────────────────────────────────────────────────────────────────
    def create_constraints(self):
        with self.driver.session(database=NEO4J_DATABASE) as s:
            for label in ALLOWED_LABELS:
                try:
                    s.run(
                        f"CREATE CONSTRAINT IF NOT EXISTS "
                        f"FOR (n:{label}) REQUIRE n.name IS UNIQUE"
                    )
                except Exception:
                    pass
        print("  Constraints ready.")

    def clear_all(self):
        with self.driver.session(database=NEO4J_DATABASE) as s:
            s.run("MATCH (n) DETACH DELETE n")
        print("  Graph cleared.")

    # ── Node insertion ────────────────────────────────────────────────────────
    def insert_nodes(self, nodes: list[Node]):
        total = 0
        for i in range(0, len(nodes), BATCH_SIZE):
            batch = nodes[i:i + BATCH_SIZE]
            with self.driver.session(database=NEO4J_DATABASE) as s:
                for node in batch:
                    label = self.safe_label(node.label)
                    try:
                        s.run(f"""
                            MERGE (n:{label} {{name: $name}})
                            ON CREATE SET
                                n.category    = $category,
                                n.description = $description,
                                n.sanskrit    = $sanskrit,
                                n.latin       = $latin,
                                n.source      = $source
                            ON MATCH SET
                                n.description = CASE
                                    WHEN n.description = '' THEN $description
                                    ELSE n.description END,
                                n.sanskrit = CASE
                                    WHEN n.sanskrit = '' THEN $sanskrit
                                    ELSE n.sanskrit END,
                                n.latin = CASE
                                    WHEN n.latin = '' THEN $latin
                                    ELSE n.latin END
                        """,
                        name=node.name, category=node.category,
                        description=node.description, sanskrit=node.sanskrit,
                        latin=node.latin, source=node.source)
                        total += 1
                    except Exception as e:
                        print(f"  ⚠ Node failed: {node.name} — {e}")
        print(f"  Nodes inserted: {total}")

    # ── Relationship insertion ────────────────────────────────────────────────
    def insert_triples(self, triples: list[Triple]):
        total = skipped = 0
        for i in range(0, len(triples), BATCH_SIZE):
            batch = triples[i:i + BATCH_SIZE]
            with self.driver.session(database=NEO4J_DATABASE) as s:
                for t in batch:
                    try:
                        s.run(f"""
                            MATCH (a {{name: $subj}})
                            MATCH (b {{name: $obj}})
                            MERGE (a)-[r:{t.relation}]->(b)
                            ON CREATE SET
                                r.source     = $source,
                                r.confidence = $confidence,
                                r.count      = 1
                            ON MATCH SET
                                r.count = r.count + 1
                        """,
                        subj=t.subject, obj=t.object,
                        source=t.source, confidence=t.confidence)
                        total += 1
                    except Exception as e:
                        skipped += 1
                        if skipped <= 5:
                            print(f"  ⚠ Rel failed: {t.subject}→{t.relation}→{t.object}: {e}")
        print(f"  Relations inserted: {total}  |  failed: {skipped}")

    # ── Summary ───────────────────────────────────────────────────────────────
    def print_summary(self):
        with self.driver.session(database=NEO4J_DATABASE) as s:
            nodes  = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels   = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            labels = s.run(
                "MATCH (n) RETURN DISTINCT labels(n)[0] AS l, count(n) AS c ORDER BY c DESC"
            ).data()
        print(f"\n── Neo4j Graph ─────────────────────────────────────────────")
        print(f"  Total nodes         : {nodes}")
        print(f"  Total relationships : {rels}")
        for row in labels:
            print(f"  {row['l']:<24}: {row['c']} nodes")

    # ── Full load ─────────────────────────────────────────────────────────────
    def load(self, nodes: list[Node], triples: list[Triple], clear: bool = False):
        self.create_constraints()
        if clear:
            self.clear_all()
        print(f"\n  Loading {len(nodes)} nodes...")
        self.insert_nodes(nodes)
        print(f"  Loading {len(triples)} relationships...")
        self.insert_triples(triples)
        self.print_summary()