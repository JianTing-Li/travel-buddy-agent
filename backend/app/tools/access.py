"""Booking access and source routing shared by the agent tools. Owner: Jian.

Every tool call names a booking id chosen by the model, so each call is checked here first:
- the booking must be one this session may access (otherwise it looks exactly like an unknown booking);
- the booking id decides the service: MOCK-... goes to the mock service. Duffel bookings are not wired yet;
- an option must carry the data_source of the service handling it, so a mock option never reaches Duffel.
"""
import functools
from typing import Any, Callable

from ..contract.models import Option
from ..services.mock.mock_service import DUFFEL_ID_PREFIXES, MockService, MockServiceError

MOCK_BOOKING_PREFIX = "MOCK-"
NOT_FOUND = "Booking not found or not available in this session."
LimitsFilter = Callable[[list[Option], dict[str, Any]], list[Option]]


class ToolError(Exception):
    """A tool could not complete. The message is safe to show to the model."""


class BookingRouter:
    def __init__(self, mock: MockService, allowed_booking_ids: set[str] | None = None) -> None:
        self.mock = mock
        self._allowed = None if allowed_booking_ids is None else set(allowed_booking_ids)

    def service_for(self, booking_id: Any) -> MockService:
        """Return the service for a booking this session may access, or raise ToolError."""
        if not isinstance(booking_id, str) or not booking_id:
            raise ToolError("booking_id must be a non-empty string.")
        if self._allowed is not None and booking_id not in self._allowed:
            raise ToolError(NOT_FOUND)
        if booking_id.startswith(DUFFEL_ID_PREFIXES):
            raise ToolError("Duffel bookings aren't supported by the tools yet.")
        if booking_id.startswith(MOCK_BOOKING_PREFIX):
            return self.mock
        raise ToolError(NOT_FOUND)

    @staticmethod
    def check_source(option: Option, expected: str = "mock") -> None:
        if option.data_source != expected:
            raise ToolError(f"Option '{option.option_id}' comes from '{option.data_source}', "
                            f"not from the '{expected}' service handling this booking.")


def mock_errors_as_tool_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Turn mock service errors into ToolError, keeping the service's message."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except MockServiceError as exc:
            raise ToolError(str(exc)) from None

    return wrapper
