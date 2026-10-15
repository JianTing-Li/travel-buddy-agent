"""FastAPI application entry point. Owner: Jian.

Run locally (no access log, since it would print paths and client addresses):
    uvicorn backend.app.api.main:app --reload --no-access-log

Every call except POST /sessions and GET /health needs the X-Session-Id header from POST /sessions.
A session can only reach its own bookings; any other booking id gets the same 404 as an unknown one.
Everything served today is simulated mock data.
"""
from functools import lru_cache
from typing import Annotated, Any

import anthropic
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .. import config
from ..agent.loop import load_system_prompt, run_turn
from .request_log import RedactedRequestLog, configure_logging
from .schemas import (
    BookingDetail,
    BookingSummary,
    ChatIn,
    ChatOut,
    ConfirmCard,
    ConfirmIn,
    ConfirmOut,
    ErrorOut,
    SessionCreate,
    SessionOut,
)
from .sessions import Session, SessionStore, UnknownScenarioError

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")  # Vite dev server
SESSION_HEADER = "X-Session-Id"
BOOKING_NOT_FOUND = "Booking not found."
NOT_CONFIGURED = "The assistant isn't configured on the server."
MAX_NOTICES = 5


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return load_system_prompt()


def _chat_system_prompt(booking_id: str) -> str:
    """The agent's prompt plus app-controlled context; the booking id never comes from the traveler's text."""
    return (f"{_system_prompt()}\n\nApp context (written by the application, not the traveler): the traveler has "
            f"opened booking {booking_id}. Use this booking_id when you call tools. All data is simulated.")


def _notice(outcome: dict[str, Any], option_id: str) -> str:
    """A line for the next chat turn so the agent only reports what the application actually did."""
    if outcome["status"] == "confirmed":
        confirmation_id = outcome["result"].get("confirmation_id")
        return (f"[App notice] The traveler explicitly confirmed option {option_id}. The application completed the "
                f"SIMULATED rebooking (confirmation {confirmation_id}). Tell the traveler it is simulated.")
    if outcome["status"] == "pending":
        return (f"[App notice] The result of confirming option {option_id} is uncertain. Confirmation is pending. "
                "Do not encourage another attempt.")
    return (f"[App notice] The application rejected the confirmation of option {option_id}: "
            f"{outcome.get('reason', 'not allowed')} Nothing was booked.")


def _summary(session: Session, booking_id: str) -> BookingSummary:
    trip = session.service.get_trip_context(booking_id)
    itinerary = trip.original_itinerary
    rebooked = session.service.get_confirmation(booking_id) is not None
    return BookingSummary(
        booking_id=booking_id,
        origin=itinerary["origin"],
        destination=itinerary["destination"],
        departs=itinerary["departs"],
        passenger_count=len(trip.passengers),
        status="rebooked" if rebooked else itinerary["status"],
        disruption_type=trip.disruption_details["type"],
        data_source=trip.data_source,
        rebooked=rebooked,
    )


