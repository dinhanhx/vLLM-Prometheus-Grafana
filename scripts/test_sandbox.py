import json
from openai import OpenAI
from llm_sandbox import SandboxSession

client = OpenAI(base_url="http://localhost:8791/v1", api_key="EMPTY")
MODEL = "Qwen/Qwen3-4B-Instruct-2507-FP8"

tools = [
    {
        "type": "function",
        "function": {
            "name": "run_python_code",
            "description": (
                "Execute Python code in a secure sandbox and return stdout. "
                "Use this for any calculation, data processing, or computation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The Python code to execute",
                    },
                    "libraries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional pip packages to install before running",
                    },
                },
                "required": ["code"],
            },
        },
    }
]


def run_python_code(code: str, libraries: list[str] | None = None) -> str:
    with SandboxSession(lang="python", verbose=False) as session:
        result = session.run(code, libraries=libraries or [])
    if result.exit_code != 0:
        return f"Error (exit {result.exit_code}):\n{result.stderr}"
    return result.stdout.strip()


TOOL_DISPATCH = {"run_python_code": run_python_code}


def chat(user_message: str) -> str:
    messages = [{"role": "user", "content": user_message}]

    while True:
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        msg = response.choices[0].message

        # No tool call → final answer
        if not msg.tool_calls:
            return msg.content

        # Append assistant message with tool_calls
        messages.append(msg)

        # Execute each tool call and feed results back
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            fn = TOOL_DISPATCH[tc.function.name]
            output = fn(**args)
            print(f"[sandbox] {tc.function.name}({args}) →\n{output}\n")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output,
                }
            )


if __name__ == "__main__":
    answer = chat(r"What is sum of the first 100 primes?")
    print("Answer:", answer)
