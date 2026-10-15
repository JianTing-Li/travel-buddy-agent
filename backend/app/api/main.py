"""FastAPI application entry point. Owner: Jian.

Run locally (no access log, since it would print paths and client addresses):
    uvicorn backend.app.api.main:app --reload --no-access-log

Every call except POST /sessions and GET /health needs the X-Session-Id header from POST /sessions.
A session can only reach its own bookings; any other booking id gets the same 404 as an unknown one.
Everything served today is simulated mock data.
"""
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from .request_log import RedactedRequestLog, configure_logging
from .schemas import BookingDetail, BookingSummary, ErrorOut, SessionCreate, SessionOut
from .sessions import Session, SessionStore, UnknownScenarioError

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")  # Vite dev server
SESSION_HEADER = "X-Session-Id"
BOOKING_NOT_FOUND = "Booking not found."


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


def create_app(store: SessionStore | None = None, allowed_origins: tuple[str, ...] = DEV_ORIGINS) -> FastAPI:
    app = FastAPI(title="Travel Buddy API", description="Simulated rebooking. No real tickets are created.")
    app.state.sessions = store or SessionStore()
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

    return app


app = create_app()
