# Apache Jena and Fuseki: background, setup, and implementation guide

Written for Alex Clark's Local AI Plug-In project. Documentation checked October 20, 2026.

## 1. Recommended starting point

Use **Fuseki + TDB2 as the persistent, local knowledge graph**, accessed by a small Python service that your Qwen-Agent tools call. Begin with a small vocabulary, explicit evidence links, SHACL validation, and a narrowly defined classification step. Add richer reasoning when a concrete question requires it.

This is an architecture recommendation for your prototype, not a measured comparison against other databases. The intended outcome is a device that can retain structured knowledge, connect it to local documents, and recover it across sessions and host computers.

The critical separation is:

| Responsibility | Component in the proposed prototype |
|---|---|
| Generate and interpret natural language | Local Qwen model |
| Coordinate tools and messages | Qwen-Agent |
| Retrieve similar passages | Local embedding model and vector index |
| Store entities and explicit relationships | Jena TDB2 |
| Expose the graph over HTTP | Fuseki |
| Query the graph | SPARQL through Jena ARQ |
| Check required fields and permitted values | SHACL |
| Derive supported logical consequences | A deliberately selected reasoner or restricted rule step |
| Execute a task or choose an action | Application controller and tool implementations |

Do not equate storing an OWL file with running an OWL reasoner. This guide's tested starter computes **subclass-based type inheritance only**. It does not implement full RDFS, OWL 2 RL, or OWL 2 DL reasoning.

## 2. Background: what Jena and Fuseki are

Apache Jena is an open-source Java framework for Semantic Web applications. It began at HP Labs in Bristol in 2000, entered Apache incubation in 2010, and became an Apache top-level project in 2012. Its libraries work with RDF and related standards. [S1]

Fuseki is Jena's SPARQL server: it accepts HTTP requests for queries, updates, and graph transfers. TDB2 supplies local persistent RDF storage. ARQ supplies query processing. You can use these together or embed Jena libraries directly in a Java application. [S2, S3, S4]

For your Python-based agent harness, an HTTP boundary is practical: the agent does not need to become a Java application. The Java process owns storage; Python sends requests and interprets responses.

### Main pieces you will encounter

| Name | Role | When you need it |
|---|---|---|
| RDF | Graph data model | All graph data |
| Turtle, `.ttl` | Human-readable RDF serialization | Ontology, sample facts, configuration, shapes |
| RDFS / OWL | Vocabulary and ontology semantics | Class hierarchies and richer formal descriptions |
| ARQ | Jena query engine | SPARQL execution |
| TDB2 | Transactional disk-backed dataset | Knowledge that must survive restart |
| Fuseki | HTTP service | Sharing the dataset with Python and other clients |
| Jena inference API | Interfaces and supplied reasoning engines | In-process reasoning in Java |
| Jena SHACL | Shape validation | Structural checks and data-quality reports |
| RIOT | RDF parsing and writing tools | Data conversion and syntax checks |

The Jena downloads page currently lists **6.2.0**. Jena 6 requires **Java 21 or later**. Keep the Fuseki server and any separate Jena command-line distribution on the same version. [S5]

## 3. The data model, with your project in mind

An RDF triple has a subject, predicate, and object. Subjects identify resources or blank nodes; predicates are IRIs; objects can also be literals. An RDF dataset has a default graph and named graphs. A prefix is shorthand for an IRI namespace. These identifiers do not need to be fetched from the internet for ordinary local graph use. [S6]

```turtle
@prefix ex: <https://example.org/local-ai/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:task1 a ex:OfflineTask ;
    rdfs:label "Summarize an offline document" ;
    ex:requiresCapability ex:LocalInference .

ex:OfflineTask rdfs:subClassOf ex:Task .
```

Read this as:

- `task1` is an instance of `OfflineTask`.
- `task1` has a readable label and requires the `LocalInference` capability.
- `OfflineTask` is a subclass of `Task`.

Here, `a` abbreviates `rdf:type`. The semicolon repeats the subject for the next predicate.

Your ontology defines what classes and relationships mean. Your instance data describes particular tasks, documents, requirements, hypotheses, and observations. The database stores their RDF representation. A reasoner applies a selected set of semantics; a query retrieves a selected view.

For the example, type inheritance licenses the conclusion that `task1` is also a `Task`. Merely loading the three statements into an ordinary TDB2 dataset does not automatically add that inferred type to query results.

### Ontology concepts worth starting with

