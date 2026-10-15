"""Registry of the agent tools. Owner: Jian.

Implements the contract in agent/tool_source.py:
  TOOLS               tool name -> function taking keyword arguments, returning a JSON-ready dict
  TOOL_SCHEMAS        Anthropic tool definitions for the same four tools
  complete_rebooking  completes the SIMULATED rebooking after the traveler confirmed; not a model tool

The module-level values use a shared MockService with every mock booking allowed. The API should call
build_tools() per session instead, passing only the bookings that session may access.
Only mock bookings are wired today; Duffel bookings return a clear "not supported yet" error.
"""
from dataclasses import dataclass
from typing import Any, Callable

from ..services.mock.mock_service import MockService
from . import escalate_to_support, get_trip_context, prepare_rebooking, search_replacements
from .access import BookingRouter, LimitsFilter, mock_errors_as_tool_errors


@dataclass(frozen=True)
class ToolSet:
    tools: dict[str, Callable[..., dict[str, Any]]]
    schemas: list[dict[str, Any]]
    complete_rebooking: Callable[[str, str], dict[str, Any]]


SCHEMAS: list[dict[str, Any]] = [
    get_trip_context.SCHEMA,
    search_replacements.SCHEMA,
    prepare_rebooking.SCHEMA,
    escalate_to_support.SCHEMA,
]


def build_tools(
    service: MockService | None = None,
    allowed_booking_ids: set[str] | None = None,
    limits_filter: LimitsFilter | None = None,
) -> ToolSet:
    """Build the tools for one session. allowed_booking_ids=None allows every mock booking (tests and demos)."""
    router = BookingRouter(service or MockService(), allowed_booking_ids)

    @mock_errors_as_tool_errors
    def complete_rebooking(booking_id: str, option_id: str) -> dict[str, Any]:
        """Complete after explicit confirmation. Routes by booking source and raises on any failure."""
        service = router.service_for(booking_id)
        router.check_source(service.get_option(booking_id, option_id))
        return service.complete_rebooking(booking_id, option_id)

    tools = {
        "get_trip_context": get_trip_context.make(router),
        "search_replacements": search_replacements.make(router, limits_filter),
        "prepare_rebooking": prepare_rebooking.make(router),
        "escalate_to_support": escalate_to_support.make(router),
    }
    return ToolSet(tools=tools, schemas=[dict(s) for s in SCHEMAS], complete_rebooking=complete_rebooking)


_default = build_tools()
TOOLS = _default.tools
TOOL_SCHEMAS = _default.schemas
complete_rebooking = _default.complete_rebooking
