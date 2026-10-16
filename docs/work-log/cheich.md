# Cheich work log

## 2026-10-14: agent loop (branch cheich/agent-loop)
Done
- `agent/decide.py`: one model call returns tool calls, a text reply, or an error. Never raises on API errors, empty or cut-off output, missing tool-call ids.
- `agent/loop.py`: `run_turn` runs once per traveler message. Step limit (default 8), tool errors and unknown tool names are fed back to the model, turn ends when the model replies with text (including a question). On error the history is left unchanged.
- `agent/stub_tools.py`: STUB tools with fixed fake data built from `contract/models.py` (unchanged). Tool input fields are stub-only guesses. Replace with Jian's `tools/registry.py` when ready.
- `tests/unit/agent/test_loop.py`: 10 tests with a fake client, no network. Run: `.venv/bin/python -m pytest backend/tests/unit/agent`

Not done / handoff
- `prompts/system_prompt_v0.txt` saved word for word from PRD 3b (no separate file was provided).
- No live Anthropic call has been made.
- `tests/unit/agent/` is not in the CLAUDE.md or CODEOWNERS ownership lists; add it.
- Requirement extraction (decide.py in TASKS.md) is a separate task and is still open.

### Switching from mock to Jian's real tools
- `agent/stub_tools.py` now holds mock data for the 4 PRD eval cases (`MOCK-CASE-1` to `MOCK-CASE-4`). No limits filtering yet: the harness limits filter is not built.
- `agent/tool_source.py` is the one switch: `get_tool_source("stub", scenario="case_2")` or `get_tool_source("real")`. `loop.py` is unchanged.
- ASK FOR JIAN: `backend/app/tools/registry.py` should define `TOOLS` (tool name -> function taking keyword arguments, returning a dict) and `TOOL_SCHEMAS` (Anthropic tool definitions) for the 4 tools. Details are in the `tool_source.py` docstring.
- Check once ready: `.venv/bin/python -m pytest backend/tests/unit/agent -rs`. The `real` test is skipped until the registry exists, then it checks the fit automatically.

### Rebooking confirmation (mock fallback)
- `harness/confirmation.py`: `ConfirmationGate`. Only a prepared (validated) option can be confirmed; the option is re-checked first and changed details need a new confirmation; repeat or uncertain attempts are never re-run; the mock completer accepts only mock options. The model has no tool to book.
- `agent/stub_tools.py`: `build_stub_completer` is the MOCK completion (simulated confirmation, no real ticket). TODO: the contract has no confirmation model yet.
- ASK FOR JIAN: `registry.py` also needs `complete_rebooking(booking_id, option_id) -> dict` (completes after confirmation, routes by option source, raises on failure). Swap is `get_tool_source("real")`; the gate is unchanged.
- Tests: `tests/unit/harness/test_confirmation.py` (7). Whole suite: `.venv/bin/python -m pytest backend/tests/unit -rs`.

### Eval cases
- The 4 PRD eval cases are in `backend/tests/evals/cases/` as JSON (setup, expected behavior, must-not lists). Expected behavior was written before any run.
- Not done: no automated runner yet; they were checked by hand in the live chat only.

