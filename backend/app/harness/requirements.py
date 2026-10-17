"""Requirement check: the agent may only search once all required limits are known and valid. Owner: Cheich.

The PRD says the agent must capture the traveler's required limits, ask a focused question when one is unclear,
and never assume a limit is flexible. This is the code side of that rule. Before a search runs, `check_limits`
looks at the limits the agent wants to search with. If any required limit is missing or invalid, the search is
refused and the agent is told, in plain words, exactly what to ask the traveler.

It checks that the limits are COMPLETE and VALID (contract v1: Limits). It cannot know whether the traveler
really said them, so the prompt still has to make the agent ask and confirm; this rule only makes sure a search
can never run on a guess that is missing a piece.

Preferences (for example "nonstop if possible") are not part of the contract's Limits in MVP 1, so they are not
checked here; the agent weighs them when it compares the options that passed the limits filter.
"""
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from backend.app.contract.models import Limits

# What to ask the traveler for, in plain words, for each required limit.
REQUIRED: dict[str, str] = {
    "budget_additional_cost": "the most extra the traveler will pay, for the whole booking (0 if nothing extra)",
    "currency": "the currency of that budget, as a 3-letter code such as USD",
    "arrive_by": "the latest acceptable arrival at the destination, as local time with its UTC offset "
                 "(for example 2026-10-15T15:00-07:00)",
    "max_connections": "the most connections the traveler accepts (0 means nonstop only)",
    "passenger_count": "how many people are traveling (everyone stays on the same flight)",
}


@dataclass
class RequirementsCheck:
    ok: bool
    missing: list[str] = field(default_factory=list)
    invalid: dict[str, str] = field(default_factory=dict)  # field -> what is wrong
    message: str = ""


def check_limits(limits: Any) -> RequirementsCheck:
    """Are all required limits present and valid? If not, say exactly what is missing."""
    given = limits if isinstance(limits, dict) else {}
    missing = [name for name in REQUIRED if given.get(name) is None]
    invalid: dict[str, str] = {}

    if not missing:
        try:
            Limits.model_validate(given)
        except (ValidationError, ValueError, TypeError) as exc:
            if isinstance(exc, ValidationError):
                for err in exc.errors():
                    name = str(err["loc"][0]) if err["loc"] else "limits"
                    invalid[name] = str(err["msg"])
            else:
                invalid["limits"] = "not readable"

    if not missing and not invalid:
        return RequirementsCheck(ok=True)

    lines = ["Cannot search yet: the required limits are not complete and valid."]
    if missing:
        lines.append("Missing: " + "; ".join(f"{name} ({REQUIRED[name]})" for name in missing) + ".")
    if invalid:
        lines.append("Not valid: " + "; ".join(f"{name}: {why}" for name, why in invalid.items()) + ".")
    lines.append(
        "If the traveler already told you these, call search_replacements again with every field in `limits`. "
        "Otherwise ask the traveler a short, focused question for what is missing. Never guess a value and never "
        "assume a limit is flexible."
    )
    return RequirementsCheck(ok=False, missing=missing, invalid=invalid, message=" ".join(lines))
