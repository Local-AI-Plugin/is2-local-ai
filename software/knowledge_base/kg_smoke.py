"""Checks for the UGV KG query path against Fuseki. No LLM needed.

Reloads the default graph from docs/knowledge/*.rdf first.
"""
import json

from kg_query import QUERIES, build_query, compact, run_query, same_rows
from load_kg import load, triple_count


def raises(exc, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc:
        return True
    raise AssertionError(f"{fn.__name__}{args}{kwargs} did not raise {exc.__name__}")


count = load()
assert count > 1000, count

expected = json.loads((QUERIES / "cq1_1.expected.json").read_text(encoding="utf-8"))

# Test 1 input: the saved query, verbatim, gives the known answer.
assert same_rows(compact(run_query("cq1_1")), expected)

# The template gives the same answer whichever way the task is named.
for task in ["ObserveAreaTask", "s1:ObserveAreaTask", "observe an inspection area",
             "https://example.org/is2/ugv-mission-planning/scenario-1#ObserveAreaTask"]:
    rows = compact(run_query("cq1_1", task=task, mission="MissionAlpha"))
    assert same_rows(rows, expected, ignore={"mission"}), (task, rows)

# Omitted mission = any mission assigning the task (Alpha and Alpha-Bravo).
rows = compact(run_query("cq1_1", task="ObserveAreaTask"))
assert sorted(r["mission"] for r in rows) == ["s1:MissionAlpha", "s1:MissionAlphaBravo"], rows

# A known task with no recorded requirement returns nothing (not an error).
assert run_query("cq1_1", task="MoveTask", mission="MissionAlpha") == []

# Unknown names, wrong classes and injection attempts never reach the query.
raises(LookupError, run_query, "cq1_1", task="NoSuchTask")
raises(LookupError, run_query, "cq1_1", task="MissionAlpha")  # a Mission, not a Task
raises(LookupError, run_query, "cq1_1", task='x") } ; DROP ALL #')
raises(LookupError, run_query, "cq1_1", task="ObserveAreaTask> } UNION { ?s ?p ?o")
raises(ValueError, run_query, "cq1_1", task="x" * 500)
raises(ValueError, run_query, "cq1_1", area="Alpha")          # param not in registry
raises(ValueError, run_query, "drop_everything")              # unknown query_id
sparql, _ = build_query("cq1_1", task="ObserveAreaTask")
assert "{{" not in sparql and "UNDEF" in sparql

assert triple_count() == count  # nothing above changed the data
print(f"PASS: {count} triples loaded, CQ1.1 expected rows, name resolution, "
      "UNDEF mission, empty result, input rejection")
