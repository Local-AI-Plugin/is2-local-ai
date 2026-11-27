"""Load the UGV mission-planning ontology and Scenario 1 individuals into Fuseki.

Both Protégé exports are RDF/XML and go in unchanged. By default they REPLACE
the dataset's default graph, which is what the competency-question queries
read (they have no GRAPH/FROM clauses). The demo named graphs used by
client.py/smoke.py are not touched.

Later, mission data may live in named staging/active graphs; pass --graph IRI
to load there instead (queries would then need FROM <IRI>).
"""
import argparse
from pathlib import Path

from client import ROOT, post_graph, put_graph, query

DOCS = ROOT.parents[1] / "docs" / "knowledge"
ONTOLOGY = DOCS / "UGV_Mission_Planning_Ontology.rdf"
SCENARIO = DOCS / "UGV_Scenario_1_Individuals.rdf"
RDF_XML = "application/rdf+xml"


def triple_count(graph=None):
    where = "{ ?s ?p ?o }" if graph is None else f"{{ GRAPH <{graph}> {{ ?s ?p ?o }} }}"
    rows = query(f"SELECT (COUNT(*) AS ?n) WHERE {where}")["results"]["bindings"]
    return int(rows[0]["n"]["value"])


def load(graph=None, ontology=ONTOLOGY, scenario=SCENARIO):
    put_graph(graph, Path(ontology).read_bytes(), RDF_XML)   # replace
    post_graph(graph, Path(scenario).read_bytes(), RDF_XML)  # append
    return triple_count(graph)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--graph", help="named graph IRI (default: the default graph)")
    parser.add_argument("--ontology", default=ONTOLOGY, type=Path)
    parser.add_argument("--scenario", default=SCENARIO, type=Path)
    args = parser.parse_args()
    count = load(args.graph, args.ontology, args.scenario)
    print(f"Loaded {count} triples into {args.graph or 'the default graph'}")


if __name__ == "__main__":
    main()