My suggested first vocabulary is deliberately small:

| Class | Example use |
|---|---|
| `Task` | Summarize a document or compare test results |
| `OfflineTask` | A task that must operate without a network |
| `Capability` | Local inference, document search, graph lookup |
| `Evidence` | A specific document chunk or benchmark record |
| `Hypothesis` | An interpretation that has not been accepted |
| `UnresolvedQuestion` | A missing fact that affects a decision |

These are proposed application concepts. The starter is not a finished domain ontology.

## 4. Where this fits with RAG, Qwen-Agent, and working memory

Use vector retrieval for finding relevant language, and graph lookup for relationships you have chosen to represent explicitly.

A useful request flow is:

1. The user asks a question.
2. The controller retrieves local passages and/or known graph entities.
3. The model receives the relevant context.
4. If needed, Qwen-Agent invokes a bounded graph tool.
5. The controller returns facts, classifications, and evidence identifiers.
6. The model explains the result and identifies unknowns.

Neither RAG nor graph access must be model-selected tool calls. You can retrieve automatically before prompting, let the model choose a tool, or combine both. For a small model, I would automatically retrieve a modest context package, then provide a few specific graph tools for follow-up questions. This is a proposed design, not a requirement imposed by Jena.

For persistent working memory, store items worth recovering: task state, evidence-backed findings, unresolved questions, and accepted interpretations. Avoid automatically storing every sentence of model reasoning. A useful graph should preserve the status and origin of an interpretation.

The KG does not replace the documents, embeddings, prompt context, or model weights. Keep document text and embeddings outside the graph unless you have a specific need to store them there; link them using stable document/chunk IDs.

## 5. Keep graph contents separated by purpose

The starter uses explicit named graphs:

| Graph IRI suffix | Contents | Query policy in the starter |
|---|---|---|
| `graph/schema` | Small vocabulary and subclass axioms | Used during classification |
| `graph/staging` | Candidate replacement data | Validate before promotion |
| `graph/accepted` | Accepted demonstration facts | Read by the task tool |
| `graph/inferred` | Derived parent-class memberships | Read alongside accepted types |

The shared namespace is `https://example.org/local-ai/`.

A later project version could add separate session, hypothesis, provenance, and validation-report graphs. This separation is an application convention, **not an access-control boundary**. A client with unrestricted SPARQL access can request other graphs. The controller must enforce the intended access policy.

Do not enable a union default graph simply to make every query easier. In this design it could accidentally mix candidates with accepted facts. Queries name the graphs they intend to read.

The default graph can be empty while named graphs contain all the data. Therefore `SELECT * WHERE { ?s ?p ?o }` may return nothing. Inspect named graphs with:

```sparql
SELECT ?g (COUNT(*) AS ?triples)
WHERE { GRAPH ?g { ?s ?p ?o } }
GROUP BY ?g
ORDER BY ?g
```

## 6. Setup: native Java server

### Prerequisites

Install a Java 21 runtime; install a Java 21 JDK if you also want to compile Java code. Python 3.10+ is a reasonable starting point for the optional agent integration. Confirm the Java version with:

```bash
java -version
```

