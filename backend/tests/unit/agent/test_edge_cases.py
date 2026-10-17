"""Edge cases found by the coverage check: failures in decide, the prompt loader, tool sources and stub tools. Owner: Cheich."""
import anthropic
import httpx
import pytest
from types import SimpleNamespace as NS

from backend.app.agent import tool_source as ts
from backend.app.agent.decide import decide
from backend.app.agent.loop import PROMPT_PATH, load_system_prompt
from backend.app.agent.stub_tools import SCENARIOS, build_stub_completer, build_stub_tools
from backend.tests.unit.agent.test_loop import FakeClient, resp, text, tool


def test_a_real_api_error_becomes_an_error_decision_not_a_crash():
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    d = decide(FakeClient(error), "m", "s", [], [])
    assert d.kind == "error" and "APIConnectionError" in d.error


def test_an_unknown_reply_block_type_is_ignored():
    d = decide(FakeClient(resp(NS(type="thinking", thinking="..."), text("Hello."))), "m", "s", [], [])
    assert d.kind == "text" and d.text == "Hello." and len(d.assistant_content) == 1


def test_a_tool_call_next_to_unknown_blocks_still_works():
    d = decide(FakeClient(resp(NS(type="thinking"), tool("get_trip_context", {"booking_id": "b"}))), "m", "s", [], [])
    assert d.kind == "tool_calls" and d.tool_calls[0].name == "get_trip_context"


def test_a_missing_prompt_file_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="System prompt not found"):
        load_system_prompt(tmp_path / "nope.txt")


def test_the_real_prompt_loads_and_keeps_the_rules_that_code_relies_on():
    prompt = load_system_prompt(PROMPT_PATH)
    for must_have in ("Never invent flights", "untrusted data", "explicit", "escalate_to_support"):
        assert must_have in prompt


def test_check_tool_source_names_every_kind_of_problem():
    good = {n: (lambda **k: {}) for n in ts.REQUIRED_TOOLS}
    schemas = [{"name": n, "description": "d", "input_schema": {"type": "object"}} for n in ts.REQUIRED_TOOLS]
    assert ts.check_tool_source(good, schemas) == []
    assert ts.check_tool_source("not a dict", schemas)
    assert ts.check_tool_source(good, "not a list")
    assert any("bad schema entry" in p for p in ts.check_tool_source(good, [*schemas, "junk"]))
    assert any("not callable" in p for p in ts.check_tool_source({**good, "get_trip_context": 5}, schemas))
    assert any("missing required tools" in p for p in ts.check_tool_source({"only_one": lambda: {}}, [schemas[0] | {"name": "only_one"}]))


def test_a_registry_that_cannot_be_imported_gives_a_clear_error(monkeypatch):
    def boom(name):
        raise ImportError("no registry")
    monkeypatch.setattr(ts.importlib, "import_module", boom)
    with pytest.raises(ts.ToolSourceError, match="Could not import"):
        ts.get_tool_source("real")


def test_a_registry_missing_what_the_loop_needs_gives_a_clear_error(monkeypatch):
    monkeypatch.setattr(ts.importlib, "import_module", lambda name: NS(TOOLS={}))
    with pytest.raises(ts.ToolSourceError, match="must define TOOLS, TOOL_SCHEMAS and complete_rebooking"):
        ts.get_tool_source("real")


def test_a_real_source_that_does_not_fit_the_loop_is_rejected(monkeypatch):
    registry = NS(TOOLS={"get_trip_context": lambda **k: {}}, TOOL_SCHEMAS=[], complete_rebooking=lambda b, o: {})
    monkeypatch.setattr(ts.importlib, "import_module", lambda name: registry)
    with pytest.raises(ts.ToolSourceError, match="do not fit the loop"):
        ts.get_tool_source("real")


def test_stub_tools_reject_unknown_bookings_and_options():
    name = next(iter(SCENARIOS))
    tools = build_stub_tools(name)
    booking = SCENARIOS[name]["booking_id"]
    with pytest.raises(ValueError, match="not found"):
        tools["get_trip_context"](booking_id="NOPE")
    with pytest.raises(ValueError, match="Option"):
        tools["prepare_rebooking"](booking_id=booking, option_id="nope")
    with pytest.raises(ValueError):
        build_stub_completer(name)("NOPE", "nope")


def test_prompt_v1_is_the_prd_prompt_plus_exactly_one_added_paragraph():
    from backend.app.agent.loop import PROMPT_PATH
    v0 = (PROMPT_PATH.parent / "system_prompt_v0.txt").read_text(encoding="utf-8")
    v1 = (PROMPT_PATH.parent / "system_prompt_v1.txt").read_text(encoding="utf-8")
    added = [line for line in v1.splitlines() if line not in v0.splitlines()]
    assert len(added) == 1
    assert v1.replace(added[0] + "\n", "", 1) == v0  # nothing else differs from the PRD text
    for rule in ('"by 3"', "ask first and do not guess", "Do not ask about what the booking already settles",
                 "is not their budget", "ask before raising it"):
        assert rule in added[0]


def test_prompt_v2_is_v1_plus_only_a_section_on_working_with_the_app():
    from backend.app.agent.loop import PROMPT_PATH
    v1 = (PROMPT_PATH.parent / "system_prompt_v1.txt").read_text(encoding="utf-8")
    v2 = PROMPT_PATH.read_text(encoding="utf-8")
    assert PROMPT_PATH.name == "system_prompt_v2.txt"
    assert v2.startswith(v1 + "\nWorking with the app\n")  # the PRD text and v1 are unchanged
    added = v2[len(v1):]
    for rule in ("Confirm rebooking button", 'Never ask them to reply "yes"', "never say you passed a confirmation on",
                 "Never show UTC offsets, internal ids", "Do not ask the traveler to repeat or confirm limits",
                 "let them choose one before you prepare it"):
        assert rule in added
