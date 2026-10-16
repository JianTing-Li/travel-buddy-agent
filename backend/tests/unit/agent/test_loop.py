"""Unit tests for decide.py and loop.py using a fake model client (no network). Owner: Cheich."""
from types import SimpleNamespace as NS

from backend.app.agent.loop import STEP_LIMIT_REPLY, run_turn
from backend.app.agent.stub_tools import STUB_TOOL_SCHEMAS, STUB_TOOLS


def text(t):
    return NS(type="text", text=t)


def tool(name, input, id="t1"):
    return NS(type="tool_use", id=id, name=name, input=input)


class FakeClient:
    """Returns scripted responses in order; an Exception item is raised."""

    def __init__(self, *items):
        self.items = list(items)
        self.messages = NS(create=self._create)
        self.calls = 0

    def _create(self, **kwargs):
        self.calls += 1
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def resp(*blocks, stop_reason="end_turn"):
    return NS(content=list(blocks), stop_reason=stop_reason)


def run(client, msg="hi", max_steps=8, history=None):
    return run_turn(client, "m", "sys", history or [], msg, STUB_TOOLS, STUB_TOOL_SCHEMAS, max_steps)


def test_text_reply_ends_turn():
    r = run(FakeClient(resp(text("When do you need to arrive?"))))
    assert r.stopped_reason == "reply" and r.reply == "When do you need to arrive?" and r.steps == 1


def test_tool_call_then_reply():
    c = FakeClient(resp(tool("get_trip_context", {"booking_id": "MOCK-CASE-1"})), resp(text("Here is what happened.")))
    r = run(c)
    assert r.stopped_reason == "reply" and r.steps == 2
    result = r.history[2]["content"][0]
    assert result["tool_use_id"] == "t1" and "is_error" not in result


def test_unknown_tool_is_fed_back_as_error():
    c = FakeClient(resp(tool("book_flight", {})), resp(text("Sorry.")))
    r = run(c)
    result = r.history[2]["content"][0]
    assert result["is_error"] and "Unknown tool" in result["content"] and r.stopped_reason == "reply"


def test_bad_arguments_fed_back_as_error():
    c = FakeClient(resp(tool("get_trip_context", {"wrong": 1})), resp(text("ok")))
    assert run(c).history[2]["content"][0]["is_error"]


def test_non_object_input_fed_back_as_error():
    c = FakeClient(resp(tool("get_trip_context", "oops")), resp(text("ok")))
    r = run(c)
    assert r.history[2]["content"][0]["is_error"]
    assert r.history[1]["content"][0]["input"] == {}


def test_tool_exception_fed_back_as_error():
    tools = {"get_trip_context": lambda booking_id: 1 / 0}
    c = FakeClient(resp(tool("get_trip_context", {"booking_id": "b"})), resp(text("ok")))
    r = run_turn(c, "m", "s", [], "hi", tools, STUB_TOOL_SCHEMAS)
    assert r.history[2]["content"][0]["is_error"]


def test_step_limit():
    c = FakeClient(*[resp(tool("get_trip_context", {"booking_id": "b"}, id=f"t{i}")) for i in range(3)])
    r = run(c, max_steps=3)
    assert r.stopped_reason == "step_limit" and r.reply == STEP_LIMIT_REPLY and c.calls == 3
    assert r.history[-1]["role"] == "assistant"


def test_api_error_leaves_history_unchanged():
    prior = [{"role": "user", "content": "a"}, {"role": "assistant", "content": [{"type": "text", "text": "b"}]}]
    r = run(FakeClient(RuntimeError("boom")), history=prior)
    assert r.stopped_reason == "error" and r.history == prior


def test_empty_and_malformed_responses_do_not_crash():
    assert run(FakeClient(resp())).stopped_reason == "error"
    assert run(FakeClient(NS(content=None, stop_reason="end_turn"))).stopped_reason == "error"
    assert run(FakeClient(resp(text("   ")))).stopped_reason == "error"
    assert run(FakeClient(resp(tool("get_trip_context", {}), stop_reason="max_tokens"))).stopped_reason == "error"
    assert run(FakeClient(resp(tool("get_trip_context", {}, id="")))).stopped_reason == "error"


def test_multiple_tool_calls_all_get_results():
    c = FakeClient(
        resp(tool("get_trip_context", {"booking_id": "b"}, id="a"), tool("book_flight", {}, id="b")),
        resp(text("done")),
    )
    ids = [x["tool_use_id"] for x in run(c).history[2]["content"]]
    assert ids == ["a", "b"]


def test_cut_off_reply_is_continued_and_joined():
    c = FakeClient(resp(text("Option 1 leaves at 11 AM and ar"), stop_reason="max_tokens"),
                   resp(text("rives at 2 PM.")))
    r = run(c)
    assert r.stopped_reason == "reply" and r.reply == "Option 1 leaves at 11 AM and arrives at 2 PM."
    assert r.steps == 2 and c.calls == 2
    assert r.history[-2]["role"] == "user" and "cut off" in r.history[-2]["content"]


def test_reply_cut_off_too_many_times_is_an_error_and_history_unchanged():
    c = FakeClient(*[resp(text(f"part{i} "), stop_reason="max_tokens") for i in range(3)])
    prior = [{"role": "user", "content": "a"}, {"role": "assistant", "content": [{"type": "text", "text": "b"}]}]
    r = run(c, history=prior)
    assert r.stopped_reason == "error" and r.history == prior and c.calls == 3


def test_normal_reply_is_not_marked_truncated_and_default_limit_is_4096():
    from backend.app.agent.decide import DEFAULT_MAX_TOKENS, decide
    d = decide(FakeClient(resp(text("hi"))), "m", "s", [], [])
    assert d.kind == "text" and d.truncated is False and DEFAULT_MAX_TOKENS == 4096