def create_app(
    store: SessionStore | None = None,
    allowed_origins: tuple[str, ...] = DEV_ORIGINS,
    model_client: Any = None,
    model: str | None = None,
) -> FastAPI:
    """model_client and model are injectable for tests; by default they come from config (server-side only)."""
    app = FastAPI(title="Travel Buddy API", description="Simulated rebooking. No real tickets are created.")
    app.state.sessions = store or SessionStore()
    app.state.model_client = model_client
    app.state.model = model
    app.add_middleware(RedactedRequestLog)
    app.add_middleware(  # added last so it wraps everything, including error responses
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", SESSION_HEADER],
        expose_headers=["X-Request-Id"],
    )
    configure_logging()

    def current_session(x_session_id: Annotated[str | None, Header()] = None) -> Session:
        session = app.state.sessions.get(x_session_id)
        if session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session not found or expired. Start a new session.")
        return session

    SessionDep = Annotated[Session, Depends(current_session)]

    def owned_booking(booking_id: str, session: SessionDep) -> str:
        if not session.owns(booking_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, BOOKING_NOT_FOUND)
        return booking_id

    BookingDep = Annotated[str, Depends(owned_booking)]
    errors = {401: {"model": ErrorOut}, 404: {"model": ErrorOut}}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionOut,
              responses={422: {"model": ErrorOut}})
    def create_session(body: SessionCreate | None = None) -> SessionOut:
        try:
            session = app.state.sessions.create(body.scenarios if body else None)
        except UnknownScenarioError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        return SessionOut(session_id=session.session_id, booking_ids=session.booking_ids)

    @app.get("/bookings", response_model=list[BookingSummary], responses=errors)
    def list_bookings(session: SessionDep) -> list[BookingSummary]:
        with session.lock:
            return [_summary(session, booking_id) for booking_id in session.booking_ids]

    @app.get("/bookings/{booking_id}", response_model=BookingDetail, responses=errors)
    def get_booking(booking_id: BookingDep, session: SessionDep) -> BookingDetail:
        with session.lock:
            return BookingDetail(
                summary=_summary(session, booking_id),
                trip=session.service.get_trip_context(booking_id),
                confirmation=session.service.get_confirmation(booking_id),
            )

    def model_client_and_name() -> tuple[Any, str]:
        name = app.state.model or config.MODEL
        if app.state.model_client is None:
            if not config.ANTHROPIC_API_KEY or not name:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_CONFIGURED)
            app.state.model_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        if not name:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_CONFIGURED)
        return app.state.model_client, name

    def confirm_card(session: Session, booking_id: str) -> ConfirmCard | None:
        prepared = session.prepared.get(booking_id)
        if not prepared or prepared.get("validation_result") != "valid":
            return None
        if session.service.get_confirmation(booking_id) is not None:
            return None
        return ConfirmCard(
            booking_id=booking_id,
            option=prepared["latest_option_details"],
            validation_result=prepared["validation_result"],
            changes_to_review=prepared["changes_to_review"],
        )

    unavailable = {**errors, 503: {"model": ErrorOut}}

    @app.post("/chat", response_model=ChatOut, responses=unavailable)
    def chat(body: ChatIn, session: SessionDep) -> ChatOut:
        if not session.owns(body.booking_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, BOOKING_NOT_FOUND)
        client, model_name = model_client_and_name()
        booking_id = body.booking_id
        with session.lock:
            notices = session.notices.pop(booking_id, [])
            user_message = "\n".join([*notices, "", body.message]) if notices else body.message
            result = run_turn(
                client, model_name, _chat_system_prompt(booking_id), session.histories.get(booking_id, []),
                user_message, session.tools, session.toolset.schemas,
            )
            if result.stopped_reason == "error":
                session.notices[booking_id] = notices  # the model never saw them; keep them for the next try
            else:
                session.histories[booking_id] = result.history
            return ChatOut(reply=result.reply, stopped_reason=result.stopped_reason,
                           confirm_card=confirm_card(session, booking_id))

    @app.post("/confirm", response_model=ConfirmOut, responses={**errors, 409: {"model": ConfirmOut},
                                                              202: {"model": ConfirmOut}})
    def confirm(body: ConfirmIn, session: SessionDep, response: Response) -> ConfirmOut:
        """The traveler's explicit confirmation. Only the app's button calls this; the model has no such tool."""
        if not session.owns(body.booking_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, BOOKING_NOT_FOUND)
        with session.lock:
            outcome = session.gate.confirm(body.booking_id, body.option_id)
            repeat = bool(outcome.get("repeat"))
            if not repeat:
                notices = session.notices.setdefault(body.booking_id, [])
                notices.append(_notice(outcome, body.option_id))
                del notices[:-MAX_NOTICES]
            if outcome["status"] == "confirmed":
                session.prepared.pop(body.booking_id, None)
            elif outcome["status"] == "rejected":
                response.status_code = status.HTTP_409_CONFLICT
            else:
                response.status_code = status.HTTP_202_ACCEPTED
            return ConfirmOut(status=outcome["status"], reason=outcome.get("reason"),
                              confirmation=outcome.get("result"), repeat=repeat)

    return app


app = create_app()
