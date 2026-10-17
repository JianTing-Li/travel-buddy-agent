"""Limits filter: removes options that break the traveler's confirmed required limits. Owner: Cheich.

Pure code, no model. It plugs into Jian's tool as `build_tools(limits_filter=limits_filter)`; the tool then reports
`limits_checked_by_code: true` and the model only ever sees options that passed.

An option is kept only if ALL of these hold (contract v1):
- eligibility is "eligible" and validity is "valid" (unknown, ineligible, expired and unavailable are removed)
- it arrives at or before Limits.arrive_by (compared as real moments in time, so time zones are handled)
- its additional cost is within the budget, and ONLY when its currency equals Limits.currency. An option in another
  currency cannot be compared, so it is removed (a number in the wrong currency must never look cheap)
- its connections are within max_connections

It fails closed: missing, incomplete or invalid limits, or an option that cannot be read, remove the option(s)
instead of letting anything through.

Not checked here: Limits.passenger_count. Options are for the whole booking and carry no passenger count, so the
booking itself keeps everyone together; the value is only validated.
"""
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from backend.app.contract.models import Limits, Option


def _parse(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError("time has no UTC offset")
    return moment


def check_option(option: Any, limits: Limits) -> list[str]:
    """Why this option must be removed. An empty list means it is within every limit."""
    try:
        if not isinstance(option, Option):
            return ["option could not be read"]
        reasons: list[str] = []

        if option.eligibility != "eligible":  # contract: "unknown" always blocks, "ineligible" is not allowed
            reasons.append(f"eligibility is {option.eligibility}")
        if option.validity != "valid":
            reasons.append(f"option is {option.validity}")

        if _parse(option.flight_details.arrives) > _parse(limits.arrive_by):
            reasons.append("arrives after the arrival deadline")

        if option.currency != limits.currency:
            reasons.append(f"priced in {option.currency}, budget is in {limits.currency}: cannot be compared")
        elif round(option.additional_cost, 2) > round(limits.budget_additional_cost, 2):
            reasons.append("additional cost is over the budget")

        if option.flight_details.connections > limits.max_connections:
            reasons.append("has more connections than allowed")
        return reasons
    except Exception:  # anything unreadable fails closed
        return ["option could not be checked"]


def _read_limits(limits: Any) -> Limits | None:
    try:
        return Limits.model_validate(limits)
    except (ValidationError, ValueError, TypeError):
        return None


def exclusion_reasons(options: list[Option], limits: dict[str, Any]) -> dict[str, list[str]]:
    """option_id -> reasons it was removed, for logs, tests and explaining a 'no options' result.

    With unusable limits every option is reported as removed for that reason.
    """
    parsed = _read_limits(limits)
    out: dict[str, list[str]] = {}
    for i, option in enumerate(options):
        key = getattr(option, "option_id", f"option {i}")
        reasons = ["limits are missing or not valid: nothing can be checked"] if parsed is None else check_option(option, parsed)
        if reasons:
            out[key] = reasons
    return out


def limits_filter(options: list[Option], limits: dict[str, Any]) -> list[Option]:
    """The hook for build_tools(limits_filter=...): keep only options inside every confirmed limit."""
    parsed = _read_limits(limits)
    if parsed is None:
        return []
    return [option for option in options if not check_option(option, parsed)]