Download the matching Fuseki archive from [Apache's downloads page](https://jena.apache.org/download/), verify its SHA-512 checksum, and extract it. The Fuseki archive contains the server and UI. The separate `apache-jena` distribution supplies the broader command-line toolkit. [S5, S7]

Extract the accompanying starter ZIP and open a terminal in its `jena-fuseki-starter` directory. In the following command, replace `/absolute/path/...` with your extracted Fuseki path:

```bash
java -Xms128m -Xmx512m \
  -jar /absolute/path/apache-jena-fuseki-6.2.0/fuseki-server.jar \
  --config=config.ttl --localhost
```

On Windows, the equivalent PowerShell command is:

```powershell
java -Xms128m -Xmx512m -jar "C:\tools\apache-jena-fuseki-6.2.0\fuseki-server.jar" --config=config.ttl --localhost
```

Run it from the starter directory so the relative database location is predictable. Keep this terminal running. In your browser, open `http://127.0.0.1:3030/`.

The starter configuration is explicit about TDB2 storage; it does not depend on a UI default. It stores data under `databases/kg` relative to the server's working directory. The server's operational work area is separate from that database location. [S7, S8]

### Install Python dependencies and load the demo

In a second terminal, in the same starter directory:

```bash
python -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

Or on Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Then:

```bash
python -m pip install -r requirements.txt
python client.py
python smoke.py
```

`client.py` and `smoke.py` **replace the four demonstration graphs**. Use a disposable dataset for these commands. They are bootstrap/verification utilities, not a general-purpose merge importer.

The first output should contain two types for `task1`: `OfflineTask` and `Task`, together with its label, status, and evidence IRI. The smoke script checks successful loading and rejects intentionally invalid data.

### Check readiness independently

```bash
curl -fsS -X POST http://127.0.0.1:3030/kg/sparql \
  --data-urlencode 'query=ASK {}' \
  -H 'Accept: application/sparql-results+json'
```

In Windows PowerShell use `curl.exe` if `curl` is an alias. Wait until the server accepts a query before starting ingestion.

## 7. Setup: Docker alternative

The starter includes a custom Dockerfile using the official Apache Fuseki distribution and a Java 21 runtime. It is not a claim that Apache publishes this particular prebuilt container image. Apache also documents a separate Docker toolkit based on Fuseki Main without a UI. [S9]

With Docker installed and running, from the starter directory:

```bash
docker compose up --build -d
docker compose logs -f fuseki
```

Once the server is ready, run the same host-side Python commands from section 6. Docker exposes it at `127.0.0.1:3030`.

The Dockerfile pins Jena to 6.2.0 and verifies the archive checksum. For stricter reproducibility, also pin the base image by digest. The archive and checksum are downloaded during the build; runtime graph operations do not need those downloads.

The Compose file supplies named volumes for the database and server work area. `docker compose down` stops and removes the container while retaining those volumes. `docker compose down -v` deletes those volumes and therefore the stored demo database.

The example starts with a 512 MiB maximum heap and a 1 GiB container memory limit. These are trial settings for a tiny demonstration, not measured requirements for your full system. Monitor actual memory before selecting deployment limits.

If your agent runs in another Compose service on the same network, use:

```text
FUSEKI_URL=http://fuseki:3030/kg
```

Inside a container, `localhost` refers to that container. The supplied Compose file contains only Fuseki; your model runtime and agent are separate services to add later.

For an offline deployment, prepare the image, Python wheels, model files, embedding files, and ontology imports while online. Transfer them to the target and verify a cold start with networking disabled. Containerization alone does not ensure the other components avoid network access.

## 8. Understanding the Fuseki configuration

The essential parts of `config.ttl` are:

```turtle
@prefix fuseki: <http://jena.apache.org/fuseki#> .
@prefix tdb2: <http://jena.apache.org/2016/tdb#> .

<#service> a fuseki:Service ;
    fuseki:name "kg" ;
    fuseki:endpoint [ fuseki:operation fuseki:query ; fuseki:name "sparql" ] ;
    fuseki:endpoint [ fuseki:operation fuseki:update ; fuseki:name "update" ] ;
    fuseki:endpoint [ fuseki:operation fuseki:gsp-rw ; fuseki:name "data" ] ;
    fuseki:endpoint [ fuseki:operation fuseki:shacl ; fuseki:name "shacl" ] ;
    fuseki:dataset <#store> .

<#store> a tdb2:DatasetTDB2 ;
    tdb2:location "databases/kg" .
```

Fuseki's RDF configuration describes the service, permitted operation types, endpoint names, and backing dataset. The complete supplied file also adds a query timeout. Endpoint names such as `sparql` are configuration choices rather than universal fixed paths. [S8, S10]

| Configured URL | Purpose | Example content |
|---|---|---|
| `/kg/sparql` | Query | SPARQL SELECT / ASK |
| `/kg/update` | Change triples | SPARQL INSERT / DELETE |
| `/kg/data?graph=IRI` | Transfer one graph | Turtle via Graph Store Protocol |
| `/kg/shacl?graph=IRI` | Validate a selected graph | Shapes posted as Turtle |

The optional SHACL endpoint is explicitly enabled; do not assume every Fuseki dataset has it.

## 9. Ingestion and validation

The tested demo pipeline is:

1. Load `ontology.ttl` into the schema graph.
2. Load `facts.ttl` into the staging graph.
3. Submit `shapes.ttl` to validate staging.
4. Parse the returned RDF validation report.
5. Promote staging to accepted and refresh inherited types in one update request.
6. Query only the intended accepted and inferred graphs.

### What SHACL checks

The demo shapes require tasks to have one string label, one allowed status, and at least one evidence IRI. The allowed statuses are `open`, `completed`, and `blocked`. Jena implements SHACL Core and SPARQL constraints, and its Fuseki operation returns a validation report for the selected data graph. [S11]

A minimal shape is:

```turtle
@prefix ex: <https://example.org/local-ai/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .

ex:TaskShape a sh:NodeShape ;
    sh:targetClass ex:Task ;
    sh:targetClass ex:OfflineTask ;
    sh:property [
        sh:path ex:status ;
        sh:minCount 1 ;
        sh:maxCount 1 ;
        sh:in ( "open" "completed" "blocked" )
    ] .
```

A successful HTTP response does not itself mean validation passed. Inspect `sh:conforms` in the report. The Python client rejects a report unless it contains the expected true value.

**SHACL validation is not automatic write interception.** In this starter, the controller checks the report before promotion. A direct SPARQL update could bypass that controller.

The starter explicitly targets both current task classes because the schema is in another graph. If you add subclasses, update the targets or validate an intentionally assembled view containing the required schema and instance data. A shape that targets no nodes can pass while checking none of the records you intended to check. [S12]

Structural validation also cannot prove that an evidence link supports a claim. You still need evidence review or an evaluation process for that relationship.

### Concurrency limitation

This example assumes one trusted writer. Staging validation and publication are separate HTTP requests. Another writer could modify staging or the schema between them. For multiple writers, use immutable per-batch staging graphs, serialize publication, and validate against a fixed schema version. If validation and publication must share one transaction, implement them in the server/application layer around the same dataset transaction. Do not assume several HTTP calls form one transaction.

The demo also replaces the schema before validating facts. A production schema migration needs its own validation and publication procedure; this bootstrap is not that procedure.

## 10. Querying with SPARQL

SPARQL SELECT returns bindings; ASK returns a boolean; CONSTRUCT returns an RDF graph. Update operations change a dataset and use the configured update endpoint. [S13]

### A. Retrieve one task and its evidence

```sparql
PREFIX ex: <https://example.org/local-ai/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?label ?status ?evidence
WHERE {
  GRAPH <https://example.org/local-ai/graph/accepted> {
    ex:task1 rdfs:label ?label ;
             ex:status ?status ;
             ex:supportedBy ?evidence .
  }
}
```

The graph name is a complete IRI. The following is the same graph pattern in isolation:

```sparql
GRAPH <https://example.org/local-ai/graph/accepted> {
  ex:task1 rdfs:label ?label ; ex:status ?status ; ex:supportedBy ?evidence .
}
```

### B. Retrieve explicit and inherited types

```sparql
PREFIX ex: <https://example.org/local-ai/>
SELECT DISTINCT ?type
WHERE {
  VALUES ?g {
    <https://example.org/local-ai/graph/accepted>
    <https://example.org/local-ai/graph/inferred>
  }
  GRAPH ?g { ex:task1 a ?type }
}
```

Expected types are `ex:OfflineTask` and `ex:Task`.

### C. Find dependencies that have not completed

```sparql
PREFIX ex: <https://example.org/local-ai/>
SELECT ?task ?dependency ?status
WHERE {
  GRAPH <https://example.org/local-ai/graph/accepted> {
    ?task ex:dependsOn ?dependency .
    OPTIONAL { ?dependency ex:status ?status }
  }
  FILTER (!BOUND(?status) || ?status != "completed")
}
LIMIT 50
```

The proposed policy treats missing dependency status as a reason to withhold automatic execution. That is your application's decision rule. An absent triple is not a universal logical statement that a dependency is incomplete.

### D. Change task state

Use this only through the trusted writer:

```sparql
PREFIX ex: <https://example.org/local-ai/>
DELETE {
  GRAPH <https://example.org/local-ai/graph/accepted> { ex:task1 ex:status ?old }
}
INSERT {
  GRAPH <https://example.org/local-ai/graph/accepted> { ex:task1 ex:status "completed" }
}
WHERE {
  GRAPH <https://example.org/local-ai/graph/accepted> { ex:task1 ex:status ?old }
}
```

For the present rule, status changes do not alter inherited types. If later rules depend on status, refresh their deductions after those changes as well.

## 11. Reasoning: classification, constraints, and execution

Keep these three questions distinct:

| Question | Proposed mechanism |
|---|---|
| What broader class does this entity belong to? | Type inheritance or a selected ontology reasoner |
| Does this submitted record have required fields? | SHACL |
| Which action should happen next? | Controller, planner, or scheduler |

OWL follows an open-world approach: missing information need not be false. Domain/range statements can entail types; they are not ordinary database input constraints. More expressive axioms can require reasoning beyond straightforward class hierarchy traversal. [S14]

Your domain being defense, enterprise, or education does not itself determine whether you need OWL 2 DL. Choose expressivity from the actual class definitions, restrictions, and questions.

### The implemented classification step

The client uses a SPARQL property path to find parent classes:

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
INSERT {
  GRAPH <https://example.org/local-ai/graph/inferred> { ?item a ?parent }
}
WHERE {
  GRAPH <https://example.org/local-ai/graph/accepted> { ?item a ?child }
  GRAPH <https://example.org/local-ai/graph/schema> {
    ?child rdfs:subClassOf+ ?parent
  }
  FILTER NOT EXISTS {
    GRAPH <https://example.org/local-ai/graph/accepted> { ?item a ?parent }
  }
}
```