## 2026-10-15: guards (branch cheich/guards)
Done
- `harness/guards.py`: `check_option_known` blocks an option whose eligibility, additional cost or currency is unknown or invalid (zero cost is known, not unknown). `wrap_untrusted` labels every tool result as data and flags text that looks like instructions (eval case 4).
- `agent/loop.py`: every successful tool result now goes through `wrap_untrusted`.
- `harness/confirmation.py`: an option with unknown eligibility or cost can no longer be prepared or confirmed.
- `tests/unit/harness/test_guards.py`: 19 tests. Whole suite: 42 pass, 1 skipped (Jian's real tools).
- Ticked the confirmation gate in TASKS.md. README: kept Jian's version (his branch rewrites it); my friendlier draft is not committed.

Not done / notes
- The injection detector is a phrase list, a seatbelt only. Real protection is that code enforces limits and confirmation.
- Allowed eligibility values are still undefined in the contract; guards treat missing, empty and "unknown" as unknown. Update when settled.
- Not yet checked live: whether the model really ignores the flagged field in case 4 (try `live_chat.py case_4`).

## 2026-10-15: decide.py cut-off fix (branch cheich/decide-cutoff, based on cheich/guards)
Done
- `decide.py`: default `max_tokens` raised from 1024 to 4096 (`DEFAULT_MAX_TOKENS`). A text reply that stops with `max_tokens` is now flagged `truncated`.
- `loop.py`: a cut-off reply is continued automatically with an app-written "continue" message, up to `MAX_CONTINUATIONS` (2) times. The traveler sees the parts joined. If it is still cut off after that, the turn is an error and history is unchanged. Each continuation counts toward the step limit.
- Tests in `tests/unit/agent/test_loop.py` (3 new). Suite: 45 pass, 1 skipped.

Notes
- Raised from Jian's handoff: a live reply was cut off mid-sentence ("If the…") because only tool calls were checked for `max_tokens`.
- Not checked live: whether the model continues cleanly mid-word. Check with `live_chat.py` on a long answer.
- This branch sits on top of `cheich/guards`, so merge that one first.

## 2026-10-15: gate says what changed (branch cheich/decide-cutoff)
- `harness/confirmation.py`: when the re-check finds a changed or unavailable option, the rejection reason now ends with `What changed: ...` built from the re-check's `changes_to_review`. Before, that list was dropped and the traveler was only told the option was no longer valid (Jian's handoff gap).
- Chosen approach: reason text only. The change list is not stored for the confirm card; if the UI needs it, that touches Jian's API code.
- 3 new tests in `test_confirmation.py`.

