"""Model stand-ins for the eval runner: a recorder (works with the real model too) and a scripted model. Owner: Cheich.

The recorder sits between Jian's chat endpoint and any model client. It does not change anything; it remembers every
tool call the model made and what the tools answered, so the checks can look at what really happened.
"""
import copy
import itertools
from types import SimpleNamespace as NS
from typing import Any

_ids = itertools.count(1)


def text(t: str) -> NS:
    return NS(type="text", text=t)


def tool(name: str, input: dict[str, Any]) -> NS:
    return NS(type="tool_use", id=f"toolu_eval_{next(_ids)}", name=name, input=input)


def resp(*blocks: NS, stop_reason: str = "end_turn") -> NS:
    return NS(content=list(blocks), stop_reason=stop_reason)


class ScriptedModel:
    """Plays back prepared replies in order. It never looks at the conversation: it tests the code around the model."""

    def __init__(self) -> None:
        self._replies: list[NS] = []
        self.messages = NS(create=self._create)

    def queue(self, *replies: NS) -> None:
        self._replies.extend(replies)

    def _create(self, **kwargs: Any) -> NS:
        if not self._replies:
            raise AssertionError("The scripted model ran out of replies: the code asked for more steps than scripted.")
        return self._replies.pop(0)


class RecordingModel:
    """Wraps a model client (scripted or the real Anthropic client) and records the tool calls and their results."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.turn = 0  # the runner sets this before each chat message
        self.calls: list[dict[str, Any]] = []
        self._last_messages: list[dict[str, Any]] = []
        self.messages = NS(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self._last_messages = copy.deepcopy(kwargs.get("messages", []))
        reply = self.inner.messages.create(**kwargs)
        for block in getattr(reply, "content", None) or []:
            if getattr(block, "type", None) == "tool_use":
                self.calls.append({"turn": self.turn, "id": block.id, "name": block.name,
                                   "input": copy.deepcopy(block.input), "result": None, "is_error": False})
        return reply

    def collect_results(self) -> None:
        """Attach each tool's answer to its call. Call once at the end: the last request holds the whole history."""
        answers: dict[str, dict[str, Any]] = {}
        for message in self._last_messages:
            content = message.get("content")
            if message.get("role") == "user" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        answers[block["tool_use_id"]] = block
        for call in self.calls:
            block = answers.get(call["id"])
            if block is not None:
                call["result"] = block.get("content")
                call["is_error"] = bool(block.get("is_error"))