The `+` traverses one or more subclass edges. The full client first clears the previous inferred graph, preventing stale memberships from surviving the next refresh. Property-path evaluation is a query mechanism; it does not enable all RDFS or OWL entailments. [S15]

This restricted baseline is useful for measuring whether your smaller model benefits from external, deterministic classification before introducing a larger reasoning subsystem.

### Actual Jena inference API

Jena supplies configurable RDFS reasoning and useful but incomplete OWL reasoners, plus a generic rule engine. Its supplied OWL, OWL Mini, and OWL Micro reasoners should not be presented as complete OWL 2 DL reasoners or automatically as complete OWL 2 RL implementations. Inference models can expose consequences alongside base statements; the base storage dataset is a separate concern. [S16]

An illustrative Java fragment is:

```java
import org.apache.jena.rdf.model.*;
import org.apache.jena.reasoner.*;
import org.apache.jena.riot.RDFDataMgr;

Model schema = RDFDataMgr.loadModel("ontology.ttl");
Model facts = RDFDataMgr.loadModel("facts.ttl");
Reasoner reasoner = ReasonerRegistry.getRDFSReasoner().bindSchema(schema);
InfModel view = ModelFactory.createInfModel(reasoner, facts);
view.prepare();

Resource task = view.createResource("https://example.org/local-ai/task1");
Resource taskClass = view.createResource("https://example.org/local-ai/Task");
boolean classified = view.contains(task,
    view.createProperty("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"),
    taskClass);
System.out.println(classified);
```

