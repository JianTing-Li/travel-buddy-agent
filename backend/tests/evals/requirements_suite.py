"""Scores requirement understanding against the PRD target (2c): at least 90% of cases captured correctly. Owner: Cheich.

Each case in requirements/extraction_cases.json is one traveler message. The suite plays it through Jian's real API:

  turn 0   the traveler's message
  turn 1   if the agent has not searched yet (it asked a question), the traveler answers with the case's followup_answer
  turn 2   if it still has not searched, one more nudge: "Yes, that is right, please search."

Then CODE compares the limits the agent passed to its first search that the limits filter accepted with the case's
final_limits. A case PASSES only if all of these hold (PRD: a missing required limit is a failure):
  - it searched with all five required limits and every one is right (budget, currency, arrival time in Pacific time,
    connections, passengers)
  - when the case needs a clarification, it asked a question and did NOT search on the first message
  - it never prepared or confirmed anything, and never claimed a booking

Scripted mode uses an ideal agent built from the case data (free; it tests the scoring and the code around the model).
Live mode uses the real model and costs credit.
"""
import json
import re
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.tests.evals.checks import RunRecord, TurnRecord, _accepted_searches, claims_success
from backend.tests.evals.recording import RecordingModel, ScriptedModel, resp, text, tool
from backend.tests.evals.scenarios import Ctx, Scenario

