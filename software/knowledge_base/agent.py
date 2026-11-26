"""Optional Qwen-Agent integration; requires a running LOCAL model endpoint."""
import json
import os
import json5
from qwen_agent.agents import Assistant
from qwen_agent.tools.base import BaseTool, register_tool
from client import lookup_task


@register_tool("lookup_task")
class LookupTask(BaseTool):
    description = "Look up a known task ID, its stored/inferred types and evidence."
    parameters = [{"name": "task_id", "type": "string", "required": True,
                   "description": "Known identifier such as task1; never guess an ID."}]

    def call(self, params: str, **kwargs) -> str:
        try:
            args = json5.loads(params)
            return json.dumps(lookup_task(args["task_id"]), ensure_ascii=False)
        except Exception as exc:
            # Return bounded diagnostic; production code should log full details privately.
            return json.dumps({"error": str(exc)[:500]})


if __name__ == "__main__":
    bot = Assistant(
        llm={"model": os.environ["LOCAL_MODEL_NAME"],
             "model_server": os.environ.get("LOCAL_MODEL_URL", "http://127.0.0.1:8000/v1"),
             "api_key": "EMPTY"},
        function_list=["lookup_task"],
        system_message=("Use the task lookup for factual task questions. Cite evidence IDs. "
                        "Distinguish stored facts from inferred classifications; "
                        "if a task is missing, report unknown.")
    )
    for response in bot.run(messages=[{"role": "user", "content":
            "What is task1, what classes does it belong to, and what supports it?"}]):
        print(response)
