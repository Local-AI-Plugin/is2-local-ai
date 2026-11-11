"""Small trusted HTTP client. Do not expose update() as an agent tool."""
import os
import re
from pathlib import Path

import requests
from rdflib import Graph, Namespace

BASE = os.environ.get("FUSEKI_URL", "http://127.0.0.1:3030/kg").rstrip("/")
ROOT = Path(__file__).resolve().parent
NS = "https://example.org/local-ai/"
SCHEMA = NS + "graph/schema"
ACCEPTED = NS + "graph/accepted"
INFERRED = NS + "graph/inferred"
STAGING = NS + "graph/staging"
SH = Namespace("http://www.w3.org/ns/shacl#")


def query(sparql):
    response = requests.post(
        BASE + "/sparql", data={"query": sparql},
        headers={"Accept": "application/sparql-results+json"}, timeout=(3, 10)
    )
    response.raise_for_status()
    return response.json()


def update(sparql):
    response = requests.post(
        BASE + "/update", data=sparql.encode(),
        headers={"Content-Type": "application/sparql-update"}, timeout=(3, 10)
    )
    response.raise_for_status()


def put_graph(iri, turtle):
    response = requests.put(
        BASE + "/data", params={"graph": iri}, data=turtle.encode(),
        headers={"Content-Type": "text/turtle"}, timeout=(3, 10)
    )
    response.raise_for_status()


def validate_graph(iri):
    response = requests.post(
        BASE + "/shacl", params={"graph": iri},
        data=(ROOT / "shapes.ttl").read_bytes(),
        headers={"Content-Type": "text/turtle", "Accept": "text/turtle"},
        timeout=(3, 10)
    )
    response.raise_for_status()
    report = Graph().parse(data=response.text, format="turtle")
    values = [v.toPython() for v in report.objects(None, SH.conforms)]
    if values != [True]:
        raise ValueError("SHACL rejected the graph:\n" + response.text)
    return True


def classify_update():
    # Restricted subclass closure, NOT a complete RDFS or OWL reasoner.
    # One update request publishes accepted data and refreshed classifications.
    return f"""PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
COPY GRAPH <{STAGING}> TO GRAPH <{ACCEPTED}>;
CLEAR SILENT GRAPH <{INFERRED}>;
INSERT {{ GRAPH <{INFERRED}> {{ ?item a ?parent }} }}
WHERE {{
  GRAPH <{ACCEPTED}> {{ ?item a ?child }}
  GRAPH <{SCHEMA}> {{ ?child rdfs:subClassOf+ ?parent }}
  FILTER NOT EXISTS {{ GRAPH <{ACCEPTED}> {{ ?item a ?parent }} }}
}}
"""


def load_demo():
    # This bootstrap REPLACES schema/staging/accepted/inferred demo graphs.
    # Single trusted writer; see guide for multi-writer transaction requirements.
    put_graph(SCHEMA, (ROOT / "ontology.ttl").read_text())
    put_graph(STAGING, (ROOT / "facts.ttl").read_text())
    validate_graph(STAGING)
    update(classify_update())


def lookup_task(task_id):
    if not isinstance(task_id, str) or not re.fullmatch(r"task[0-9]{1,8}", task_id):
        raise ValueError("task_id must be task followed by 1–8 digits")
    # Only the validated identifier is interpolated; no free-form SPARQL input.
    return query(f"""
PREFIX ex: <{NS}>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?type ?label ?status ?evidence
WHERE {{
  VALUES ?typeGraph {{ <{ACCEPTED}> <{INFERRED}> }}
  GRAPH ?typeGraph {{ ex:{task_id} a ?type }}
  GRAPH <{ACCEPTED}> {{
    ex:{task_id} rdfs:label ?label ; ex:status ?status ; ex:supportedBy ?evidence .
  }}
}} ORDER BY ?type LIMIT 20
""")


if __name__ == "__main__":
    import json
    load_demo()
    print(json.dumps(lookup_task("task1"), indent=2))
