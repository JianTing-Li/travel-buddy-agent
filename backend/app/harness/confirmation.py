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
                 source: str = "mock", require_checked_search: bool = False):
        self._prepare = tools["prepare_rebooking"]
        self._tools = tools
        self._complete = complete
        self.source = source  # "mock": accept only mock options. "real": the completer routes by option source.
        # False (default): with no checked search yet there are no limits to hold an option to, so nothing is enforced.
        # True: fail closed. An option cannot be prepared or confirmed until a search checked by code has confirmed
        # the limits. Off by default because many existing flows prepare without searching first.
        self.require_checked_search = require_checked_search
        self._prepared: dict[str, tuple[str, str, str]] = {}  # booking -> (option_id, fingerprint, data_source)
        self._attempts: dict[tuple[str, str], dict[str, Any]] = {}
        self.last_prepared: tuple[str, str] | None = None  # (booking_id, option_id)
        self._limits: dict[str, Limits] = {}  # booking -> limits of the last search that code checked

    def forget(self, booking_id: str) -> None:
        """Drop everything the gate holds for one booking (test tool: the booking was put back to normal)."""
        self._prepared.pop(booking_id, None)
        self._limits.pop(booking_id, None)
        self._attempts = {key: value for key, value in self._attempts.items() if key[0] != booking_id}
        if self.last_prepared and self.last_prepared[0] == booking_id:
            self.last_prepared = None

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
                        limits = Limits.model_validate(kwargs.get("limits"))
                    except Exception:
                        self._limits.pop(booking_id, None)
                        return result
                    self._limits[booking_id] = limits
                    return {**result, **self._excluded_summary(search, booking_id, result, limits)}
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

    @staticmethod
    def _excluded_summary(search: Callable[..., Any], booking_id: str, result: dict[str, Any],
                          limits: Limits) -> dict[str, Any]:
        """The options the limits filter removed, and which limit each one breaks, so the agent can explain a
        "nothing fits" result (PRD: say which limits cannot be met).

        Only typed facts and code-written reasons are passed on. Free text from the source (flight_details.extras) is
        untrusted and is never included, so a planted instruction cannot ride along.
        """
        try:
            kept = {o["option_id"] for o in result.get("options", [])}
            everything = search(booking_id=booking_id)  # no limits: the unfiltered list
            removed = []
            for raw in everything.get("options", []):
                if raw.get("option_id") in kept:
                    continue
                option = Option.model_validate(raw)
                removed.append({
                    "option_id": option.option_id,
                    "arrives": option.flight_details.arrives,
                    "additional_cost": option.additional_cost,
                    "currency": option.currency,
                    "connections": option.flight_details.connections,
                    "reasons": check_option(option, limits),
                })
            return {
                "excluded_by_limits": removed,
                "excluded_note": "Removed by code because they break the traveler's confirmed limits. They are NOT "
                                 "suitable recommendations and cannot be prepared. You may explain which limit each "
                                 "one breaks, clearly separate from any recommendation.",
            }
        except Exception:  # explaining is a bonus; a failure here must never break the search itself
            return {}

    def _outside_limits(self, booking_id: str, result: Any) -> list[str]:
        """Why a prepared option breaks the remembered limits. Empty when it fits, or when no limits are known yet."""
        limits = self._limits.get(booking_id)
        if limits is None:
            return ["no limits were confirmed by a checked search yet"] if self.require_checked_search else []
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
