"""Checks that a tool source fits the loop. Run against stubs now, and against Jian's registry later. Owner: Cheich."""
import pytest

from backend.app.agent.stub_tools import SCENARIOS
from backend.app.agent.tool_source import ToolSourceError, check_tool_source, get_tool_source


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_stub_source_fits_the_loop(scenario):
    src = get_tool_source("stub", scenario)
    assert check_tool_source(src.tools, src.schemas) == []


def test_unknown_source_and_scenario_give_clear_errors():
    with pytest.raises(ToolSourceError):
        get_tool_source("nope")
    with pytest.raises(ToolSourceError):
        get_tool_source("stub", "case_99")


def test_check_catches_mismatches():
    tools = {"get_trip_context": lambda **k: {}}
    schemas = [{"name": "other", "description": "d", "input_schema": {"type": "object"}}]
    assert check_tool_source(tools, schemas)


def test_real_source_fits_once_jian_provides_it():
    """Passes when Jian's registry is ready. Until then it is skipped, not failed."""
    try:
        src = get_tool_source("real")
    except ToolSourceError as exc:
        pytest.skip(f"real tools not ready: {exc}")
    assert check_tool_source(src.tools, src.schemas) == []
