"""Explicit-confirmation gate and duplicate-attempt tracking. Owner: Cheich.

Application code, not the model, completes a rebooking. The model can only call prepare_rebooking.
The traveler's explicit confirmation reaches confirm(), which checks the rules and then calls an injected
`complete(booking_id, option_id)` function. That function is the swap point: a mock today, Jian's real one later.

Rules enforced here:
- Only an option that prepare_rebooking validated can be confirmed.
- The confirmed option must be the latest prepared one.
- The option is re-checked first; if its details changed, the traveler must review and confirm again.
- A confirmed or uncertain attempt is never repeated.
- With the mock completer, only mock options are accepted (never send a mock option to Duffel or the reverse).
- Once a search has been checked by code against the traveler's limits, those limits are remembered for the booking.
  An option outside them cannot be prepared or confirmed, even if the agent asks for it by id. (PRD 3c: code checks
  all confirmed limits before completing a change.) The limits are the ones the agent passed to its last checked
  search; the code cannot know the traveler confirmed them, only that they were complete and valid.
"""
import json
from typing import Any, Callable

from backend.app.contract.models import Limits, Option
from backend.app.harness.guards import check_option_known
from backend.app.harness.limits import check_option


class GateRefusal(Exception):
    """The gate refused to let an option through. The message is written for the agent, so it can explain."""


class ConfirmationGate:
    def __init__(self, tools: dict[str, Callable[..., Any]], complete: Callable[[str, str], dict[str, Any]],
                 source: str = "mock"):
        self._prepare = tools["prepare_rebooking"]
        self._tools = tools
        self._complete = complete
        self.source = source  # "mock": accept only mock options. "real": the completer routes by option source.
        self._prepared: dict[str, tuple[str, str, str]] = {}  # booking -> (option_id, fingerprint, data_source)
        self._attempts: dict[tuple[str, str], dict[str, Any]] = {}
        self.last_prepared: tuple[str, str] | None = None  # (booking_id, option_id)
        self._limits: dict[str, Limits] = {}  # booking -> limits of the last search that code checked

    def tools(self) -> dict[str, Callable[..., Any]]:
        """The agent's tools: search remembers its limits, and prepare_rebooking is held to them and remembered."""
        wrapped = dict(self._tools)
        search = self._tools.get("search_replacements")

        if search is not None:
            def search_replacements(**kwargs: Any) -> Any:
                result = search(**kwargs)
                booking_id = kwargs.get("booking_id")
                if isinstance(result, dict) and result.get("limits_checked_by_code") is True:
                    try:
                        self._limits[booking_id] = Limits.model_validate(kwargs.get("limits"))
                    except Exception:
                        self._limits.pop(booking_id, None)
                return result

            wrapped["search_replacements"] = search_replacements

        def prepare_rebooking(booking_id: str, option_id: str) -> dict[str, Any]:
            result = self._prepare(booking_id=booking_id, option_id=option_id)
            reasons = self._outside_limits(booking_id, result)
            if reasons:
                self._prepared.pop(booking_id, None)
                raise GateRefusal(
                    "This option is outside the traveler's confirmed limits (" + "; ".join(reasons) + "). Do not "
                    "present or recommend it. Search again with limits the traveler has confirmed, or ask the "
                    "traveler what to change.")
            self._record(booking_id, option_id, result)
            return result

        wrapped["prepare_rebooking"] = prepare_rebooking
        return wrapped

    def _outside_limits(self, booking_id: str, result: Any) -> list[str]:
        """Why a prepared option breaks the remembered limits. Empty when it fits, or when no limits are known yet."""
        limits = self._limits.get(booking_id)
        if limits is None:
            return []
        try:
            return check_option(Option.model_validate(result["latest_option_details"]), limits)
        except Exception:  # with limits known, an option that cannot be read must not pass
            return ["the option could not be checked"]

    def _record(self, booking_id: str, option_id: str, result: dict[str, Any]) -> None:
        if result.get("validation_result") != "valid":
            self._prepared.pop(booking_id, None)
            return
        option = result["latest_option_details"]
        if not check_option_known(option).allowed:  # unknown eligibility or cost blocks rebooking
            self._prepared.pop(booking_id, None)
            return
        self._prepared[booking_id] = (option_id, self._fingerprint(option), option.get("data_source", ""))
        self.last_prepared = (booking_id, option_id)

    @staticmethod
    def _fingerprint(option: dict[str, Any]) -> str:
        return json.dumps(option, sort_keys=True, default=str)

    def confirm(self, booking_id: str, option_id: str) -> dict[str, Any]:
        """Call only after the traveler explicitly confirmed this option. Returns a status dict."""
        key = (booking_id, option_id)
        if key in self._attempts:
            return {**self._attempts[key], "repeat": True}  # never run the same attempt twice

        prepared = self._prepared.get(booking_id)
        if prepared is None:
            return self._reject("This option has not been validated. Prepare it first.")
        if prepared[0] != option_id:
            return self._reject("This is not the option the traveler last reviewed.")
        if self.source == "mock" and prepared[2] != "mock":
            return self._reject("Only mock options can be completed by the mock service.")

        try:  # re-check the latest details before completing
            latest = self._prepare(booking_id=booking_id, option_id=option_id)
        except Exception as exc:
            return self._reject(f"Could not re-check the option: {type(exc).__name__}")
        outside = self._outside_limits(booking_id, latest)
        if outside:  # the option changed, or the limits did, since it was shown
            self._prepared.pop(booking_id, None)
            return self._reject("The option is outside the traveler's confirmed limits (" + "; ".join(outside) + ").")
        self._record(booking_id, option_id, latest)
        what_changed = self._changes_text(latest)
        if booking_id not in self._prepared:
            return self._reject("The option is no longer valid. Review another option." + what_changed)
        if self._prepared[booking_id][1] != prepared[1]:
            return self._reject(
                "The option's details changed. Review the updated details and confirm again." + what_changed)

        try:
            outcome = {"status": "confirmed", "result": self._complete(booking_id, option_id)}
        except Exception as exc:
            outcome = {"status": "pending", "reason": f"Result uncertain ({type(exc).__name__}). Do not retry."}
        self._attempts[key] = outcome
        return outcome

    @staticmethod
    def _changes_text(latest: Any) -> str:
        """The re-check's changes_to_review as text, so the traveler is told what changed."""
        changes = latest.get("changes_to_review") if isinstance(latest, dict) else None
        if not isinstance(changes, list) or not changes:
            return ""
        return " What changed: " + "; ".join(str(c) for c in changes) + "."

    @staticmethod
    def _reject(reason: str) -> dict[str, Any]:
        return {"status": "rejected", "reason": reason}