CASES_PATH = Path(__file__).parent / "requirements" / "extraction_cases.json"
NUDGE = "Yes, that is right, please search."
TARGET = 0.90
PACIFIC_OFFSETS_HOURS = {-7, -8}


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def _ideal_limits(case: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    f = case["final_limits"]
    return {"budget_additional_cost": f["budget_additional_cost"], "currency": f["currency"],
            "arrive_by": f"{ctx.day}T{f['arrive_by_local']}:00-07:00", "max_connections": f["max_connections"],
            "passenger_count": f["passenger_count"]}


def _ideal_replies(case: dict[str, Any], ctx: Ctx, turn: int) -> list[Any]:
    """What a well-behaved agent does: ask when something is unclear, otherwise search with the right limits."""
    needs_question = bool(case["expected"]["must_ask_before_search"])
    search = resp(tool("search_replacements", {"booking_id": ctx.booking_id, "limits": _ideal_limits(case, ctx)}))
    summary = resp(text("These are simulated options. Nothing is booked."))
    if turn == 0 and needs_question:
        return [resp(tool("get_trip_context", {"booking_id": ctx.booking_id})),
                resp(text("This is a simulated booking. Before I search, could you tell me what is unclear?"))]
    if turn == 0:
        return [resp(tool("get_trip_context", {"booking_id": ctx.booking_id})), search, summary]
    return [search, summary]


def play_case(case: dict[str, Any], mode: str, live_client: Any = None, model_name: str = "eval-scripted",
              replies: Any = None) -> RunRecord:
    """One run of one case. `replies(case, ctx, turn)` can replace the ideal scripted agent (used to test the scoring)."""
    scripted = ScriptedModel() if mode == "scripted" else None
    recorder = RecordingModel(scripted if scripted is not None else live_client)
    api = TestClient(create_app(model_client=recorder, model=model_name))
    scenario = Scenario(id=case["id"], title=case["id"], booking_id=case["booking_id"], source="requirements", turns=[],
                        may_search_in_first_turn=not case["expected"]["must_ask_before_search"])
    rec = RunRecord(scenario=scenario, mode=mode)
    started = time.monotonic()
    try:
        headers = {"X-Session-Id": api.post("/sessions").json()["session_id"]}
        detail = api.get(f"/bookings/{case['booking_id']}", headers=headers).json()
        day = _travel_day(api, headers["X-Session-Id"], case["booking_id"], detail)
        ctx = Ctx(booking_id=case["booking_id"], day=day)
        for turn, say in enumerate([case["traveler_message"], case["followup_answer"], NUDGE]):
            if turn > 0 and _accepted_searches(_so_far(rec, recorder)):
                break
            recorder.turn = turn
            if scripted is not None:
                scripted.queue(*(replies or _ideal_replies)(case, ctx, turn))
            answer = api.post("/chat", json={"booking_id": case["booking_id"], "message": say}, headers=headers)
            record = TurnRecord(say=say)
            rec.turns.append(record)
            if answer.status_code != 200:
                rec.error = f"chat failed on turn {turn}: HTTP {answer.status_code}"
                break
            body = answer.json()
            record.reply, record.stopped_reason = body["reply"], body["stopped_reason"]
        rec.final_status = api.get(f"/bookings/{case['booking_id']}", headers=headers).json()["summary"]["status"]
    except Exception as exc:
        rec.error = f"{type(exc).__name__}: {exc}"
    finally:
        recorder.collect_results()
        rec.calls = recorder.calls
        rec.seconds = time.monotonic() - started
    return rec


def _so_far(rec: RunRecord, recorder: RecordingModel) -> RunRecord:
    """The run so far, with the tool answers attached, so we can tell whether a search has been accepted yet."""
    recorder.collect_results()
    snapshot = RunRecord(scenario=rec.scenario, mode=rec.mode, turns=rec.turns, calls=list(recorder.calls))
    return snapshot


_REQUEST = re.compile(r"\?|\bplease (tell|let|confirm|provide|share|give)\b|\blet me know\b|\bi need (to know|you to)\b|"
                      r"\bcould you\b|\bcan you\b", re.I)


def _asks(reply: str) -> bool:
    """A clarifying question, or a plain request for the missing information."""
    return bool(_REQUEST.search(reply))


def score(case: dict[str, Any], rec: RunRecord) -> dict[str, Any]:
    """Pass or fail for one run, with the reasons. All judging is code."""
    problems: list[str] = []
    final = case["final_limits"]
    searches = _accepted_searches(rec)

    if rec.error:
        problems.append(rec.error)
    if case["expected"]["must_ask_before_search"]:
        if any(call["turn"] == 0 for call, _ in searches):
            problems.append("searched on the first message although a clarification was needed")
        if not _asks(rec.turns[0].reply if rec.turns else ""):
            problems.append("did not ask a question on the first message")

    if not searches:
        problems.append("never searched with complete, valid limits (a required limit was missed)")
    else:
        used = searches[0][0]["input"].get("limits") or {}
        for name in ("budget_additional_cost", "currency", "max_connections", "passenger_count"):
            if used.get(name) != final[name]:
                problems.append(f"{name}: used {used.get(name)!r}, expected {final[name]!r}")
        try:
            moment = datetime.fromisoformat(used.get("arrive_by", ""))
            local = f"{moment.hour:02d}:{moment.minute:02d}"
            hours = moment.utcoffset().total_seconds() / 3600
            if local != final["arrive_by_local"] or hours not in PACIFIC_OFFSETS_HOURS:
                problems.append(f"arrive_by: used {used.get('arrive_by')!r}, expected {final['arrive_by_local']} Pacific")
        except (ValueError, AttributeError, TypeError):
            problems.append(f"arrive_by: not a usable time ({used.get('arrive_by')!r})")

    if any(c["name"] == "prepare_rebooking" for c in rec.calls):
        problems.append("prepared a rebooking during requirement gathering")
    if rec.final_status == "rebooked" or any(claims_success(t.reply) for t in rec.turns):
        problems.append("booked or claimed a booking")

    asked_first = bool(rec.turns) and not any(call["turn"] == 0 for call, _ in searches)
    return {"case": case["id"], "passed": not problems, "problems": problems, "asked_first": asked_first,
            "turns": len(rec.turns), "seconds": round(rec.seconds, 2)}


def run_suite(mode: str, runs: int, case_ids: list[str] | None = None, live_client: Any = None,
              model_name: str = "eval-scripted") -> list[dict[str, Any]]:
    results = []
    for case in load_cases():
        if case_ids and case["id"] not in case_ids:
            continue
        for n in range(1, runs + 1):
            result = score(case, play_case(case, mode, live_client, model_name))
            result["run"] = n
            results.append(result)
    return results


def format_report(results: list[dict[str, Any]], mode: str) -> str:
    lines = [f"Requirement-understanding report ({mode} mode)", ""]
    header = f"{'case':<38}{'runs':>5}{'passed':>8}{'asked first':>13}"
    lines += [header, "-" * len(header)]
    for cid in dict.fromkeys(r["case"] for r in results):
        rows = [r for r in results if r["case"] == cid]
        lines.append(f"{cid:<38}{len(rows):>5}{sum(r['passed'] for r in rows):>8}{sum(r['asked_first'] for r in rows):>13}")
    passed = sum(r["passed"] for r in results)
    rate = passed / len(results) if results else 0.0
    verdict = "MEETS" if rate >= TARGET else "BELOW"
    lines += ["", f"Captured correctly: {passed} of {len(results)} runs ({rate:.0%}). PRD target: at least {TARGET:.0%}. "
                  f"{verdict} the target.", f"Median seconds per run: "
                  f"{statistics.median(r['seconds'] for r in results) if results else 0:.1f}", ""]
    for r in results:
        if not r["passed"]:
            lines.append(f"  {r['case']} run {r['run']}: " + "; ".join(r["problems"]))
    lines.append("Judged by code only. Simulated data: no real tickets are bought or changed.")
    return "\n".join(lines)

def _travel_day(api: Any, session_id: str, booking_id: str, detail: dict[str, Any]) -> str:
    """The day the replacement flights are on: the original flight's day, except for a missed flight that already
    left the day before. Read from the in-process app, not from the model."""
    service = api.app.state.sessions.get(session_id).service
    return service.travel_day(booking_id) or detail["trip"]["original_itinerary"]["departs"][:10]
