"""Tool: load the original booking, passengers and airline-change details. Owner: Jian."""
from typing import Any, Callable

from .access import BookingRouter, mock_errors_as_tool_errors

SCHEMA: dict[str, Any] = {
    "name": "get_trip_context",
    "description": (
        "Load the traveler's original booking, passengers and disruption details. The data_source field says "
        "whether the booking is a simulated mock booking or a Duffel test booking."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"booking_id": {"type": "string", "description": "The traveler's booking id."}},
        "required": ["booking_id"],
    },
}


def make(router: BookingRouter) -> Callable[..., dict[str, Any]]:
    @mock_errors_as_tool_errors
    def get_trip_context(booking_id: str) -> dict[str, Any]:
        return router.service_for(booking_id).get_trip_context(booking_id).model_dump()

    return get_trip_context
