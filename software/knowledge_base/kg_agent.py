"""Test 2: Qwen chooses the lookup. A `query_kg` Qwen-Agent tool lets the model
pick a registered competency query and name the entities. Our code validates
the arguments, resolves names to IRIs and fills the SPARQL template; the model
never writes SPARQL.

    python kg_agent.py                       # score queries/paraphrases.json
    python kg_agent.py "What does the observe task need on Mission Alpha?"
"""
import argparse
import json
import time

import json5
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool

from kg_query import (QUERIES, check_llm, compact, compact_iri, final_content, llm_config,
                      load_registry, log_run, registry_entry, resolve, run_query)

REGISTRY = load_registry()
PARAMS = {name: spec for entry in REGISTRY.values()
          for name, spec in entry.get("params", {}).items()}

SYSTEM_MESSAGE = (
    "You answer questions about UGV missions, tasks and vehicle capabilities. "
    "For any such factual question, call query_kg first. Pass task and mission "
    "names as the user wrote them; never invent IDs. If the tool reports an "
    "unknown name, you may retry with one of the known names it lists. "
    "Answer using only the tool results and name the entities that support the "
    "answer. If the results are empty or a detail is missing, say so."
)


@register_tool("query_kg")
class QueryKG(BaseTool):
    description = ("Run a fixed knowledge-graph query. Available queries:\n" + "\n".join(
        f"- {qid}: {entry['question']} {entry['description']}" for qid, entry in REGISTRY.items()))
    parameters = {
        "type": "object",
        "properties": {
            "query_id": {"type": "string", "enum": sorted(REGISTRY),
                         "description": "Which registered query to run."},
            **{name: {"type": "string", "description": spec["description"]}
               for name, spec in PARAMS.items()},
        },
        "required": ["query_id"],
    }

    def call(self, params: str, **kwargs) -> str:
        try:
            args = json5.loads(params)
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
            query_id = args.pop("query_id", None)
            rows = compact(run_query(query_id, **args))
            return json.dumps({"query_id": query_id, "rows": rows}, ensure_ascii=False)
        except LookupError as exc:
            # Unknown/ambiguous name: tell the model how to recover.
            return json.dumps({"error": str(exc)[:500],
                               "next_step": "Call query_kg again using one of the known names "
                                            "that matches the user's wording."})
        except Exception as exc:
            # Bounded diagnostic back to the model; nothing is executed from it.
            return json.dumps({"error": str(exc)[:500]})


def make_bot():
    return Assistant(llm=llm_config(), function_list=["query_kg"],
                     system_message=SYSTEM_MESSAGE)


def tool_calls(messages):
    calls = []
    for message in messages:
        call = message.get("function_call")
        if message.get("role") == "assistant" and call and call.get("name") == "query_kg":
            try:
                args = json5.loads(call.get("arguments") or "{}")
            except ValueError:
                args = {"_unparsed": call.get("arguments")}
            calls.append(args)
    return calls


def resolved_args(args):
    """Tool-call arguments mapped to prefixed IRIs, so names and IDs compare equal."""
    out = {"query_id": args.get("query_id")}
    try:
        params = registry_entry(args.get("query_id")).get("params", {})
    except ValueError:
        return out
    for name, spec in params.items():
        if args.get(name):
            try:
                out[name] = compact_iri(resolve(args[name], spec["class"]))
            except (LookupError, ValueError):
                out[name] = f"<unresolved {args[name]!r}>"
    return out


def matches(call, expect):
    return all(call.get(key) == value for key, value in expect.items())


def ask(bot, question):
    started = time.perf_counter()
    final = []
    for update in bot.run(messages=[{"role": "user", "content": question}]):
        final = update
    calls = [resolved_args(c) | {"raw": c} for c in tool_calls(final)]
    return {"question": question, "tool_calls": calls, "answer": final_content(final),
            "seconds": round(time.perf_counter() - started, 1)}


def main():
    parser = argparse.ArgumentParser(description="Qwen picks the KG lookup (Test 2)")
    parser.add_argument("question", nargs="?", help="ask one question instead of the paraphrase set")
    args = parser.parse_args()

    check_llm()
    bot = make_bot()
    model = llm_config()["model"]
    if args.question:
        result = ask(bot, args.question)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        log_run({"test": "kg_agent", "model": model, **result})
        return

    cases = json.loads((QUERIES / "paraphrases.json").read_text(encoding="utf-8"))
    passed = 0
    for i, case in enumerate(cases, 1):
        result = ask(bot, case["question"])
        ok = any(matches(call, case["expect"]) for call in result["tool_calls"])
        passed += ok
        print(f"[{i}/{len(cases)}] {'PASS' if ok else 'FAIL'} ({result['seconds']} s) {case['question']}")
        print("  expected:", case["expect"])
        print("  called:  ", [{k: v for k, v in c.items() if k != "raw"} for c in result["tool_calls"]])
        print("  answer:  ", result["answer"].replace("\n", " ")[:300])
        log_run({"test": "kg_agent", "model": model, "expect": case["expect"], "pass": ok, **result})
    print(f"\n{passed}/{len(cases)} paraphrases produced the expected tool call")


if __name__ == "__main__":
    main()
