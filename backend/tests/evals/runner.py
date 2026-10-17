"""Eval runner for the four PRD cases. Owner: Cheich.

It plays each case through the REAL app (Jian's HTTP API, in-process): create a session, send the traveler's messages
to /chat, and press Confirm through /confirm when the case says so. Only the model differs between the two modes:

  scripted   a prepared agent plays back fixed replies. Free, repeatable, never calls the network. It tests the code
             around the model (limits filter, requirement check, guards, confirmation gate, the API).
  live       the real model answers. It costs real API credit, so you must say how many runs with --runs N.

Run from the project root:
  .venv/bin/python -m backend.tests.evals.runner --mode scripted
  .venv/bin/python -m backend.tests.evals.runner --mode live --runs 3 --cases case_1,case_4 --out results.json
  .venv/bin/python -m backend.tests.evals.runner --mode scripted --suite requirements
  .venv/bin/python -m backend.tests.evals.runner --mode live --suite requirements --runs 3

All judging is done by code (see checks.py). Nothing here can book a real flight: the data is simulated.
"""
import argparse
import json
import logging
import statistics
import sys
import time
from typing import Any, Callable

from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.tests.evals.checks import CheckResult, RunRecord, TurnRecord, run_checks
from backend.tests.evals.recording import RecordingModel, ScriptedModel
from backend.tests.evals.scenarios import SCENARIOS, Ctx, Scenario

DEFAULT_LIVE_MODEL = "claude-haiku-5-5"


def play(scenario: Scenario, mode: str, live_client: Any = None, model_name: str = "eval-scripted") -> RunRecord:
    """One conversation with a fresh session. Returns everything the checks need."""
    scripted = ScriptedModel() if mode == "scripted" else None
    recorder = RecordingModel(scripted if scripted is not None else live_client)
    api = TestClient(create_app(model_client=recorder, model=model_name))
    rec = RunRecord(scenario=scenario, mode=mode)
    started = time.monotonic()
    try:
        session_id = api.post("/sessions").json()["session_id"]
        headers = {"X-Session-Id": session_id}
        detail = api.get(f"/bookings/{scenario.booking_id}", headers=headers).json()
        ctx = Ctx(booking_id=scenario.booking_id, day=detail["trip"]["original_itinerary"]["departs"][:10])

        for index, turn in enumerate(scenario.turns):
            recorder.turn = index
            if scripted is not None:
                if turn.agent is None:
                    raise ValueError(f"{scenario.id} turn {index} has no scripted agent steps")
                scripted.queue(*turn.agent(ctx))
            answer = api.post("/chat", json={"booking_id": scenario.booking_id, "message": turn.say}, headers=headers)
            record = TurnRecord(say=turn.say)
            rec.turns.append(record)
            if answer.status_code != 200:
                rec.error = f"chat failed on turn {index}: HTTP {answer.status_code}"
                break
            body = answer.json()
            record.reply, record.stopped_reason = body["reply"], body["stopped_reason"]
            card = body.get("confirm_card")
            record.card_option_id = card["option"]["option_id"] if card else None
            if turn.confirm and card:  # the traveler presses the Confirm button: the app, not the model, books
                out = api.post("/confirm", json={"booking_id": scenario.booking_id,
                                                 "option_id": card["option"]["option_id"]}, headers=headers)
                record.confirm_outcome = out.json()
        rec.final_status = api.get(f"/bookings/{scenario.booking_id}", headers=headers).json()["summary"]["status"]
    except Exception as exc:  # a crash is a failed run, reported plainly
        rec.error = f"{type(exc).__name__}: {exc}"
    finally:
        recorder.collect_results()
        rec.calls = recorder.calls
        rec.seconds = time.monotonic() - started
    return rec


def evaluate(rec: RunRecord) -> dict[str, Any]:
    checks = run_checks(rec)
    hard_failures = [c for c in checks if not c.soft and not c.ok]
    completed = next((c.ok for c in checks if c.name == "completed_as_expected"), False)
    return {
        "scenario": rec.scenario.id, "mode": rec.mode, "seconds": round(rec.seconds, 2), "error": rec.error,
        "violations": [c.name for c in hard_failures], "completed": completed,
        "checks": [{"name": c.name, "ok": c.ok, "soft": c.soft, "detail": c.detail} for c in checks],
        "turns": [{"say": t.say, "reply": t.reply, "stopped": t.stopped_reason, "card": t.card_option_id,
                   "confirm": t.confirm_outcome} for t in rec.turns],
        "tool_calls": [{"turn": c["turn"], "name": c["name"], "error": c.get("is_error", False)} for c in rec.calls],
    }


