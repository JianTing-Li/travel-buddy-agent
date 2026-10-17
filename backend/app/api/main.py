"""FastAPI application entry point. Owner: Jian.

Run locally (no access log, since it would print paths and client addresses):
    uvicorn backend.app.api.main:app --reload --no-access-log
    uvicorn backend.app.api.main:dev_app --reload --no-access-log   # adds the /dev test endpoints

Every call except POST /sessions and GET /health needs the X-Session-Id header from POST /sessions.
A session can only reach its own bookings; any other booking id gets the same 404 as an unknown one.
Everything served today is simulated mock data.
"""
from datetime import datetime
from functools import lru_cache
from typing import Annotated, Any

import secrets

import anthropic
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .. import config
from ..services.airline_change import AirlineChange
from ..services.duffel.client import DuffelClient, DuffelConfigError
from ..services.duffel.service import DuffelServiceError
from ..services.duffel.test_orders import create_test_booking
from ..services.errors import ServiceError
from ..services.mock.generator import MAX_SEED, GeneratorError, generate_scenario
from ..services.mock.mock_service import MockServiceError
from ..services.validation import local_time_text
from ..agent.loop import load_system_prompt, run_turn
from .rate_limit import Limits, RateLimiter
from .request_log import RedactedRequestLog, configure_logging
from .schemas import (
    BookingDetail,
    BookingSummary,
    ChangeCheckOut,
    ChatEntry,
    ChatHistoryOut,
    ChatIn,
    ChatOut,
    ConfirmCard,
    ConfirmIn,
    ConfirmOut,
    DevBookingCreate,
    DevBookingOut,
    DevDisruptIn,
    DevDuffelBookingIn,
    DevFaultsIn,
    DevFaultsOut,
    DevResetOut,
    ErrorOut,
    SearchResults,
    SessionCreate,
    SessionOut,
)
from .sessions import (
    RECOMMEND_SCHEMA,
    DuffelNotConfiguredError,
    Session,
    SessionStore,
    TooManyBookingsError,
    UnknownScenarioError,
)

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")  # Vite dev server
SESSION_HEADER = "X-Session-Id"
ACCESS_CODE_HEADER = "X-Access-Code"
_FROM_CONFIG: Any = object()  # "read it from config", so tests can pass None to switch a setting off
BOOKING_NOT_FOUND = "Booking not found."
NOT_CONFIGURED = "The assistant isn't configured on the server."
MAX_NOTICES = 5
MODEL_TIMEOUT_SECONDS = 45.0


@lru_cache(maxsize=1)
def _system_prompt() -> str:
    return load_system_prompt()


def _chat_system_prompt(booking_id: str, confirmation: dict[str, Any] | None = None,
                        travel_day: str | None = None) -> str:
    """The agent's prompt plus app-controlled context; the booking id never comes from the traveler's text."""
    context = (f"{_system_prompt()}\n\nApp context (written by the application, not the traveler): the traveler has "
               f"opened booking {booking_id}. Use this booking_id when you call tools. All data is simulated.")
    if travel_day:
        # e.g. a missed flight that left yesterday: the replacements, and so the traveler's times, are on another day
        context += (f" The replacement flights are on {travel_day}, not on the day of the original flight: read a time"
                    f" the traveler gives as local time on {travel_day} unless they say another day.")
    if confirmation:
        # every turn, not only the one after confirming, so the agent never treats a rebooked trip as open
        confirmation_id = confirmation.get("confirmation_id")
        context += (f" This booking is already rebooked (simulated, confirmation {confirmation_id})."
                    " It cannot be rebooked again here. Answer questions about the new flight. Only if the traveler asks"
                    " for a different flight, explain that and offer the support handoff. Do not search for or"
                    " prepare another replacement.")
    return context


def _change_notice(change: AirlineChange) -> str:
    """Tells the agent about a detected change on its next turn; the text is written by the app, not the airline."""
    return (f"[App notice] The airline changed this booking (simulated): {change.summary} Explain what happened "
            "using get_trip_context, then ask what the traveler needs. Do not assume what a replacement costs.")


