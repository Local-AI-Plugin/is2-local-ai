# Local AI Plug-In: Jena/Fuseki starter

Read `Implementation_Guide.md` for background, configuration, queries, reasoning choices, resource planning, and references.

## Native quick start

1. Install Java 21+ and extract Apache Jena Fuseki 6.2.0.
2. Open a terminal in this directory and start the server:

```bash
java -Xms128m -Xmx512m -jar /YOUR/PATH/apache-jena-fuseki-6.2.0/fuseki-server.jar --config=config.ttl --localhost
```

3. Keep that terminal running. In a second terminal here:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python client.py
python smoke.py
```

On Windows PowerShell activate with `.venv\Scripts\Activate.ps1` instead of `source`.

Open http://127.0.0.1:3030/ for the server UI. Wait for startup to finish before running the client.

## Docker alternative

```bash
docker compose up --build -d
docker compose logs -f fuseki
```

Then install the Python dependencies and run the client on the host. Named volumes preserve database and server work-area data. Do not use `down -v` unless you intend to delete those volumes.

## Scope

- Synthetic tasks, evidence, and a proposed minimal vocabulary.
- TDB2 persistence and named graphs.
- Validation using an explicitly configured SHACL endpoint.
- Restricted subclass-based type materialization; not full RDFS or OWL reasoning.
- Fixed task lookup exposed as an optional Qwen-Agent tool.
- Bootstrap replaces demo schema/staging/accepted/inferred graphs. Use a disposable dataset.
- One trusted writer. Validation and promotion are separate requests.
- Query endpoints have no per-user authorization in this example. Keep access local.

## Optional agent

Install `qwen-agent`, set `LOCAL_MODEL_NAME` to an existing locally served model ID and `LOCAL_MODEL_URL` to its OpenAI-compatible endpoint, then run `python agent.py`. No model is bundled, downloaded, or started here.

## Validation performed

Native server/HTTP workflow tested with Fuseki 6.2.0, Java 21, Requests 2.34.2, RDFLib 7.6.0. Loading, SHACL acceptance/rejection, graph separation, type materialization, task lookup, invalid identifier rejection, and persistence after restart passed.

Docker build, live Qwen-Agent inference, and the guide's illustrative Java API fragment were not executed.

## KG query tests (UGV Scenario 1)

Standalone path, separate from RAG: **Fuseki → Python → Qwen**. Python runs a saved
competency-question (CQ) SPARQL query and gives Qwen only the rows. Qwen never writes SPARQL.

Data: `docs/knowledge/UGV_Mission_Planning_Ontology.rdf` (classes, restrictions) and
`docs/knowledge/UGV_Scenario_1_Individuals.rdf` (individuals). The files share no triples.
Both are needed, because Fuseki does not follow the Scenario file's `owl:imports`.

```bash
python load_kg.py      # REPLACES the kg dataset's default graph with both RDF/XML files
python kg_smoke.py     # no LLM: expected CQ1.1 rows, name resolution, input rejection
```

CQ queries have no `GRAPH`/`FROM`, so they read the **default graph**. The demo named graphs
used by `client.py`/`smoke.py` are separate and untouched.

### Test 1: can Qwen explain known graph results?

```bash
python kg_query.py cq1_1 --rows-only   # rows + PASS/FAIL against queries/cq1_1.expected.json
python kg_query.py cq1_1               # rows, then Qwen's answer from those rows only
python kg_query.py cq1_1 --task "Observe an inspection area" --mission MissionAlphaBravo
```

Check the rows before reading the answer. If the rows are wrong, the problem is the
graph or the query. If the rows are right but the answer is wrong, the problem is the model.

### Test 2: can Qwen pick the right lookup?

```bash
python kg_agent.py                     # scores queries/paraphrases.json
python kg_agent.py "your question"
```

`query_kg` takes a `query_id` (enum from `queries/registry.json`) plus entity names. The code
resolves each name to exactly one IRI of the expected class (local name or label, escaped
literal) and fills the template's `{{param}}` with `<IRI>`, or `UNDEF` when omitted. Unknown
or ambiguous names come back to the model with the known names.

Runs are appended to `logs/kg_runs.jsonl` (gitignored).

### Adding a CQ

Put the working Protégé query in `queries/<id>.rq`, plus a `<id>_template.rq` with
`{{param}}` placeholders and `<id>.expected.json`. Then add an entry to `registry.json` and
paraphrases to `paraphrases.json`.

### LLM access

The scripts call Ollama's OpenAI-compatible API at `$OLLAMA_URL/v1` (default
`http://127.0.0.1:11434`) with `$KG_MODEL` (default `qwen3:4b-instruct-2507-q4_K_M`). They check
first and exit with a clear message if Ollama or the model is missing. Ollama must listen on the
host: use the standalone `local-ai-ollama` container. Only one Ollama can use the
`local-ai-models` volume at a time.

### Caveats

- Fuseki runs no OWL reasoner. CQs that depend on entailments must encode them, as the
  `owl:hasValue` UNION branch in CQ1.1 does.
- Future work: move mission data into named staging/active mission graphs for revisions and
  approval. `load_kg.py --graph IRI` already loads into a named graph, and queries would add `FROM <IRI>`.