This is an explanatory API fragment, not a separately tested Java program in the starter. It requires the matching Jena libraries. It does not automatically attach inference to the configured Fuseki dataset or persist deductions into its inferred graph.

If richer OWL classification becomes necessary, evaluate a suitable external reasoner against your actual ontology, confirm supported features and compatibility, and publish only the needed classifications with provenance. Do not add another always-running service before measuring its cost and benefit.

### Precompute or infer during queries?

| Design | Benefit for this prototype | Work you must account for |
|---|---|---|
| Materialize selected deductions | Predictable query behavior; easy to inspect explicit vs derived types | Refresh and retract stale deductions |
| Query an inference view | Avoid storing every consequence explicitly | Query latency, caches, and inference-view update behavior |
| Run external reasoning on snapshots | Isolate richer classification from the main agent | Snapshot versions, result publishing, failure handling |

My starting recommendation is materialized, narrowly scoped classifications after accepted-data changes. Record the schema and rule version used for each batch.

## 12. Hypotheses, provenance, and plan vocabularies

Avoid giving every model extraction the status of an accepted fact. A candidate can be represented as a statement resource:

```turtle
@prefix ex: <https://example.org/local-ai/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix prov: <http://www.w3.org/ns/prov#> .

ex:hypothesis17 a ex:Hypothesis, rdf:Statement ;
    rdf:subject ex:task1 ;
    rdf:predicate ex:requiresCapability ;
    rdf:object ex:LocalInference ;
    ex:reviewStatus "candidate" ;
    prov:wasDerivedFrom ex:chunk1 .
```

This describes a proposed statement without asserting the described subject-predicate-object triple by reification alone. Keep such proposals outside accepted-data queries. The example is a modeling pattern for future work; the starter does not implement hypothesis review or promotion.

PROV-O gives you vocabulary for entities, activities, agents, and derivation. For example, identify the source chunk as an entity, extraction as an activity, and the extracting software as an agent. Record which activity generated a claim. [S17]

