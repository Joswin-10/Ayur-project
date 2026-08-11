# main.py
# ─────────────────────────────────────────────────────────────────────────────
# Amarakosha PDF → Medhya Rasayana Knowledge Graph
#
# Usage:
#   python main.py --pdf amarakosha.pdf --neo4j
#   python main.py --pdf amarakosha.pdf --neo4j --clear
#   python main.py --pdf amarakosha.pdf --llm --neo4j
#   python main.py --pdf amarakosha.pdf           # export JSON only, no Neo4j
#   python main.py --pdf scanned.pdf --ocr        # scanned/image PDF (needs Tesseract)
#
# Flags:
#   --pdf        path to Amarakosha PDF (required)
#   --neo4j      load graph into Neo4j
#   --clear      wipe Neo4j before loading (use on first run)
#   --llm        use Groq LLM for ambiguous entries
#   --ocr        OCR scanned pages with Tesseract (Sanskrit/Devanagari)
#   --all-lines  parse ALL lines, not just Medhya/Rasayana relevant ones
# ─────────────────────────────────────────────────────────────────────────────

import argparse
import os

from pdf_parser    import AmarakoshaParser
from extractor     import MedhyaExtractor
from graph_builder import GraphBuilder
from neo4j_loader  import Neo4jLoader
from config        import OUTPUT_TRIPLES_PATH, OUTPUT_DIR


def main():
    parser = argparse.ArgumentParser(
        description="Amarakosha PDF → Medhya Rasayana Knowledge Graph"
    )
    parser.add_argument("--pdf",       required=True,
                        help="Path to Amarakosha PDF")
    parser.add_argument("--neo4j",     action="store_true",
                        help="Load into Neo4j")
    parser.add_argument("--clear",     action="store_true",
                        help="Clear Neo4j before loading")
    parser.add_argument("--llm",       action="store_true",
                        help="Use LLM for ambiguous entries (needs GROQ_API_KEY)")
    parser.add_argument("--all-lines", action="store_true",
                        help="Parse all lines, not just Medhya/Rasayana relevant ones")
    parser.add_argument("--ocr",       action="store_true",
                        help="OCR scanned/image PDF pages (requires Tesseract + Sanskrit/Hindi pack)")
    parser.add_argument("--export",    default=OUTPUT_TRIPLES_PATH,
                        help=f"JSON export path (default: {OUTPUT_TRIPLES_PATH})")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"Error: PDF not found at '{args.pdf}'")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("\n" + "="*60)
    print("  AMARAKOSHA -> MEDHYA RASAYANA KNOWLEDGE GRAPH")
    print("="*60)

    # ── Step 1: Parse PDF ──────────────────────────────────────────────────
    print("\n[1/4] Parsing Amarakosha PDF")
    pdf_parser = AmarakoshaParser()
    try:
        entries = pdf_parser.parse(
            pdf_path=args.pdf,
            save_cleaned=True,
            use_ocr=args.ocr,
            parse_all_lines=args.all_lines,
        )
    except RuntimeError as exc:
        print(f"\n  Error: {exc}")
        return

    if not entries:
        print("\n  No entries extracted.")
        if not args.ocr:
            print("  Your PDF may be scanned — try: python main.py --pdf <file> --ocr")
        print("  Try running with --all-lines if the PDF has dense content.")
        print("  Also check output/cleaned_text.txt to inspect what was read.")
        return

    # ── Step 2: Extract triples ────────────────────────────────────────────
    print(f"\n[2/4] Extracting triples  (LLM={'on' if args.llm else 'off'})")
    extractor = MedhyaExtractor(use_llm=args.llm)
    extractor.extract_all(entries)
    extractor.export_json(args.export)

    # ── Step 3: Build graph ────────────────────────────────────────────────
    print("\n[3/4] Building graph structure")
    builder = GraphBuilder(extractor)
    builder.build()
    builder.summary()

    # ── Step 4: Neo4j ─────────────────────────────────────────────────────
    if args.neo4j:
        print("\n[4/4] Loading into Neo4j")
        loader = Neo4jLoader()
        loader.load(builder.get_nodes(), builder.get_triples(), clear=args.clear)
        loader.close()
        print_queries()
    else:
        print("\n[4/4] Neo4j — SKIPPED")
        print(f"       Triples saved to: {args.export}")
        print(f"       Run with --neo4j to load into the graph database.")

    print("\n" + "="*60)
    print("  DONE")
    print("="*60)
    print(f"""
Output files:
  {OUTPUT_TRIPLES_PATH:<40} ← all extracted triples (JSON)
  output/cleaned_text.txt                  ← cleaned PDF text for inspection
""")


def print_queries():
    print("""
── Cypher queries to try in Neo4j Browser ──────────────────────────

  # Full graph
  MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100

  # All Medhya Rasayana herbs
  MATCH (h:Herb)-[:TYPE_OF]->({name:'Medhya Rasayana'})
  RETURN h.name, h.latin, h.description

  # Seed ontology (semantic)
  MATCH ({name:'Medhya'})-[:ASSOCIATED_WITH]->(c)
  RETURN c.name, c.description ORDER BY c.name

  # Subgroup membership (TYPE_OF + PART_OF)
  MATCH (root) WHERE root.name IN ['Medhya','Rasayana','Medhya Rasayana']
  MATCH (n)-[r:TYPE_OF|PART_OF]->(root)
  RETURN n.name, type(r) AS relation, root.name AS subgroup

  # Synonyms under Medhya subgroup
  MATCH (n)-[:TYPE_OF|PART_OF]->({name:'Medhya'})
  OPTIONAL MATCH (n)-[:SYNONYM_OF]-(syn)
  RETURN n.name, collect(DISTINCT syn.name) AS synonyms

  # Synonym chains from Amarakosha
  MATCH (a)-[:SYNONYM_OF]-(b)
  RETURN a.name, b.name LIMIT 100

  # Herbs that enhance Smriti or Medha
  MATCH (h:Herb)-[:ENHANCES]->(c)
  WHERE c.name IN ['Smriti','Medha']
  RETURN h.name, c.name

  # Full subgraph around Brahmi
  MATCH (n {name:'Brahmi'})-[r*1..2]-(m) RETURN n, r, m

  # Nodes from Amarakosha (not seed)
  MATCH (n {source:'amarakosha'}) RETURN n.name, n.label, n.category

  # Auto-created nodes to review
  MATCH (n {source:'auto'}) RETURN n.name LIMIT 20
""")


if __name__ == "__main__":
    main()