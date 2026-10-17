"""In-memory traveler sessions: which bookings a session may access, plus its tools and confirmation gate. Owner: Jian.

There is no login in MVP 1. A session id is a random secret returned by POST /sessions and sent back in the
X-Session-Id header. Each session gets its own MockService, so one session's simulated rebooking never
affects another, and its tools are built with only that session's booking ids.
Sessions live in memory: a restart drops them. Idle sessions expire and the store has a size cap.
"""
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from ..harness.confirmation import ConfirmationGate
from ..harness.limits import limits_filter
from ..services.duffel.client import DuffelClient
from ..services.duffel.service import DuffelService
from ..services.mock.generator import generate_scenario
from ..services.mock.mock_service import MockService
from ..services.mock.scenarios import Scenario, scenario_names
from ..tools.registry import ToolSet, build_tools

SESSION_IDLE_SECONDS = 12 * 60 * 60
MAX_SESSIONS = 200
MAX_BOOKINGS_PER_SESSION = 50
# On-time bookings every default session starts with next to the PRD cases, so the list is not only disruptions.
# (booking id, generator seed); the seed fixes the route, times and options.
STARTER_ON_TIME = (("MOCK-ONTIME-1", 1), ("MOCK-ONTIME-2", 6))


class UnknownScenarioError(ValueError):
    pass


class TooManyBookingsError(ValueError):
    pass


class DuffelNotConfiguredError(ValueError):
    pass


@dataclass
class Session:
    session_id: str
    service: MockService
    toolset: ToolSet
    gate: ConfirmationGate
    tools: dict[str, Callable[..., Any]]  # the agent's tools: gate-wrapped, recording each prepare result
    allowed_ids: set[str]  # the bookings this session's tools may reach; shared with the tools, grows with new bookings
    duffel: DuffelService | None = None  # this session's Duffel TEST bookings; None when Duffel isn't configured
    histories: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # booking_id -> chat history
    prepared: dict[str, dict[str, Any]] = field(default_factory=dict)  # booking_id -> latest prepare_rebooking result
    notices: dict[str, list[str]] = field(default_factory=dict)  # booking_id -> app notices for the next chat turn
    shown_changes: dict[str, set[str]] = field(default_factory=dict)  # booking_id -> change ids already shown
    scenario_names: list[str] = field(default_factory=list)  # the mock scenarios this session started with
    starters: bool = False  # whether it also started with the on-time starter bookings
    duffel_client: DuffelClient | None = None  # kept so a reset can start a fresh Duffel service
    last_used: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)  # one request at a time per session

    @property
    def booking_ids(self) -> list[str]:
        return [*self.service.booking_ids(), *(self.duffel.booking_ids() if self.duffel else [])]

    def owns(self, booking_id: str) -> bool:
        return booking_id in self.booking_ids

    def service_for(self, booking_id: str) -> MockService | DuffelService:
        """The service that holds this booking (the caller has already checked owns())."""
        if self.duffel is not None and booking_id in self.duffel.booking_ids():
            return self.duffel
        return self.service

    def _check_room(self) -> None:
        if len(self.booking_ids) >= MAX_BOOKINGS_PER_SESSION:
            raise TooManyBookingsError(f"A session can hold at most {MAX_BOOKINGS_PER_SESSION} bookings.")

    def add_duffel_booking(self, order_id: str) -> str:
        """Track a Duffel TEST order in this session and let its tools reach it."""
        if self.duffel is None:
            raise DuffelNotConfiguredError("Duffel isn't configured on the server.")
        self._check_room()
        booking_id = self.duffel.add_booking(order_id)
        self.allowed_ids.add(booking_id)
        return booking_id

    def add_booking(self, scenario: Scenario) -> str:
        """Add a generated mock booking to this session and let its tools reach it."""
        self._check_room()
        booking_id = self.service.add_booking(scenario)
        self.allowed_ids.add(booking_id)
        return booking_id

    def clear_disruption(self, booking_id: str) -> None:
        """Put one mock booking back to normal (on time) and forget its chat, card, notices and gate state.
        The caller holds the session lock and has checked it is a mock booking."""
        self.service.clear_disruption(booking_id)
        self.gate.forget(booking_id)
        for per_booking in (self.histories, self.prepared, self.notices, self.shown_changes):
            per_booking.pop(booking_id, None)

    def reset(self) -> None:
        """Start this session over: its first mock bookings only, nothing generated, changed, faulted or rebooked,
        no chat history. Duffel test bookings leave the session (the orders stay on the Duffel test account).
        Other sessions are untouched. The caller holds the session lock."""
        parts = _build(self.scenario_names, self.duffel_client, self.starters)
        self.service, self.toolset, self.gate, self.tools = parts.service, parts.toolset, parts.gate, parts.tools
        self.allowed_ids, self.duffel, self.prepared = parts.allowed_ids, parts.duffel, parts.prepared
        self.histories, self.notices, self.shown_changes = {}, {}, {}


