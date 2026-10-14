"""The one place that chooses which tools the agent uses: stub (mock data) or real (Jian's tools). Owner: Cheich.

Switching is a single argument: get_tool_source("stub", scenario="case_2") or get_tool_source("real").
The loop (loop.py) does not change.

Contract for Jian's backend/app/tools/registry.py (agree with Jian before relying on it):
  TOOLS: dict[str, Callable[..., dict]]   tool name -> function taking keyword arguments, returning a JSON-ready dict
  TOOL_SCHEMAS: list[dict]                Anthropic tool definitions (name, description, input_schema)
  complete_rebooking(booking_id, option_id) -> dict
                                          completes the simulated rebooking AFTER the traveler confirmed. Not a model
                                          tool. Must route by the option's source (duffel or mock) and raise on failure.
Tool names: get_trip_context, search_replacements, prepare_rebooking, escalate_to_support.
"""
import importlib
from dataclasses import dataclass
from typing import Any, Callable

REQUIRED_TOOLS = {"get_trip_context", "search_replacements", "prepare_rebooking", "escalate_to_support"}


class ToolSourceError(Exception):
    pass


@dataclass
class ToolSource:
    name: str
    tools: dict[str, Callable[..., Any]]
    schemas: list[dict[str, Any]]
    complete_rebooking: Callable[[str, str], dict[str, Any]]


def check_tool_source(tools: Any, schemas: Any) -> list[str]:
    """Return a list of problems (empty means the tools fit what the loop expects)."""
    if not isinstance(tools, dict) or not isinstance(schemas, list):
        return ["tools must be a dict and schemas must be a list"]
    problems = []
    schema_names = []
    for s in schemas:
        if not isinstance(s, dict) or not s.get("name") or not s.get("description") \
                or not isinstance(s.get("input_schema"), dict):
            problems.append(f"bad schema entry: {s!r:.80}")
        else:
            schema_names.append(s["name"])
    for name in tools:
        if not callable(tools[name]):
            problems.append(f"tool '{name}' is not callable")
    if set(schema_names) != set(tools):
        problems.append(f"schema names {sorted(schema_names)} do not match tool names {sorted(tools)}")
    missing = REQUIRED_TOOLS - set(tools)
    if missing:
        problems.append(f"missing required tools: {sorted(missing)}")
    return problems


def get_tool_source(source: str = "stub", scenario: str = "case_1") -> ToolSource:
    if source == "stub":
        from backend.app.agent.stub_tools import (
            SCENARIOS, STUB_TOOL_SCHEMAS, build_stub_completer, build_stub_tools,
        )
        if scenario not in SCENARIOS:
            raise ToolSourceError(f"Unknown scenario '{scenario}'. Choose from: {', '.join(SCENARIOS)}")
        tools, schemas = build_stub_tools(scenario), STUB_TOOL_SCHEMAS
        complete = build_stub_completer(scenario)
    elif source == "real":
        try:
            registry = importlib.import_module("backend.app.tools.registry")
        except ImportError as exc:
            raise ToolSourceError(f"Could not import backend.app.tools.registry: {exc}") from exc
        tools = getattr(registry, "TOOLS", None)
        schemas = getattr(registry, "TOOL_SCHEMAS", None)
        complete = getattr(registry, "complete_rebooking", None)
        if tools is None or schemas is None or not callable(complete):
            raise ToolSourceError(
                "registry.py must define TOOLS, TOOL_SCHEMAS and complete_rebooking (see tool_source.py docstring)")
    else:
        raise ToolSourceError(f"Unknown tool source '{source}'. Use 'stub' or 'real'.")

    problems = check_tool_source(tools, schemas)
    if problems:
        raise ToolSourceError(f"'{source}' tools do not fit the loop: " + "; ".join(problems))
    return ToolSource(source, tools, schemas, complete)
