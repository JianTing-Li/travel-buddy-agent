"""Deployment guards: the access code, the allowed origins and the rate limits. Owner: Jian."""
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.app.api.rate_limit import Limits, RateLimiter


def reply(text="ok"):
    return NS(content=[NS(type="text", text=text)], stop_reason="end_turn")


class Model:
    def __init__(self):
        self.messages = NS(create=lambda **kwargs: reply())


def test_with_an_access_code_a_session_needs_it():
    client = TestClient(create_app(access_code="sesame"))
    assert client.post("/sessions").status_code == 403
    assert client.post("/sessions", headers={"X-Access-Code": "wrong"}).status_code == 403
    assert client.post("/sessions", headers={"X-Access-Code": "sesame"}).status_code == 201


def test_without_an_access_code_the_app_is_open():
    assert TestClient(create_app(access_code=None)).post("/sessions").status_code == 201


def test_only_the_allowed_origin_may_call_the_api_from_a_browser():
    client = TestClient(create_app(allowed_origins=("https://travel-buddy.example",)))
    allowed = client.options("/sessions", headers={"Origin": "https://travel-buddy.example",
                                                   "Access-Control-Request-Method": "POST",
                                                   "Access-Control-Request-Headers": "x-access-code"})
    other = client.options("/sessions", headers={"Origin": "https://evil.example",
                                                 "Access-Control-Request-Method": "POST"})
    assert allowed.headers.get("access-control-allow-origin") == "https://travel-buddy.example"
    assert "access-control-allow-origin" not in other.headers


def test_new_sessions_are_limited_per_address():
    client = TestClient(create_app(access_code=None, limits=Limits(sessions_per_ip_per_hour=2)))
    assert [client.post("/sessions").status_code for _ in range(3)] == [201, 201, 429]


def test_a_session_has_a_message_limit_and_an_address_a_rate_limit():
    client = TestClient(create_app(access_code=None, model_client=Model(), model="m",
                                   limits=Limits(chat_turns_per_session=2, chat_per_ip_per_minute=100)))
    headers = {"X-Session-Id": client.post("/sessions").json()["session_id"]}
    body = {"booking_id": "MOCK-CASE-1", "message": "hi"}
    codes = [client.post("/chat", json=body, headers=headers).status_code for _ in range(3)]
    assert codes == [200, 200, 429]

    client = TestClient(create_app(access_code=None, model_client=Model(), model="m",
                                   limits=Limits(chat_per_ip_per_minute=1)))
    headers = {"X-Session-Id": client.post("/sessions").json()["session_id"]}
    assert [client.post("/chat", json=body, headers=headers).status_code for _ in range(2)] == [200, 429]


def test_the_limiter_forgets_hits_outside_its_window():
    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])
    assert limiter.allow("chat", "1.2.3.4", 1, 60) and not limiter.allow("chat", "1.2.3.4", 1, 60)
    now[0] = 61
    assert limiter.allow("chat", "1.2.3.4", 1, 60)
    assert limiter.allow("chat", "5.6.7.8", 1, 60)  # another address has its own count
