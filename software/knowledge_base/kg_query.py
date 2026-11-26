"""Standalone KG query: run a saved competency-question SPARQL query on Fuseki,
then have the local Qwen model answer using only the returned rows (Test 1).

The graph is queried by Python before Qwen is called. Qwen never writes SPARQL:
it only sees the rows. kg_agent.py reuses run_query() as a tool (Test 2).

    python kg_query.py cq1_1 --rows-only
    python kg_query.py cq1_1
    python kg_query.py cq1_1 --task "Observe an inspection area" --mission MissionAlphaBravo
"""
import argparse
import json
import os
import re
import time
from pathlib import Path

from rdflib import Literal

from client import ROOT, query

QUERIES = ROOT / "queries"
LOG = ROOT / "logs" / "kg_runs.jsonl"
DEFAULT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"  # same default as software/rag/rag.py

PREFIXES = {
    "ugv": "https://example.org/is2/ugv-mission-planning#",
    "s1": "https://example.org/is2/ugv-mission-planning/scenario-1#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}
# Literal properties an entity can be referred to by, besides its local name.
LABEL_PROPS = ["rdfs:label", "ugv:taskName", "ugv:missionId", "ugv:capabilityName", "ugv:areaId"]
SAFE_IRI = re.compile(r'^https?://[^\s<>"{}|\\^`]+$')
MAX_NAME = 200

SYSTEM_MESSAGE = (
    "Answer using only the supplied graph results. "
    "Identify the entities supporting your answer. "
    "If a requested detail is missing, say which detail is missing."
)


def load_registry():
    return json.loads((QUERIES / "registry.json").read_text(encoding="utf-8"))


def registry_entry(query_id):
    registry = load_registry()
    if not isinstance(query_id, str) or query_id not in registry:
        raise ValueError(f"unknown query_id {query_id!r}; known: {sorted(registry)}")
    return registry[query_id]


def expand(name):
    prefix, _, local = name.partition(":")
    return PREFIXES[prefix] + local


def compact_iri(iri):
    for prefix, ns in PREFIXES.items():
        if iri.startswith(ns) and re.fullmatch(r"[\w.-]+", iri[len(ns):]):
            return f"{prefix}:{iri[len(ns):]}"
    return iri


def compact(rows):
    """SPARQL JSON bindings -> [{var: 'prefix:name' or literal value}]."""
    return [
        {var: compact_iri(b["value"]) if b["type"] == "uri" else b["value"]
         for var, b in row.items()}
        for row in rows
    ]


def prefix_block():
    return "".join(f"PREFIX {p}: <{ns}>\n" for p, ns in PREFIXES.items())


def class_members(cls, limit=20):
    rows = query(f"{prefix_block()}SELECT DISTINCT ?s WHERE {{ ?s a {cls} }} "
                 f"ORDER BY ?s LIMIT {limit}")["results"]["bindings"]
    return [compact_iri(r["s"]["value"]) for r in rows]


def resolve(name, cls):
    """Map a user/model-supplied name to exactly one IRI of class `cls`.

    Matches (case-insensitively) the local name or a label-like literal. The
    text only ever enters SPARQL as an escaped string literal.
    """
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME:
        raise ValueError(f"entity name must be a non-empty string of at most {MAX_NAME} chars")
    name = name.strip()
    # Accept "s1:ObserveAreaTask" or a full IRI as well as a bare name.
    forms = {name.lower(), re.sub(r"^.*[#:/]", "", name).lower()}
    candidates = ", ".join(Literal(f).n3() for f in sorted(forms))
    rows = query(f"""{prefix_block()}
SELECT DISTINCT ?s WHERE {{
  ?s a {cls} .
  OPTIONAL {{ ?s ?labelProp ?label . VALUES ?labelProp {{ {' '.join(LABEL_PROPS)} }} }}
  FILTER (LCASE(REPLACE(STR(?s), "^.*[#/]", "")) IN ({candidates})
          || LCASE(STR(?label)) IN ({candidates}))
}} LIMIT 5""")["results"]["bindings"]
    iris = [r["s"]["value"] for r in rows]
    if not iris:
        raise LookupError(f"no {cls} matches {name!r}; known: {class_members(cls)}")
    if len(iris) > 1:
        raise LookupError(f"{name!r} is ambiguous: {[compact_iri(i) for i in iris]}")
    if not SAFE_IRI.match(iris[0]):
        raise ValueError(f"refusing to substitute unsafe IRI {iris[0]!r}")
    return iris[0]


def build_query(query_id, **entities):
    """Return (sparql, resolved) for a registry query.

    No entities: the saved query verbatim. With entities: the template, with
    each {{param}} replaced by a resolved <IRI>, or UNDEF (any) when omitted.
    """
    entry = registry_entry(query_id)
    params = entry.get("params", {})
    entities = {k: v for k, v in entities.items() if v not in (None, "")}
    unknown = set(entities) - set(params)
    if unknown:
        raise ValueError(f"{query_id} takes {sorted(params)}, not {sorted(unknown)}")
    if not entities:
        return (QUERIES / entry["file"]).read_text(encoding="utf-8"), {}
    sparql = (QUERIES / entry["template"]).read_text(encoding="utf-8")
    resolved = {}
    for param, spec in params.items():
        if param in entities:
            iri = resolve(entities[param], spec["class"])
            resolved[param] = compact_iri(iri)
            term = f"<{iri}>"
        else:
            term = "UNDEF"
        sparql = sparql.replace("{{" + param + "}}", term)
    return sparql, resolved


def run_query(query_id, **entities):
    sparql, _ = build_query(query_id, **entities)
    return query(sparql)["results"]["bindings"]


def same_rows(rows, expected, ignore=()):
    def norm(rs):
        return sorted(json.dumps({k: v for k, v in r.items() if k not in ignore}, sort_keys=True)
                      for r in rs)
    return norm(rows) == norm(expected)


def llm_config():
    base = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    return {
        "model": os.environ.get("KG_MODEL", DEFAULT_MODEL),
        "model_server": base + "/v1",  # Ollama's OpenAI-compatible API
        "api_key": "EMPTY",
        "generate_cfg": {"temperature": 0, "seed": 42},
    }


def check_llm(cfg=None):
    """Fail fast with a fix-it message if Ollama or the model isn't reachable."""
    import requests

    cfg = cfg or llm_config()
    base = cfg["model_server"].removesuffix("/v1")
    try:
        tags = requests.get(base + "/api/tags", timeout=(3, 10)).json()
    except requests.RequestException:
        raise SystemExit(
            f"error: no Ollama at {base}. Start one that listens on the host, e.g. "
            "`docker start local-ai-ollama` (stop any other Ollama using the "
            "local-ai-models volume first), or set OLLAMA_URL. "
            "Use --rows-only to skip the LLM.")
    names = {m["name"] for m in tags.get("models", [])}
    if cfg["model"] not in names:
        raise SystemExit(f"error: model {cfg['model']!r} not pulled on {base}; "
                         f"available: {sorted(names)}. Set KG_MODEL or `ollama pull` it.")


def final_content(messages):
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("content"):
            return message["content"]
    return ""


def answer_from_kg(question, rows, llm_cfg):
    if not rows:
        return "The graph returned no matching facts for this question."
    from qwen_agent.agents import Assistant  # imported lazily: --rows-only needs no LLM

    assistant = Assistant(llm=llm_cfg, system_message=SYSTEM_MESSAGE)
    evidence = json.dumps(rows, ensure_ascii=False)
    messages = [{
        "role": "user",
        "content": f"Question:\n{question}\n\nGraph results:\n{evidence}",
    }]
    final_messages = []
    for update in assistant.run(messages=messages):
        final_messages = update
    return final_content(final_messages)


def log_run(record):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **record},
                           ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Fuseki -> Python -> Qwen (Test 1)")
    parser.add_argument("query_id")
    parser.add_argument("--task")
    parser.add_argument("--mission")
    parser.add_argument("--question", help="defaults to the registry wording")
    parser.add_argument("--rows-only", action="store_true", help="skip the LLM")
    args = parser.parse_args()

    try:
        entry = registry_entry(args.query_id)
        sparql, resolved = build_query(args.query_id, task=args.task, mission=args.mission)
    except (LookupError, ValueError) as exc:
        parser.exit(2, f"error: {exc}\n")
    question = args.question or entry["question"]
    rows = compact(query(sparql)["results"]["bindings"])

    print("Rows from Fuseki:")
    print(json.dumps(rows, indent=2, ensure_ascii=False))
    if resolved:
        print("Resolved:", resolved)
    check = None
    if not resolved and entry.get("expected"):
        expected = json.loads((QUERIES / entry["expected"]).read_text(encoding="utf-8"))
        check = "PASS" if same_rows(rows, expected) else "FAIL"
        print(f"Expected rows: {check}")

    record = {"test": "kg_query", "query_id": args.query_id, "resolved": resolved,
              "question": question, "rows": rows, "expected_check": check}
    if not args.rows_only:
        cfg = llm_config()
        if rows:
            check_llm(cfg)
        started = time.perf_counter()
        answer = answer_from_kg(question, rows, cfg)
        record.update(model=cfg["model"], answer=answer,
                      seconds=round(time.perf_counter() - started, 1))
        print("\nQwen's answer:\n" + answer)
    log_run(record)


if __name__ == "__main__":
    main()