P-Plan offers vocabulary for plans, steps, variables, and the relationship between planned steps and execution. It is useful if you need to represent a reusable procedure and compare it with what actually ran. It does not itself execute that procedure. [S18]

For your first prototype, introduce provenance before importing a large planning vocabulary. Suggested records include:

- Source document ID, content hash, page/section, and chunk ID.
- Extraction model/version, prompt version, and time.
- Accepted/rejected status and reviewer or rule.
- Schema version and classification rule used.
- IDs of supporting base assertions for important derived findings.

A numerical extraction confidence is metadata about a process; do not treat it as an automatically calibrated probability or as fuzzy OWL semantics.

## 13. Qwen-Agent integration

Qwen-Agent supports custom tools through `BaseTool` and registration, and can use a local OpenAI-compatible model endpoint. The included `agent.py` follows that integration pattern. [S19]

The example tool is `lookup_task(task_id)`. The agent passes `task1`; the Python function validates that identifier, runs a fixed SPARQL template, and returns structured results. The agent does not supply raw query text.

This design reduces the amount of syntax and schema detail a 3B–7B model needs to get right. Extend it with small tools only when a use case needs them, for example:

| Tool | Inputs | Result |
|---|---|---|
| `lookup_task` | Known task ID | Labels, state, types, evidence |
| `list_unresolved_questions` | Session or task ID | Questions affecting that task |
| `get_dependencies` | Task ID | Known dependency states |
| `get_evidence` | Accepted evidence ID | Source metadata and local chunk reference |

Only `lookup_task` is implemented in this starter.

To try the optional integration, install minimal Qwen-Agent in the virtual environment:

```bash
python -m pip install qwen-agent
```

Record the version you actually validate, then pin it in your project's lock file. The starter's base requirements intentionally do not pull in the entire agent framework.

Configure your existing local model server; its model name must match what that server exposes:

```bash
export LOCAL_MODEL_NAME='YOUR_LOCAL_MODEL_ID'
export LOCAL_MODEL_URL='http://127.0.0.1:8000/v1'
python agent.py
```

PowerShell:

```powershell
$env:LOCAL_MODEL_NAME = "YOUR_LOCAL_MODEL_ID"
$env:LOCAL_MODEL_URL = "http://127.0.0.1:8000/v1"
python agent.py
```

The code does not download or start a model. The model backend must support your selected tool-calling setup. The live Qwen-Agent/model loop was not run for this deliverable.

For deployment, enforce tool-call budgets, maximum returned rows/bytes, and an end-to-end deadline in your controller. A prompt instruction alone is not an execution limit.

## 14. Runtime access policy

The native startup command binds to localhost, and Docker publishes the port on the host loopback address. This is appropriate for the supplied local-development example.

Fuseki Full's default security configuration restricts administration to localhost while its data endpoints are otherwise open by default. Treat network binding and explicit access configuration as part of deployment. Full/UI security instructions are not interchangeable with every Fuseki Main deployment. [S20]

Before connecting a host computer to the module:

1. Define which controller may query and which may publish graph changes.
2. Authenticate requests across the host/device boundary.
3. Restrict direct database/update access to the trusted writer.
4. Keep the agent tool interface narrower than SPARQL.
5. Keep ontology imports and model dependencies local for offline operation.

For your portable-agent idea, USB or USB-C connectivity is not a feature Fuseki creates. Another subsystem must provide a transport, such as a deliberate IP link, and a host client. Fuseki then serves requests over that link. Persistent graph state can stay on the module while the host changes.

The starter has no user accounts, per-session authorization, encrypted transport, or production host/device protocol. Those are integration tasks for the product.

## 15. RAM, CPU, and storage on a small device

A 512 MiB Java maximum heap does **not** cap total process memory at 512 MiB. Account for JVM native allocations, stacks, direct buffers, memory-mapped storage, and OS caching. TDB relies heavily on memory mapping; leave room outside the Java heap. [S21]

For your possible 8 GB target, measure all components together. I would start with a small graph and 256–512 MiB maximum heap for experiments, then adjust based on latency and memory pressure. This is a proposed experiment range, not a supported capacity guarantee.

Budget these separately:

| Consumer | What to measure |
|---|---|
| LLM | Loaded weights, KV cache at target context, runtime buffers |
| Embedding model | Loaded model and peak indexing batch |
| Fuseki | Heap, total resident/container memory, query/inference spikes |
| Vector index | Resident pages and indexing peaks |
| Python harness | Imports, tool results, parsing and temporary copies |
| OS | Baseline services, cache, and device I/O |

