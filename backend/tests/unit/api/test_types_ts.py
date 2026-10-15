"""Checks that frontend/src/app/types.ts uses the same field names as the Python models. Owner: Jian."""
import re
from datetime import date
from pathlib import Path

import pytest

from backend.app.api import schemas
from backend.app.contract import models
from backend.app.services import airline_change
from backend.app.services.mock.mock_service import MockService

TYPES_TS = Path(__file__).resolve().parents[4] / "frontend" / "src" / "app" / "types.ts"


def ts_interface_fields(name: str) -> set[str]:
    source = TYPES_TS.read_text()
    match = re.search(rf"export interface {name}\b[^{{]*\{{(.*?)^\}}", source, re.DOTALL | re.MULTILINE)
    assert match, f"interface {name} not found in types.ts"
    return {m.group(1) for m in re.finditer(r"^\s{2}(\w+)\??:", match.group(1), re.MULTILINE)}


CONTRACT = ["Limits", "Option", "TripContext", "ValidationResult", "Handoff"]
API = ["SessionCreate", "SessionOut", "BookingSummary", "BookingDetail", "ErrorOut", "ChatIn", "ConfirmCard",
       "ChatOut", "ConfirmIn", "ConfirmOut", "ChangeCheckOut"]


@pytest.mark.parametrize("name", CONTRACT)
def test_contract_interfaces_match_the_pydantic_models(name):
    assert ts_interface_fields(name) == set(getattr(models, name).model_fields)


@pytest.mark.parametrize("name", API)
def test_api_interfaces_match_the_pydantic_schemas(name):
    assert ts_interface_fields(name) == set(getattr(schemas, name).model_fields)


def test_airline_change_interface_matches_the_service_model():
    assert ts_interface_fields("AirlineChange") == set(airline_change.AirlineChange.model_fields)


def test_confirmation_interface_matches_what_the_mock_service_returns():
    service = MockService(today=date(2026, 10, 15))
    service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    confirmation = service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    assert ts_interface_fields("Confirmation") == set(confirmation)


def test_flight_details_documents_the_keys_the_mock_service_uses():
    service = MockService(today=date(2026, 10, 15))
    used = set(service.search_replacements("MOCK-CASE-1")[0].flight_details)
    assert used <= ts_interface_fields("FlightDetails")


def test_session_header_name_matches_the_backend():
    from backend.app.api.main import SESSION_HEADER
    assert f'SESSION_HEADER = "{SESSION_HEADER}"' in TYPES_TS.read_text()
