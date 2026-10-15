"""Request logging with redaction. Owner: Jian.

Logs only a request id, the method, the route template (e.g. /bookings/{booking_id}), the status and the
duration. Never logs bodies, headers (session ids, keys), query strings, client addresses or exception
messages, which may contain traveler data. Unexpected errors return a generic 500 and log only the type.
"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("travel_buddy.api")


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", "unmatched")


class RedactedRequestLog(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid.uuid4().hex[:12]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:  # never let a traceback with traveler data reach the client or the log
            logger.error("request_id=%s method=%s route=%s error=%s", request_id, request.method,
                         _route_template(request), type(exc).__name__)
            response = JSONResponse({"detail": "Something went wrong. Please try again."}, status_code=500)
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info("request_id=%s method=%s route=%s status=%s duration_ms=%.0f", request_id, request.method,
                    _route_template(request), response.status_code, duration_ms)
        response.headers["X-Request-Id"] = request_id
        return response


def configure_logging() -> None:
    """Send this app's redacted lines to stderr and turn off uvicorn's access log.

    uvicorn configures only its own loggers, so without a handler these lines would be dropped. Its access
    log prints full paths and client IP addresses, so it is disabled; this app logs its own redacted line.
    """
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True
