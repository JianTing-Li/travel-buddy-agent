"""Tool: recheck the selected option before confirmation. Owner: Jian."""
from typing import Any, Callable

from .access import BookingRouter, mock_errors_as_tool_errors

SCHEMA: dict[str, Any] = {
    "name": "prepare_rebooking",
    "description": (
        "Recheck the option the traveler selected: availability, eligibility and additional cost right now. "
        "Returns the latest option details, a validation_result, and any changes the traveler must review. "
        "This does not rebook anything; application code completes the rebooking only after the traveler "
        "explicitly confirms."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"booking_id": {"type": "string"}, "option_id": {"type": "string"}},
        "required": ["booking_id", "option_id"],
    },
}


def make(router: BookingRouter) -> Callable[..., dict[str, Any]]:
    @mock_errors_as_tool_errors
    def prepare_rebooking(booking_id: str, option_id: str) -> dict[str, Any]:
        service = router.service_for(booking_id)
        router.check_source(service.get_option(booking_id, option_id))
        return service.prepare_rebooking(booking_id, option_id).model_dump()

    return prepare_rebooking