@dataclass
class _Parts:
    service: MockService
    toolset: ToolSet
    gate: ConfirmationGate
    tools: dict[str, Callable[..., Any]]
    allowed_ids: set[str]
    duffel: DuffelService | None
    prepared: dict[str, dict[str, Any]]


def _build(names: list[str], client: DuffelClient | None, starters: bool = False) -> _Parts:
    """Everything a session needs, wired together: services, tools, the confirmation gate."""
    service = MockService(scenarios=list(dict.fromkeys(names)))
    if starters:
        for booking_id, seed in STARTER_ON_TIME:
            service.add_booking(generate_scenario(seed, situation="on time", booking_id=booking_id))
    allowed = set(service.booking_ids())
    duffel = DuffelService(client) if client is not None else None
    toolset = build_tools(service, allowed_booking_ids=allowed, duffel=duffel, limits_filter=limits_filter)
    # strict: nothing can be prepared or confirmed until a search checked by code has confirmed the traveler's limits
    gate = ConfirmationGate(toolset.tools, toolset.complete_rebooking, source="real", require_checked_search=True)
    prepared: dict[str, dict[str, Any]] = {}
    gate_tools = gate.tools()

    def prepare_rebooking(booking_id: str, option_id: str) -> dict[str, Any]:
        result = gate_tools["prepare_rebooking"](booking_id=booking_id, option_id=option_id)
        prepared[booking_id] = result  # what the confirm card shows comes from this, not from the model
        return result

    tools = {**gate_tools, "prepare_rebooking": prepare_rebooking}
    return _Parts(service, toolset, gate, tools, allowed, duffel, prepared)


class SessionStore:
    def __init__(
        self,
        idle_seconds: float = SESSION_IDLE_SECONDS,
        max_sessions: int = MAX_SESSIONS,
        duffel_client_factory: Callable[[], DuffelClient | None] | None = None,
    ) -> None:
        self._duffel_client_factory = duffel_client_factory
        self._idle_seconds = idle_seconds
        self._max_sessions = max_sessions
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, scenarios: list[str] | None = None) -> Session:
        known = scenario_names()
        names = known if scenarios is None else scenarios
        unknown = [n for n in names if n not in known]
        if unknown or not names:
            raise UnknownScenarioError(f"Unknown or empty scenarios. Choose from: {', '.join(known)}")
        client = self._duffel_client_factory() if self._duffel_client_factory else None
        starters = scenarios is None  # a session asking for specific scenarios gets exactly those
        p = _build(names, client, starters)
        session = Session(secrets.token_urlsafe(32), p.service, p.toolset, p.gate, p.tools, p.allowed_ids, p.duffel,
                          prepared=p.prepared, scenario_names=list(names), starters=starters, duffel_client=client)
        with self._lock:
            self._expire()
            while len(self._sessions) >= self._max_sessions:
                oldest = min(self._sessions.values(), key=lambda s: s.last_used)
                del self._sessions[oldest.session_id]
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str | None) -> Session | None:
        if not session_id:
            return None
        with self._lock:
            self._expire()
            session = self._sessions.get(session_id)
            if session is not None:
                session.last_used = time.monotonic()
            return session

    def _expire(self) -> None:
        cutoff = time.monotonic() - self._idle_seconds
        for session_id in [s.session_id for s in self._sessions.values() if s.last_used < cutoff]:
            del self._sessions[session_id]

    def __len__(self) -> int:
        return len(self._sessions)
