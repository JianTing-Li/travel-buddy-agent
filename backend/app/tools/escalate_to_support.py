"""Tool: prepare a simulated support handoff. Owner: Jian.

confirmed_needs is supplied by the model for now and validated against the contract's Limits. Once the
harness tracks confirmed limits per session, it should inject them instead.
"""
from typing import Any, Callable

from pydantic import ValidationError

from ..contract.models import Limits
from .access import BookingRouter, ToolError, mock_errors_as_tool_errors
from .search_replacements import LIMITS_PROPERTIES

SCHEMA: dict[str, Any] = {
    "name": "escalate_to_support",
    "description": (
        "Prepare a SIMULATED support handoff when the case is unresolved, eligibility cannot be verified, or a "
        "tool fails. Include the traveler's confirmed needs and the unresolved issue. Tell the traveler that no "
        "real staff will follow up."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "booking_id": {"type": "string"},
            "unresolved_issue": {"type": "string", "description": "What could not be resolved, in plain words."},
            "confirmed_needs": {"type": "object", "properties": LIMITS_PROPERTIES,
                                "required": list(LIMITS_PROPERTIES)},
        },
        "required": ["booking_id", "unresolved_issue", "confirmed_needs"],
    },
}


def make(router: BookingRouter) -> Callable[..., dict[str, Any]]:
    @mock_errors_as_tool_errors
    def escalate_to_support(booking_id: str, unresolved_issue: str, confirmed_needs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(unresolved_issue, str) or not unresolved_issue.strip():
            raise ToolError("unresolved_issue must describe the problem.")
        if not isinstance(confirmed_needs, dict):
            raise ToolError("confirmed_needs must be an object.")
        try:
            needs = Limits(**confirmed_needs)
        except ValidationError:
            raise ToolError("confirmed_needs must include " + ", ".join(LIMITS_PROPERTIES) + ".") from None
        service = router.service_for(booking_id)
        return service.escalate_to_support(booking_id, unresolved_issue.strip(), needs).model_dump()

    return escalate_to_support
