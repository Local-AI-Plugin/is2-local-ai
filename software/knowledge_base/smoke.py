"""Integration checks against the disposable demo dataset."""
from client import *

def ask(pattern):
    return query("PREFIX ex: <" + NS + "> ASK { " + pattern + " }")["boolean"]

load_demo()
assert ask(f"GRAPH <{INFERRED}> {{ ex:task1 a ex:Task }}")
assert not ask(f"GRAPH <{ACCEPTED}> {{ ex:task1 a ex:Task }}")
assert ask(f"GRAPH <{ACCEPTED}> {{ ex:task1 a ex:OfflineTask }}")
assert len(lookup_task("task1")["results"]["bindings"]) == 2
assert lookup_task("task999")["results"]["bindings"] == []
try:
    lookup_task("task1> } SERVICE <https://invalid.example/>")
    raise AssertionError("Invalid identifier was not rejected")
except ValueError:
    pass
bad = (ROOT / "facts.ttl").read_text().replace('ex:status "open"', 'ex:status "invalid"')
put_graph(STAGING, bad)
try:
    validate_graph(STAGING)
    raise AssertionError("Invalid status was not rejected")
except ValueError:
    pass
assert ask(f'GRAPH <{ACCEPTED}> {{ ex:task1 ex:status "open" }}')
put_graph(STAGING, (ROOT / "facts.ttl").read_text())
print("PASS: loading, subclass closure, graph isolation, lookup, input validation, SHACL rejection")
