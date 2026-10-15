"""Tool: retrieve replacement options. Owner: Jian.

Options are for everyone on the booking together, and additional_cost is for the whole booking.
When a limits filter is plugged in (Cheich's harness/limits.py), it removes options outside the confirmed
limits before the model sees them. Until then every option is returned and limits_checked_by_code is false.
"""
from typing import Any, Callable

from .access import BookingRouter, LimitsFilter, ToolError, mock_errors_as_tool_errors

LIMITS_PROPERTIES: dict[str, Any] = {
    "budget_additional_cost": {"type": "number", "description": "Most the traveler will pay extra, whole booking."},
    "arrival_window": {"type": "string", "description": "When the traveler must arrive, as confirmed."},
    "max_connections": {"type": "integer"},
    "passenger_count": {"type": "integer"},
}

SCHEMA: dict[str, Any] = {
    "name": "search_replacements",
    "description": (
        "Retrieve replacement options that keep every passenger on the same itinerary. Pass the traveler's "
        "confirmed required limits. Each option shows eligibility, the additional cost for the whole booking, "
        "currency, validity and data_source. Use only these values; never invent options or prices."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "booking_id": {"type": "string"},
            "limits": {"type": "object", "properties": LIMITS_PROPERTIES,
                       "description": "The traveler's confirmed required limits."},
        },
        "required": ["booking_id"],
    },
}


def make(router: BookingRouter, limits_filter: LimitsFilter | None = None) -> Callable[..., dict[str, Any]]:
    @mock_errors_as_tool_errors
    def search_replacements(booking_id: str, limits: dict[str, Any] | None = None) -> dict[str, Any]:
        if limits is not None and not isinstance(limits, dict):
            raise ToolError("limits must be an object.")
        service = router.service_for(booking_id)
        options = service.search_replacements(booking_id)
        for option in options:
            router.check_source(option)
        checked = limits_filter is not None and limits is not None
        if checked:
            options = limits_filter(options, limits)
        return {
            "booking_id": booking_id,
            "options": [o.model_dump() for o in options],
            "limits_checked_by_code": checked,
        }

    return search_replacements
