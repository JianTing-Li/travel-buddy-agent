"""Claude tool-use loop: runs once per traveler message. Owner: Cheich."""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from backend.app.agent.decide import ToolCall, decide
from backend.app.harness.guards import wrap_untrusted
from backend.app.harness.requirements import check_limits

PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt_v0.txt"
DEFAULT_MAX_STEPS = 8
STEP_LIMIT_REPLY = "I wasn't able to finish that. Please try again or rephrase your request."
ERROR_REPLY = "Something went wrong on my side. Please try again."
MAX_CONTINUATIONS = 2
CONTINUE_MESSAGE = ("Your last reply was cut off. Continue from exactly where it stopped, "
                    "with no recap and nothing repeated.")


@dataclass
class TurnResult:
    reply: str
    history: list[dict[str, Any]]
    stopped_reason: str  # "reply" | "step_limit" | "error"
    steps: int
    error: str = ""


def load_system_prompt(path: Path = PROMPT_PATH) -> str:
    if not path.exists():
        raise FileNotFoundError(f"System prompt not found at {path}")
    return path.read_text(encoding="utf-8")


def _run_tool(call: ToolCall, tools: dict[str, Callable[..., Any]]) -> dict[str, Any]:
    """Run one tool call. Any failure becomes an error tool_result the model can see."""
    def result(content: str, is_error: bool = False) -> dict[str, Any]:
        out = {"type": "tool_result", "tool_use_id": call.id, "content": content}
        if is_error:
            out["is_error"] = True
        return out

    fn = tools.get(call.name)
    if fn is None:
        return result(f"Unknown tool '{call.name}'. Available tools: {', '.join(sorted(tools))}.", True)
    if not isinstance(call.input, dict):
        return result("Tool input must be a JSON object.", True)
    if call.name == "search_replacements":  # never search on missing or invalid required limits
        check = check_limits(call.input.get("limits"))
        if not check.ok:
            return result(check.message, True)
    try:
        return result(json.dumps(wrap_untrusted(fn(**call.input)), default=str))
    except TypeError as exc:
        return result(f"Invalid arguments for '{call.name}': {exc}", True)
    except Exception as exc:
        return result(f"Tool '{call.name}' failed: {type(exc).__name__}: {exc}", True)


def run_turn(
    client: Any,
    model: str,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_message: str,
    tools: dict[str, Callable[..., Any]],
    tool_schemas: list[dict[str, Any]],
    max_steps: int = DEFAULT_MAX_STEPS,
) -> TurnResult:
    """Handle one traveler message. Returns the reply and the updated history.

    The turn ends when the model replies with text (including a question to the traveler),
    on an error, or when max_steps model calls are used. On error, history is left unchanged.
    A reply cut off by the token limit is continued automatically (up to MAX_CONTINUATIONS times),
    and the traveler sees the joined text. If it is still cut off after that, the turn is an error.
    """
    messages = [*history, {"role": "user", "content": user_message}]
    parts: list[str] = []

    for step in range(1, max_steps + 1):
        decision = decide(client, model, system_prompt, messages, tool_schemas)

        if decision.kind == "error":
            return TurnResult(ERROR_REPLY, history, "error", step, decision.error)

        messages.append({"role": "assistant", "content": decision.assistant_content})

        if decision.kind == "text":
            parts.append(decision.text)
            if not decision.truncated:
                return TurnResult("".join(parts), messages, "reply", step)
            if len(parts) > MAX_CONTINUATIONS:
                return TurnResult(ERROR_REPLY, history, "error", step, "Reply still cut off after continuing")
            messages.append({"role": "user", "content": CONTINUE_MESSAGE})
            continue

        results = [_run_tool(call, tools) for call in decision.tool_calls]
        messages.append({"role": "user", "content": results})

    messages.append({"role": "assistant", "content": [{"type": "text", "text": STEP_LIMIT_REPLY}]})
    return TurnResult(STEP_LIMIT_REPLY, messages, "step_limit", max_steps)
