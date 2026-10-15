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
from ..services.mock.mock_service import MockService
from ..services.mock.scenarios import scenario_names
from ..tools.registry import ToolSet, build_tools

SESSION_IDLE_SECONDS = 12 * 60 * 60
MAX_SESSIONS = 200


class UnknownScenarioError(ValueError):
    pass


@dataclass
class Session:
    session_id: str
    service: MockService
    toolset: ToolSet
    gate: ConfirmationGate
    tools: dict[str, Callable[..., Any]]  # the agent's tools: gate-wrapped, recording each prepare result
    histories: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # booking_id -> chat history
    prepared: dict[str, dict[str, Any]] = field(default_factory=dict)  # booking_id -> latest prepare_rebooking result
    notices: dict[str, list[str]] = field(default_factory=dict)  # booking_id -> app notices for the next chat turn
    shown_changes: dict[str, set[str]] = field(default_factory=dict)  # booking_id -> change ids already shown
    last_used: float = field(default_factory=time.monotonic)
    lock: threading.Lock = field(default_factory=threading.Lock)  # one request at a time per session

    @property
    def booking_ids(self) -> list[str]:
        return self.service.booking_ids()

    def owns(self, booking_id: str) -> bool:
        return booking_id in self.service.booking_ids()


class SessionStore:
    def __init__(self, idle_seconds: float = SESSION_IDLE_SECONDS, max_sessions: int = MAX_SESSIONS) -> None:
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
        service = MockService(scenarios=list(dict.fromkeys(names)))
        toolset = build_tools(service, allowed_booking_ids=set(service.booking_ids()))
        gate = ConfirmationGate(toolset.tools, toolset.complete_rebooking, source="real")
        prepared: dict[str, dict[str, Any]] = {}
        gate_tools = gate.tools()

        def prepare_rebooking(booking_id: str, option_id: str) -> dict[str, Any]:
            result = gate_tools["prepare_rebooking"](booking_id=booking_id, option_id=option_id)
            prepared[booking_id] = result  # what the confirm card shows comes from this, not from the model
            return result

        tools = {**gate_tools, "prepare_rebooking": prepare_rebooking}
        session = Session(secrets.token_urlsafe(32), service, toolset, gate, tools, prepared=prepared)
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
