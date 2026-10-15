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
        changes.append(f"Additional cost changed from {old.additional_cost:g} {old.currency} "
                       f"to {new.additional_cost:g} {new.currency}.")
    for key, label in DETAIL_LABELS.items():
        if old.flight_details.get(key) != new.flight_details.get(key):
            changes.append(f"{label} changed from {old.flight_details.get(key)} to {new.flight_details.get(key)}.")
    if old.eligibility != new.eligibility:
        changes.append(f"Eligibility changed from {old.eligibility} to {new.eligibility}.")
    return changes


def clock_text(moment: datetime) -> str:
    """e.g. 'Oct 16, 9:00 AM (UTC-04:00)': the wall-clock time in the timestamp's own zone."""
    hour = moment.hour % 12 or 12
    zone = moment.strftime("%z")
    offset = f"{zone[:3]}:{zone[3:]}" if zone else "+00:00"
    return f"{moment:%b} {moment.day}, {hour}:{moment:%M} {'AM' if moment.hour < 12 else 'PM'} (UTC{offset})"