def _notice(outcome: dict[str, Any], option_id: str) -> str:
    """A line for the next chat turn so the agent only reports what the application actually did."""
    if outcome["status"] == "confirmed":
        confirmation_id = outcome["result"].get("confirmation_id")
        return (f"[App notice] The traveler explicitly confirmed option {option_id}. The application completed the "
                f"SIMULATED rebooking (confirmation {confirmation_id}) and showed the traveler a receipt with the new "
                "flight. The app labels it as simulated, so you don't need to.")
    if outcome["status"] == "pending":
        return (f"[App notice] The result of confirming option {option_id} is uncertain. Confirmation is pending. "
                "Do not encourage another attempt.")
    return (f"[App notice] The application rejected the confirmation of option {option_id}: "
            f"{outcome.get('reason', 'not allowed')} Nothing was booked.")


def _summary(session: Session, booking_id: str) -> BookingSummary:
    service = session.service_for(booking_id)
    trip = service.get_trip_context(booking_id)
    itinerary = trip.original_itinerary
    rebooked = service.get_confirmation(booking_id) is not None
    return BookingSummary(
        booking_id=booking_id,
        origin=itinerary.origin,
        destination=itinerary.destination,
        departs=itinerary.departs,
        passenger_count=len(trip.passengers),
        status="rebooked" if rebooked else itinerary.status,
        disruption_type=trip.disruption_details.type,
        data_source=trip.data_source,
        rebooked=rebooked,
        airline=" ".join(part for part in (itinerary.airline, itinerary.flight) if part) or None,
        booking_reference=itinerary.booking_reference,
    )


