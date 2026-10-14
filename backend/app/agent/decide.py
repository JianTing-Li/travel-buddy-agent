"""One Anthropic model call that returns tool calls or a text reply, never raising on bad output. Owner: Cheich."""
from dataclasses import dataclass, field
from typing import Any

import anthropic


@dataclass
class ToolCall:
    id: str
    name: str
    input: Any  # validated by the loop, may be malformed


@dataclass
class Decision:
    kind: str  # "tool_calls" | "text" | "error"
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_content: list[dict[str, Any]] = field(default_factory=list)  # blocks to add to history
    error: str = ""


def decide(
    client: Any,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    max_tokens: int = 1024,
) -> Decision:
    """Call the model once. Returns tool calls, a text reply, or an error. Never raises on API or output problems."""
    try:
        response = client.messages.create(
            model=model, max_tokens=max_tokens, system=system, tools=tools, messages=messages
        )
    except anthropic.APIError as exc:
        return Decision(kind="error", error=f"Model call failed: {type(exc).__name__}")
    except Exception as exc:  # unexpected client failure, keep the app alive
        return Decision(kind="error", error=f"Model call failed: {type(exc).__name__}")

    blocks = getattr(response, "content", None)
    if not isinstance(blocks, list) or not blocks:
        return Decision(kind="error", error="Model returned an empty response")

    text_parts: list[str] = []
    content: list[dict[str, Any]] = []
    calls: list[ToolCall] = []
    for block in blocks:
        btype = getattr(block, "type", None)
        if btype == "text":
            text = getattr(block, "text", "") or ""
            text_parts.append(text)
            content.append({"type": "text", "text": text})
        elif btype == "tool_use":
            call = ToolCall(
                id=getattr(block, "id", "") or "",
                name=getattr(block, "name", "") or "",
                input=getattr(block, "input", None),
            )
            calls.append(call)
            # history must hold a valid object, the loop reports the malformed input back to the model
            safe_input = call.input if isinstance(call.input, dict) else {}
            content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": safe_input})
        # other block types are ignored

    if calls:
        if getattr(response, "stop_reason", None) == "max_tokens":
            return Decision(kind="error", error="Model output was cut off while calling a tool")
        if any(not c.id for c in calls):
            return Decision(kind="error", error="Model returned a tool call without an id")
        return Decision(kind="tool_calls", text="\n".join(text_parts), tool_calls=calls, assistant_content=content)

    text = "\n".join(text_parts).strip()
    if not text:
        return Decision(kind="error", error="Model returned no text and no tool call")
    return Decision(kind="text", text=text, assistant_content=content)
