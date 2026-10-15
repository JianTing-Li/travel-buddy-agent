"""Booking access and source routing shared by the agent tools. Owner: Jian.

Every tool call names a booking id chosen by the model, so each call is checked here first:
- the booking must be one this session may access (otherwise it looks exactly like an unknown booking);
- the booking id decides the service: MOCK-... goes to the mock service and ord_... to the Duffel test service
  (only when the session has one). No other id is a booking;
- an option must carry the data_source of the service handling it, so a mock option never reaches Duffel.
"""
import functools
from typing import Any, Callable

from ..contract.models import Option
from ..services.duffel.service import ORDER_PREFIX, DuffelService
from ..services.errors import ServiceError
from ..services.mock.mock_service import MockService

MOCK_BOOKING_PREFIX = "MOCK-"
NOT_FOUND = "Booking not found or not available in this session."
LimitsFilter = Callable[[list[Option], dict[str, Any]], list[Option]]


class ToolError(Exception):
    """A tool could not complete. The message is safe to show to the model."""


class BookingRouter:
    def __init__(
        self, mock: MockService, allowed_booking_ids: set[str] | None = None, duffel: DuffelService | None = None
    ) -> None:
        self.mock = mock
        self.duffel = duffel
        # Kept by reference on purpose: the session adds generated bookings to this set as they are created.
        self._allowed = allowed_booking_ids

    def service_for(self, booking_id: Any) -> MockService | DuffelService:
        """Return the service for a booking this session may access, or raise ToolError."""
        if not isinstance(booking_id, str) or not booking_id:
            raise ToolError("booking_id must be a non-empty string.")
        if self._allowed is not None and booking_id not in self._allowed:
            raise ToolError(NOT_FOUND)
        if booking_id.startswith(ORDER_PREFIX):
            if self.duffel is None:
                raise ToolError("Duffel bookings aren't available in this session.")
            return self.duffel
        if booking_id.startswith(MOCK_BOOKING_PREFIX):
            return self.mock
        raise ToolError(NOT_FOUND)

    @staticmethod
    def check_source(option: Option, booking_id: str) -> None:
        """The option must come from the service that handles this booking: never mix mock and Duffel."""
        expected = "duffel" if booking_id.startswith(ORDER_PREFIX) else "mock"
        if option.data_source != expected:
            raise ToolError(f"Option '{option.option_id}' comes from '{option.data_source}', "
                            f"not from the '{expected}' service handling this booking.")


def mock_errors_as_tool_errors(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Turn service errors (mock or Duffel) into ToolError, keeping their safe messages."""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ServiceError as exc:
            raise ToolError(str(exc)) from None

    return wrapper
