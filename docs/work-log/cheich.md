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

## 2026-10-16: limits filter (branch cheich/limits-filter, from main with contract v1)
Done
- `harness/limits.py`: `limits_filter(options, limits)` is the hook for `build_tools(limits_filter=...)`. An option stays only if it is eligible and valid, arrives at or before `Limits.arrive_by` (real moments in time, so time zones work; arriving exactly at the deadline is allowed), is within the budget, and has no more connections than allowed. Cost is compared ONLY when the option's currency equals `Limits.currency`; an option in another currency is removed, so the wrong-currency gap is closed at the search step.
- Fails closed: missing, incomplete or invalid limits remove every option; an unreadable option is removed, never a crash.
- `exclusion_reasons(options, limits)` returns why each option was removed. The tool hook only returns survivors, so the agent cannot yet be told which limit failed; for now it explains conflicts itself. Asking Jian to return the removed options and reasons is a later improvement.
- `tests/unit/harness/test_limits.py` (28 tests): each rule, time zones, boundaries, bad limits, plus the PRD eval cases 1 to 4 run through Jian's real `search_replacements` and mock data (case 1 drops the 4 PM option; case 3 returns nothing at $0, then only the $120 option at a $150 budget; case 4's hidden-instruction option never reaches the model).
- Self-contained: it does not import the guards, so this branch does not depend on the unmerged guards PR.

Not done / for Jian
- The live app does not use it yet. `api/sessions.py` line 115 builds the tools without `limits_filter`; adding `limits_filter=limits_filter` there is a one-line change in Jian's file.
- If the model calls `search_replacements` without `limits`, Jian's tool returns every option with `limits_checked_by_code: false` (the filter is only called when limits are given). The agent should never recommend from an unchecked result; the tool could refuse to search without limits.
- `passenger_count` is validated but not compared: options carry no passenger count.