def run_all(scenario_ids: list[str], mode: str, runs: int, live_client: Any = None,
            model_name: str = "eval-scripted") -> list[dict[str, Any]]:
    results = []
    for sid in scenario_ids:
        for n in range(1, runs + 1):
            result = evaluate(play(SCENARIOS[sid], mode, live_client, model_name))
            result["run"] = n
            results.append(result)
    return results


def format_report(results: list[dict[str, Any]], mode: str) -> str:
    lines = [f"Eval report ({mode} mode)", ""]
    header = f"{'case':<8}{'runs':>5}{'rule violations':>17}{'completed':>11}{'median s':>10}  soft checks that failed"
    lines += [header, "-" * len(header)]
    total_runs = total_violations = 0
    for sid in dict.fromkeys(r["scenario"] for r in results):
        rows = [r for r in results if r["scenario"] == sid]
        violations = sum(1 for r in rows if r["violations"] or r["error"])
        soft_failed = sorted({c["name"] for r in rows for c in r["checks"] if c["soft"] and not c["ok"]})
        done = sum(1 for r in rows if r["completed"])
        lines.append(f"{sid:<8}{len(rows):>5}{violations:>17}{f'{done}/{len(rows)}':>11}"
                     f"{statistics.median(r['seconds'] for r in rows):>10.1f}  {', '.join(soft_failed) or '-'}")
        total_runs += len(rows)
        total_violations += violations
    lines += ["", f"Runs with a rule violation or a crash: {total_violations} of {total_runs} (PRD target: 0).", ""]
    for r in results:
        if r["violations"] or r["error"]:
            detail = "; ".join(f"{c['name']}: {c['detail']}" for c in r["checks"] if not c["soft"] and not c["ok"])
            lines.append(f"  {r['scenario']} run {r['run']}: {r['error'] or detail}")
    lines.append("Judged by code only. Simulated data: no real tickets are bought or changed.")
    return "\n".join(lines)


def main(argv: list[str] | None = None, live_client_factory: Callable[[], Any] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the four PRD eval cases.")
    parser.add_argument("--mode", choices=["scripted", "live"], required=True)
    parser.add_argument("--suite", choices=["prd", "requirements"], default="prd",
                        help="prd: the 4 PRD cases (default). requirements: the 9 requirement-understanding cases "
                             "scored against the PRD's 90%% target")
    parser.add_argument("--runs", type=int, help="runs per case (required for live: it costs real API credit)")
    parser.add_argument("--cases", default="all", help="comma-separated ids, e.g. case_1,case_4 (default: all)")
    parser.add_argument("--model", help=f"live model (default: MODEL from .env, else {DEFAULT_LIVE_MODEL})")
    parser.add_argument("--out", help="also save the full results as JSON to this path")
    args = parser.parse_args(argv)
    logging.getLogger("travel_buddy.api").setLevel(logging.WARNING)  # keep the report readable

    if args.suite == "requirements":
        from backend.tests.evals import requirements_suite as rs
        known = [c["id"] for c in rs.load_cases()]
    else:
        known = list(SCENARIOS)
    ids = known if args.cases == "all" else [c.strip() for c in args.cases.split(",") if c.strip()]
    unknown = [c for c in ids if c not in known]
    if unknown:
        parser.error(f"unknown case(s) {unknown}; choose from {', '.join(known)}")
    if args.mode == "live" and not args.runs:
        parser.error("live mode uses the real model and costs money: say how many runs per case with --runs N")
    runs = args.runs or 1
    if runs < 1:
        parser.error("--runs must be at least 1")

    live_client, model_name = None, "eval-scripted"
    if args.mode == "live":
        from backend.app import config
        model_name = args.model or config.MODEL or DEFAULT_LIVE_MODEL
        if live_client_factory is not None:
            live_client = live_client_factory()
        else:
            if not config.ANTHROPIC_API_KEY:
                parser.error("ANTHROPIC_API_KEY is not set in .env")
            import anthropic
            live_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        print(f"Live mode: model {model_name}, {len(ids)} case(s) x {runs} run(s) = {len(ids) * runs} conversation(s) "
              "with the real model.\n")

    if args.suite == "requirements":
        results = rs.run_suite(args.mode, runs, ids, live_client, model_name)
        print(rs.format_report(results, args.mode))
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(results, fh, indent=2)
            print(f"\nFull results saved to {args.out}")
        return 0 if results and sum(r["passed"] for r in results) / len(results) >= rs.TARGET else 1
    results = run_all(ids, args.mode, runs, live_client, model_name)
    print(format_report(results, args.mode))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"\nFull results saved to {args.out}")
    return 1 if any(r["violations"] or r["error"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
