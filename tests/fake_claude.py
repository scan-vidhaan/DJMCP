"""Stand-in for `claude -p --agent dj-orchestrator ...` used by the runner tests.

Emits stream-json lines like the real CLI and drives the state store the way
the orchestrator would: ask a question on the first run, finish on resume.
"""

import json
import re
import sys

from djmcp.tools import state


def emit(event: dict) -> None:
    print(json.dumps(event), flush=True)


def say(text: str) -> None:
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})


def main() -> int:
    prompt = sys.argv[sys.argv.index("-p") + 1]
    job_id = re.search(r"job_id=(\w+)", prompt).group(1)
    if "crash" in prompt:
        sys.stderr.write("boom")
        return 3
    if "quit-early" in prompt:
        say("hmm")
        return 0

    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "mcp__djmcp__state_get"}]}})
    answer = state.state_request_input(job_id, "style", "Mashup style?", ["Sequence", "Layered"], "Sequence")
    if not answer["answered"]:
        say("Waiting for your choice.")
        return 0

    say(f"Using style {answer['answer']}.")
    state.state_update(job_id, "mix_1", "done")
    state.state_complete(job_id, {"track_id": "fake-output"})
    emit({"type": "result", "result": "done", "is_error": False})
    return 0


if __name__ == "__main__":
    sys.exit(main())