Your earlier 25–50% overhead question is best answered from simultaneous peaks, rather than a universal percentage. Measure a long-context model request while querying the graph and retrieving passages. If memory pressure rises, reduce context, serialize ingestion, or unload the embedding model after indexing before changing the graph design.

For ARM hardware such as the ROCK 5B+, select an ARM64 Java runtime and compatible container image, then test on that board. The included integration run used x86-64, not the target SBC. Do not infer token speed, power consumption, or board capacity from this server test.

A possible measurement sequence is:

1. OS baseline with no AI services.
2. Fuseki idle after loading the target graph.
3. Typical and expensive graph queries, warm and cold.
4. Selected classification and validation batches.
5. LLM alone at the intended context length.
6. LLM plus graph queries, then LLM plus graph and vector retrieval.
7. A complete task with wall-clock energy measurement.

Track peak memory, p50/p95 graph latency, classification time, task success, evidence correctness, and energy per completed task. Your IFEval score can remain a model baseline, but add graph-specific tasks to evaluate the system's contribution.

## 16. Persistence, backups, and maintenance

TDB2 is a local store. One JVM process should own its database directory; other applications should use Fuseki rather than opening the same files independently. Its administration tools support consistent backups and compaction; command-line maintenance should target a database not already in use. [S22]

For a simple development backup:

1. Stop Fuseki cleanly.
2. Copy the complete `databases/kg` directory, configuration, shapes, and ontology source/version metadata.
3. Start Fuseki again.
4. Test restoration into a separate location.

A database-file copy taken while writes are active is not the same as a consistent backup. Use the documented live backup facility when you need online backups.

If using the separate Jena command distribution, after stopping the server:

```bash
/absolute/path/apache-jena-6.2.0/bin/tdb2.tdbbackup --loc=databases/kg
```

Consult the matching version's command help for output location and options. TDB2 backup files use compressed N-Quads, preserving named graphs. A Turtle dump of only one graph is not a backup of the entire dataset. [S22, S23]

A backup on the same physical module is insufficient protection against loss of the module. Keep a restorable copy elsewhere according to your project's data requirements.

## 17. Troubleshooting

| Symptom | Likely cause | First check |
|---|---|---|
| Java class-version error | Older Java runtime | `java -version`; Jena 6 needs 21+ |
| HTTP connection refused | Server not ready, wrong port, container address | Server logs and readiness query |
| Empty unqualified query | Data lives in named graphs | Run the graph inventory query |
| HTTP 404 on an operation | Endpoint absent or name differs | Compare URL with `config.ttl` |
| HTTP 400 on update | SPARQL syntax or wrong request body type | Use `/kg/update` and update MIME type |
| SHACL returns HTTP 200 but rejects data | Report has `sh:conforms false` | Parse and inspect the RDF report |
| SHACL passes invalid-looking record | Shape targeted no node or omitted constraint | Check targets and selected graph |
| Parent type missing | No inference configured/refreshed | Check schema and inferred graph |
| Deductions outlive deleted facts | Append-only materialization | Rebuild or implement truth maintenance |
| Database lock failure | Another JVM owns the directory | Stop duplicate owner; do not delete active locks |
| Data gone after container removal | No persistent volume or volume deleted | Inspect Compose volume definitions |
| Agent cannot reach Fuseki in Docker | Using container-local `localhost` | Use service name on shared network |
| Memory failure despite low `-Xmx` | Non-heap memory or other services | Inspect container/system memory together |

## 18. Suggested implementation milestones

These are proposed engineering steps, not claims about completed project work.

**Milestone 1 — local persistence:** Start Fuseki/TDB2, load a small synthetic graph, run fixed queries, and verify restart persistence. Establish a backup/restore procedure.

**Milestone 2 — evidence-backed data:** Define the first real questions, stable entity/chunk IDs, provenance fields, and shape targets. Build the extraction-to-staging path and assess extraction quality before promotion.

**Milestone 3 — bounded agent access:** Add graph lookup tools to Qwen-Agent. Evaluate whether the model selects the right tool, uses the returned evidence, and reports missing information correctly.

**Milestone 4 — measured reasoning:** Compare explicit graph lookup with the restricted classification baseline. Add a richer reasoner only for specific unsupported entailments that improve task performance.