## Handoff for Jian (2026-10-15)
Where things stand
- Merged earlier (PR #4): system prompt v0, agent loop, mock tools and swap switch (`agent/tool_source.py`), confirmation gate, 4 eval cases.
- Branch `cheich/guards` (pushed, no PR yet): guards block options with unknown eligibility, cost or currency, and label tool data as untrusted (eval case 4).
- Branch `cheich/decide-cutoff` (pushed, no PR yet, sits on top of `cheich/guards`, merge that first): `decide.py` raises max_tokens to 4096 and continues a cut-off reply up to twice; the gate's rejection now says what changed (your `changes_to_review` gap).
- I tested your branch locally: 364 tests pass, 1 fails. I posted this and my answers on PR #5.

What I need from you
1. PR #5: why does `test_a_duffel_rebooking_confirms_once_through_the_gate_and_the_api` fail for me (`prepare_rebooking` returns `unavailable`)? Date or offer expiry? I'll approve and merge once it is sorted (GitHub requires my approval).
2. Agree to my answers on PR #5: you own the shell, I own `frontend/src/features/chat`; `react-router` only; dev panel behind a flag, test token only, never in a public demo.
3. Add the frontend split and `tests/unit/services/`, `tests/unit/api/` to CLAUDE.md and CODEOWNERS.
4. Review my two PRs once opened (approvals needed on both; `TASKS.md` may need a small manual merge since we both edited it).
5. Eval runner: OK with free mode (scripted replies, tests your six fault switches, no cost) plus live mode (claude-haiku-5-5, only when asked, runs chosen each time)? Pass/fail by code checks, not a second model. I will not build it until you answer.
6. A session to settle the contract TODOs (arrival window, eligibility and validity values, flight_details, money type, confirmation result). They block the limits filter.
7. After the README merges: I will add out of scope, role and industry, and how to run it. README is shared, so I need your approval.

My next steps after PR #5 merges: pull main, limits filter hook, `confirmed_needs` injection, harness tests, eval runner, automated checks, chat UI.

## 2026-10-15: automated safety checks (branch cheich/safety-checks)
Done
- `tests/unit/harness/test_safety_checks.py` (15 tests, no live model) runs my guards, gate and loop against Jian's real `MockService` and its fault switches: guard allows every normal mock option (no false positives); `unknown_eligibility` blocked by guard and gate; `unavailable_option` never confirmed; `tool_failure` reaches the model as an error and the turn continues; case 4's injected `note` is flagged in the real mock data, and normal data is not flagged.
- The status strings Jian's mock uses (`unknown`, `ineligible`, `unavailable`) match what the guard checks.

Known gap (needs a decision)
- Wrong currency is NOT caught. The guard only checks that a currency exists. Nothing compares it to the traveler's budget currency, and contract `Limits` and `TripContext` have no currency. Recorded as a strict `xfail` test, so it fails loudly once someone fixes it. Fix needs a contract change (expected currency) agreed with Jian. PRD target: 100% of displayed costs match the service.

Covered elsewhere (Jian's `test_registry_with_gate.py`): confirm without prepare, wrong option, repeat confirm, changed cost, failure inside completion, another session's booking.

## Update for Jian (2026-10-16), in plain words
What I did
- I pulled your merged work (PR #5) into my copy and checked I have everything: Python packages, frontend packages and the frontend build all work.
- My three older branches were started before your merge, so I made one fresh branch from the new `main`: `feat/guards-and-cutoff`. It has your work plus all of mine, and it is pushed. There is no PR yet, so nothing is merged. None of your files are changed.
- What is in it: guards (options with unknown eligibility or cost are blocked, and tool text that looks like instructions is flagged), the fix for replies cut off mid-sentence, the confirmation gate now tells the traveler what changed, and new safety checks that run against your mock fault switches.
- I set my git name and email for this repo. Five older commits still show "Your Name"; I left them, because fixing that would mean rewriting history and I won't force-push.
- I added `MODEL` to my local `.env` (not committed) so the chat can run locally.

Tests
- 402 pass and 1 is an expected failure (the wrong-currency gap below).
- 2 fail, and both are yours: `tests/unit/api/test_changes.py::test_a_new_change_is_returned_once_and_updates_the_booking` and `tests/unit/api/test_duffel_api.py::test_a_duffel_rebooking_confirms_once_through_the_gate_and_the_api`. They fail on plain `main` too, so my changes did not cause them. They look tied to today's date: on Oct 16 the first one expects `2026-10-16` but gets `2026-10-17`, and the second gets `unavailable` from `prepare_rebooking` instead of `valid` (same as I flagged on PR #5). Could you look?

What I need from you
1. A look at those two date-based tests.
2. A review when I open the PR for `feat/guards-and-cutoff`.
3. Still waiting on: the eval runner question (free mode and live mode?), a session on the contract fields, and the `CLAUDE.md` and `CODEOWNERS` updates (frontend split, your new test folders).

New thing to decide together
- Wrong currency is not caught. If an option is priced in EUR and the budget is in USD, nothing notices. The contract has no currency on `Limits` or `TripContext`, so this needs a contract decision. It is recorded as an expected failure in `tests/unit/harness/test_safety_checks.py`.

## 2026-10-16: merged main (contract v1) and updated the guards (branch feat/guards-and-cutoff)
Done
- Merged `main` (Jian's PR #6, contract v1) into this branch with a normal merge, no rebase, so no force-push is needed. No conflicts; the suite is 476 passed plus 1 expected failure.
- `harness/guards.py`: eligibility is now the contract's three values. `unknown` and `ineligible` block, `eligible` passes, and anything missing or outside the contract is treated like unknown (blocked). Removed the old value lists and the TODO about allowed values. Costs are never negative (matches the contract).
- Removed two answered TODOs on `validation_result` values (`confirmation.py`, `stub_tools.py`). Kept two that are still true: the contract has no confirmation model, and confirmed needs for escalation still come from the model, not the harness.

Still open
- Wrong currency is still not caught by the guard. The contract now has `Limits.currency`, so the limits filter can compare it with each option's currency (an option in another currency cannot be checked and must not be recommended). That filter is the next task.