def create_app(
    store: SessionStore | None = None,
    allowed_origins: tuple[str, ...] | None = None,
    model_client: Any = None,
    model: str | None = None,
    dev: bool = False,
    duffel_client: DuffelClient | None = None,
    access_code: str | None = _FROM_CONFIG,
    limits: Limits | None = Limits(),
) -> FastAPI:
    """model_client and model are injectable for tests; by default they come from config (server-side only).

    dev=True also serves /dev endpoints that create simulated bookings, disruptions and faults for testing. They are
    mock-only, are not part of the traveler's app, and do not exist unless the app is created this way.

    For a deployment: allowed_origins (default ALLOWED_ORIGINS, else the Vite dev server), access_code (default
    DEMO_ACCESS_CODE; None means open) and limits (None switches the rate limits off).
    """
    origins = allowed_origins or config.ALLOWED_ORIGINS or DEV_ORIGINS
    code = config.DEMO_ACCESS_CODE if access_code is _FROM_CONFIG else access_code
    limiter = RateLimiter()
    app = FastAPI(title="Travel Buddy API", description="Simulated rebooking. No real tickets are created.")
    app.state.duffel_client = duffel_client

    def get_duffel_client() -> DuffelClient | None:
        """The shared Duffel TEST client, or None when no test token is configured (the server never uses a live one)."""
        if app.state.duffel_client is None and config.DUFFEL_ACCESS_TOKEN:
            try:
                app.state.duffel_client = DuffelClient(config.DUFFEL_ACCESS_TOKEN)
            except DuffelConfigError:
                return None
        return app.state.duffel_client

    app.state.sessions = store or SessionStore(duffel_client_factory=get_duffel_client)
    app.state.model_client = model_client
    app.state.model = model
    app.add_middleware(RedactedRequestLog)
    app.add_middleware(  # added last so it wraps everything, including error responses
        CORSMiddleware,
        allow_origins=list(origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", SESSION_HEADER, ACCESS_CODE_HEADER],
        expose_headers=["X-Request-Id"],
    )
    configure_logging()

    @app.exception_handler(DuffelServiceError)
    def duffel_unavailable(_: Request, exc: DuffelServiceError) -> JSONResponse:
        # The message holds only a Duffel error code or a fixed sentence, never raw responses or traveler data.
        return JSONResponse({"detail": str(exc)}, status_code=status.HTTP_502_BAD_GATEWAY)

    def current_session(x_session_id: Annotated[str | None, Header()] = None) -> Session:
        session = app.state.sessions.get(x_session_id)
        if session is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session not found or expired. Start a new session.")
        session.refresh_stale()  # untouched mock bookings never show flights that already left
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
    def create_session(request: Request, body: SessionCreate | None = None,
                       x_access_code: Annotated[str | None, Header()] = None) -> SessionOut:
        if code and not secrets.compare_digest((x_access_code or "").encode(), code.encode()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Enter the access code to use this demo.")
        if limits and not limiter.allow("sessions", _client_ip(request), limits.sessions_per_ip_per_hour, 3600):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many new sessions from your network. Try again in an hour.")
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
                trip=session.service_for(booking_id).get_trip_context(booking_id),
                confirmation=session.service_for(booking_id).get_confirmation(booking_id),
            )

    def model_client_and_name() -> tuple[Any, str]:
        name = app.state.model or config.MODEL
        if app.state.model_client is None:
            if not config.ANTHROPIC_API_KEY or not name:
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_CONFIGURED)
            # A stuck call must not leave the traveler waiting: one model call gets MODEL_TIMEOUT_SECONDS and one retry.
            app.state.model_client = anthropic.Anthropic(
                api_key=config.ANTHROPIC_API_KEY, timeout=MODEL_TIMEOUT_SECONDS, max_retries=1)
        if not name:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_CONFIGURED)
        return app.state.model_client, name

    def confirm_card(session: Session, booking_id: str) -> ConfirmCard | None:
        prepared = session.prepared.get(booking_id)
        if not prepared or prepared.get("validation_result") != "valid":
            return None
        if session.service_for(booking_id).get_confirmation(booking_id) is not None:
            return None
        return ConfirmCard(
            booking_id=booking_id,
            option=prepared["latest_option_details"],
            validation_result=prepared["validation_result"],
            changes_to_review=prepared["changes_to_review"],
        )

    @app.post("/bookings/{booking_id}/changes/check", response_model=ChangeCheckOut, responses=errors)
    def check_changes(booking_id: BookingDep, session: SessionDep) -> ChangeCheckOut:
        """Application code, not the agent, looks for airline changes while the app is open. The page polls this.

        Each change is returned once; its id is remembered so it is never shown twice, and the agent is told
        about it on the traveler's next chat turn.
        """
        with session.lock:
            shown = session.shown_changes.setdefault(booking_id, set())
            new = [c for c in session.service_for(booking_id).list_airline_changes(booking_id) if c.change_id not in shown]
            notices = session.notices.setdefault(booking_id, [])
            for change in new:
                shown.add(change.change_id)
                notices.append(_change_notice(change))
            del notices[:-MAX_NOTICES]
            return ChangeCheckOut(new_changes=new, booking=_summary(session, booking_id))

    unavailable = {**errors, 503: {"model": ErrorOut}}

    @app.post("/chat", response_model=ChatOut, responses=unavailable)
    def chat(body: ChatIn, session: SessionDep, request: Request) -> ChatOut:
        if not session.owns(body.booking_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, BOOKING_NOT_FOUND)
        if limits:
            if session.turns >= limits.chat_turns_per_session:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    "This demo session has reached its message limit.")
            if not limiter.allow("chat", _client_ip(request), limits.chat_per_ip_per_minute, 60):
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    "Too many messages. Wait a minute, then try again.")
        client, model_name = model_client_and_name()
        booking_id = body.booking_id
        with session.lock:
            last = session.answered.get(booking_id)
            if body.message_id and last and last[0] == body.message_id:
                return last[1]  # a retry of a message already answered: the same answer, no second turn
            session.searched.pop(booking_id, None)  # cards come only from a search in THIS turn
            notices = session.notices.pop(booking_id, [])
            user_message = "\n".join([*notices, "", body.message]) if notices else body.message
            result = run_turn(
                client, model_name,
                _chat_system_prompt(booking_id, session.service_for(booking_id).get_confirmation(booking_id),
                                    _other_travel_day(session, booking_id)),
                session.histories.get(booking_id, []),
                user_message, session.tools, [*session.toolset.schemas, RECOMMEND_SCHEMA],
                display_tools=frozenset({RECOMMEND_SCHEMA["name"]}),
            )
            if result.stopped_reason == "error":
                session.notices[booking_id] = notices  # the model never saw them; keep them for the next try
            else:
                session.histories[booking_id] = result.history
            searched = session.searched.get(booking_id) if result.stopped_reason != "error" else None
            out = ChatOut(reply=result.reply, stopped_reason=result.stopped_reason,
                          confirm_card=confirm_card(session, booking_id), search=_search_results(searched))
            if result.stopped_reason != "error":
                session.turns += 1
                session.transcripts.setdefault(booking_id, []).extend([
                    {"role": "traveler", "text": body.message},
                    {"role": "assistant", "text": out.reply, "search": out.search},
                ])
                if body.message_id:
                    session.answered[booking_id] = (body.message_id, out)
            return out

    @app.get("/bookings/{booking_id}/chat", response_model=ChatHistoryOut, responses=errors)
    def chat_history(booking_id: BookingDep, session: SessionDep) -> ChatHistoryOut:
        """The conversation as the traveler saw it, so a reloaded page can show it again."""
        with session.lock:
            return ChatHistoryOut(messages=[ChatEntry(**m) for m in session.transcripts.get(booking_id, [])],
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
            receipt = None
            if outcome["status"] == "confirmed":
                session.prepared.pop(body.booking_id, None)
                if not repeat:
                    receipt = _receipt(outcome["result"])
                    session.transcripts.setdefault(body.booking_id, []).append({"role": "app", "text": receipt})
            elif outcome["status"] == "rejected":
                response.status_code = status.HTTP_409_CONFLICT
            else:
                response.status_code = status.HTTP_202_ACCEPTED
            return ConfirmOut(status=outcome["status"], reason=outcome.get("reason"),
                              confirmation=outcome.get("result"), repeat=repeat, receipt=receipt)

    if dev:
        add_dev_routes(app, SessionDep, BookingDep, get_duffel_client, limiter, limits)
    return app


def _other_travel_day(session: Session, booking_id: str) -> str | None:
    """The replacement flights' day, when it differs from the original flight's day (mock bookings only)."""
    service = session.service_for(booking_id)
    if service is not session.service:
        return None
    day = service.travel_day(booking_id)
    original = service.get_trip_context(booking_id).original_itinerary.departs[:10]
    return day if day and day != original else None


def _client_ip(request: Request) -> str:
    """The caller's address. Behind a proxy (Render) start uvicorn with --proxy-headers so this is the real one."""
    return request.client.host if request.client else "unknown"


def _receipt(confirmation: dict[str, Any]) -> str:
    """The app's note in the chat once a rebooking is confirmed, in the words travelers read."""
    flight = confirmation.get("updated_itinerary") or {}
    try:
        leaves = local_time_text(datetime.fromisoformat(flight["departs"]))
        lands = local_time_text(datetime.fromisoformat(flight["arrives"]))
        trip = (f" {flight.get('flight') or 'your new flight'}: it leaves {flight['origin']} at {leaves} and "
                f"lands at {flight['destination']} at {lands}.")
    except (KeyError, TypeError, ValueError):
        trip = " your new flight."
    return f"You're all set! You're rebooked on{trip} Confirmation {confirmation.get('confirmation_id')}."


def _search_results(searched: dict[str, Any] | None) -> SearchResults | None:
    """Option cards are a bonus on top of the reply: data that doesn't fit the schema is left out, never an error."""
    if not searched:
        return None
    try:
        return SearchResults.model_validate(searched)
    except ValueError:
        return None


def add_dev_routes(app: FastAPI, SessionDep: Any, BookingDep: Any, get_duffel_client: Any,
                   limiter: RateLimiter | None = None, limits: Limits | None = None) -> None:
    """The test tools. On a public demo anyone can use them (only on their own session), so they are rate limited."""

    def limited(kind: str, per_hour: int) -> Any:
        def check(request: Request) -> None:
            if limiter and limits and not limiter.allow(kind, _client_ip(request), per_hour, 3600):
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    "You've used the dev tools a lot. Try again in an hour.")
        return Depends(check)

    dev_limit = [limited("dev", limits.dev_actions_per_ip_per_hour)] if limits else []
    duffel_limit = [limited("duffel", limits.duffel_bookings_per_ip_per_hour)] if limits else []

    errors = {401: {"model": ErrorOut}, 404: {"model": ErrorOut}, 409: {"model": ErrorOut}, 422: {"model": ErrorOut}}

    @app.post("/dev/bookings", status_code=status.HTTP_201_CREATED, response_model=DevBookingOut, responses=errors,
              dependencies=dev_limit)
    def dev_create_booking(session: SessionDep, body: DevBookingCreate | None = None) -> DevBookingOut:
        """Add a simulated booking to this session: an eval case, or a random one. The seed reproduces it."""
        body = body or DevBookingCreate()
        seed = body.seed if body.seed is not None else secrets.randbelow(MAX_SEED + 1)
        try:
            def build() -> Any:
                return generate_scenario(seed, scenario=body.scenario, situation=body.situation)
            scenario = build()
            with session.lock:
                booking_id = session.add_booking(scenario, source=build)
                summary = _summary(session, booking_id)
        except GeneratorError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        except (MockServiceError, TooManyBookingsError) as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        return DevBookingOut(booking=summary, seed=seed, scenario=body.scenario)

    @app.post("/dev/bookings/{booking_id}/disrupt", status_code=status.HTTP_201_CREATED,
              response_model=AirlineChange, responses=errors, dependencies=dev_limit)
    def dev_disrupt(booking_id: BookingDep, body: DevDisruptIn, session: SessionDep) -> AirlineChange:
        """Simulate an airline change. The open page finds it through the normal change check."""
        try:
            with session.lock:
                service = session.service_for(booking_id)
                if service is session.duffel:
                    if body.kind != "delay":
                        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Duffel only simulates delays.")
                    return service.simulate_airline_change(booking_id)
                return service.add_airline_change(booking_id, body.kind, body.delay_minutes)
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
        except ServiceError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

    @app.post("/dev/bookings/{booking_id}/faults", response_model=DevFaultsOut, responses=errors,
              dependencies=dev_limit)
    def dev_set_faults(booking_id: BookingDep, body: DevFaultsIn, session: SessionDep) -> DevFaultsOut:
        """Make the mock misbehave on purpose for this booking; an empty list clears it."""
        if session.service_for(booking_id) is session.duffel:
            raise HTTPException(status.HTTP_409_CONFLICT, "Faults apply to mock bookings only.")
        try:
            with session.lock:
                return DevFaultsOut(faults=session.service.set_faults(booking_id, body.faults))
        except MockServiceError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    @app.post("/dev/bookings/{booking_id}/clear", response_model=BookingSummary, responses=errors,
              dependencies=dev_limit)
    def dev_clear_disruption(booking_id: BookingDep, session: SessionDep) -> BookingSummary:
        """Put a mock booking back to normal (on time) and start its chat over. Duffel can't undo its changes."""
        if session.service_for(booking_id) is session.duffel:
            raise HTTPException(status.HTTP_409_CONFLICT, "Only mock bookings can be put back to normal.")
        with session.lock:
            session.clear_disruption(booking_id)
            return _summary(session, booking_id)

    @app.post("/dev/reset", response_model=DevResetOut, responses=errors, dependencies=dev_limit)
    def dev_reset(session: SessionDep) -> DevResetOut:
        """Start THIS session over with its first mock bookings. Other sessions are untouched; to reset
        everything, restart the backend (all state is in memory)."""
        with session.lock:
            session.reset()
            return DevResetOut(booking_ids=session.booking_ids)

    @app.post("/dev/duffel-bookings", status_code=status.HTTP_201_CREATED, response_model=BookingSummary,
              responses={**errors, 502: {"model": ErrorOut}, 503: {"model": ErrorOut}},
              dependencies=[*dev_limit, *duffel_limit])
    def dev_create_duffel_booking(session: SessionDep, body: DevDuffelBookingIn | None = None) -> BookingSummary:
        """Create a real Duffel TEST order (test token, test balance) and add it to this session."""
        body = body or DevDuffelBookingIn()
        client = get_duffel_client()
        if client is None or session.duffel is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Duffel isn't configured on the server.")
        try:
            with session.lock:
                order_id = create_test_booking(client, body.route, body.passengers)
                session.add_duffel_booking(order_id)
                return _summary(session, order_id)
        except TooManyBookingsError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        except DuffelNotConfiguredError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
        except DuffelServiceError:
            raise  # the app-wide handler answers 502 with the safe message
        except ServiceError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None

app = create_app()
dev_app = create_app(dev=True)
