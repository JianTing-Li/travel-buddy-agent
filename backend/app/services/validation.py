"""Option checks shared by the booking services (mock and Duffel). Owner: Jian.

Application code, not the model, decides whether an option can be rebooked: unknown eligibility or an
unavailable or expired option always blocks it, and any change since the traveler last saw it must be reviewed.
"""
from datetime import datetime

from ..contract.models import Option
from .mock import provisional

DETAIL_LABELS = {
    "departs": "Departure time", "arrives": "Arrival time", "duration": "Duration",
    "connections": "Connections", "flight": "Flight", "origin": "Origin", "destination": "Destination",
}


def validate_option(option: Option) -> tuple[str, list[str]]:
    """Return (validation_result, reasons) from the option's own eligibility and validity."""
    if option.eligibility == provisional.INELIGIBLE:
        return provisional.RESULT_INVALID, ["This option is not eligible for this booking."]
    if option.eligibility != provisional.ELIGIBLE:
        return provisional.RESULT_INVALID, ["Eligibility could not be verified for this option."]
    if option.validity == provisional.VALIDITY_EXPIRED:
        return provisional.RESULT_UNAVAILABLE, ["This option has expired."]
    if option.validity == provisional.VALIDITY_UNAVAILABLE:
        return provisional.RESULT_UNAVAILABLE, ["This option is no longer available."]
    if option.validity != provisional.VALIDITY_VALID:
        return provisional.RESULT_INVALID, ["The status of this option could not be verified."]
    return provisional.RESULT_VALID, []


def diff_options(old: Option, new: Option) -> list[str]:
    """Human-readable differences the traveler must review."""
    changes = []
    if old.additional_cost != new.additional_cost or old.currency != new.currency:
        changes.append(f"Extra cost changed from {old.additional_cost:g} {old.currency} "
                       f"to {new.additional_cost:g} {new.currency}.")
    for key, label in DETAIL_LABELS.items():
        before, after = getattr(old.flight_details, key), getattr(new.flight_details, key)
        if before != after:
            if key in ("departs", "arrives"):  # times as travelers read them, not raw timestamps
                before, after = _readable_time(before), _readable_time(after)
            changes.append(f"{label} changed from {before} to {after}.")
    if old.eligibility != new.eligibility:
        changes.append(f"Eligibility changed from {old.eligibility} to {new.eligibility}.")
    return changes


def local_time_text(moment: datetime) -> str:
    """e.g. '9:30 AM on Oct 16': the local time where the flight is, for notices travelers read."""
    hour = moment.hour % 12 or 12
    return f"{hour}:{moment:%M} {'AM' if moment.hour < 12 else 'PM'} on {moment:%b} {moment.day}"


def _readable_time(value: object) -> object:
    try:
        return local_time_text(datetime.fromisoformat(str(value)))
    except ValueError:
        return value
