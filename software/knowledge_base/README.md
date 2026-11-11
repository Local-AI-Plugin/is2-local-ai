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