**Milestone 5 — device integration:** Move the same workload to target hardware, measure concurrent memory and power, validate cold offline startup, and implement the host/device transport.

A useful experiment compares the same task set across: model alone; model + structured prompt state; model + RAG; model + graph lookup; and model + graph lookup + selected reasoning. Keep the model, prompt budget, and documents comparable. This helps determine whether the graph's extra infrastructure earns its resource cost.

## 19. Included starter files and verification

| File | Purpose |
|---|---|
| `config.ttl` | TDB2-backed service, endpoints, query timeout |
| `ontology.ttl` | Proposed minimal schema |
| `facts.ttl` | Clearly synthetic demonstration facts |
| `shapes.ttl` | Task record validation |
| `client.py` | Loading, validation, publication, classification, task lookup |
| `agent.py` | Optional Qwen-Agent wrapper |
| `requirements.txt` | Versions used for the Python graph client |
| `Dockerfile` | Custom image from Apache Fuseki archive |
| `compose.yaml` | Local port mapping, persistent volumes, trial resource limits |
| `smoke.py` | Integration checks using disposable demo graphs |
| `README.md` | Quick start and test scope |

Verified here with Fuseki **6.2.0**, a Java **21** runtime, Requests **2.34.2**, and RDFLib **7.6.0**:

- Server startup with the supplied TDB2/endpoint configuration.
- Graph loading through Graph Store Protocol.
- SHACL report parsing, valid-data acceptance, and invalid-status rejection.
- Promotion and subclass-derived type publication.
- Separation of explicit and derived types.
- Bounded task lookup, missing-task behavior, and rejection of invalid identifiers.
- Preservation of accepted facts after a rejected candidate.
- Persistence after a clean server restart.

The Docker image was **not built** in this environment. The optional Qwen-Agent/model loop and illustrative Java inference fragment were **not executed**. This is a tested local KG workflow with deployment and agent-integration examples, not a validated end-to-end Local AI Plug-In implementation.

## 20. Official documentation and source references

[S1] [Jena background and history](https://jena.apache.org/about_jena/about.html)

[S2] [Fuseki overview](https://jena.apache.org/documentation/fuseki2/)

[S3] [TDB2 overview](https://jena.apache.org/documentation/tdb2/)

[S4] [ARQ query engine](https://jena.apache.org/documentation/query/)

[S5] [Current downloads and Java requirements](https://jena.apache.org/download/)

[S6] [W3C RDF concepts](https://www.w3.org/TR/rdf11-concepts/)

[S7] [Running Fuseki](https://jena.apache.org/documentation/fuseki2/fuseki-server.html)

[S8] [TDB2 with Fuseki](https://jena.apache.org/documentation/tdb2/tdb2_fuseki.html)

[S9] [Apache Fuseki Docker toolkit](https://jena.apache.org/documentation/fuseki2/fuseki-docker.html)

[S10] [Endpoint configuration](https://jena.apache.org/documentation/fuseki2/fuseki-config-endpoint.html) and [server configuration](https://jena.apache.org/documentation/fuseki2/fuseki-configuration.html)

[S11] [Jena SHACL and Fuseki integration](https://jena.apache.org/documentation/shacl/)

[S12] [W3C SHACL specification](https://www.w3.org/TR/shacl/)

[S13] [W3C SPARQL query specification](https://www.w3.org/TR/sparql11-query/)

[S14] [W3C OWL 2 primer](https://www.w3.org/TR/owl2-primer/)

[S15] [SPARQL property paths](https://www.w3.org/TR/sparql11-property-paths/)

[S16] [Jena reasoners and inference](https://jena.apache.org/documentation/inference/)

[S17] [PROV-O](https://www.w3.org/TR/prov-o/)

[S18] [P-Plan vocabulary](https://www.opmw.org/model/p-plan/)

[S19] [Qwen-Agent source and custom-tool documentation](https://github.com/QwenLM/Qwen-Agent)

[S20] [Fuseki Full security](https://jena.apache.org/documentation/fuseki2/fuseki-security.html)

[S21] [TDB memory explanation](https://jena.apache.org/documentation/tdb/faqs.html) and [TDB2 memory discussion in Apache Jena](https://github.com/apache/jena/discussions/2099)

[S22] [TDB2 administration, backups, and compaction](https://jena.apache.org/documentation/tdb2/tdb2_admin.html)

[S23] [TDB2 command-line tools](https://jena.apache.org/documentation/tdb2/tdb2_cmds.html)
