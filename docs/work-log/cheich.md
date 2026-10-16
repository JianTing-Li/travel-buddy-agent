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

## 2026-10-16: chat UI (branch cheich/chat-ui)
Done
- `frontend/src/features/chat/`: `ChatPanel.tsx` (message list, "working on it" indicator, input that sends on Enter and adds a line on Shift+Enter, Send disabled while empty or sending, welcome text with three tap-to-edit example prompts), `RichText.tsx` and `markdown.ts` (a small safe formatter for bold, italic, code, bullet and numbered lists; builds React elements only, never raw HTML; links and tables stay plain text), `chat.css` (uses the shell's colour variables, so light and dark both work).
- `app/ChatSlot.tsx` (Jian's file): body replaced with `<ChatPanel {...props} />`, the one-line hand-over its own comment describes. The shell, `ChatSlotProps` and `types.ts` are unchanged. No new packages.
- Checked: `npm run build` and `npm run lint` pass; formatter logic checked with 13 cases in Node; run against the live backend and real model (Case 1): send, thinking state, formatted reply, Shift+Enter, light mode, phone width (375px, no sideways scroll).

Not done / notes
- No automated frontend tests: the project has no test framework (adding Vitest would need Jian's agreement).
- Assistant replies are only as structured as the model writes them. The structured comparison cards in TASKS.md need the limits filter.
- The first real reply asked three or four questions at once; that is the prompt's behavior, not the UI.
- Full flow checked live (Case 1, real backend and model, mock data): the agent loaded the booking, asked for the deadline, found two options inside the limits and left out the 4 PM flight, prepared the 2 PM nonstop, and the shell showed the confirm card. Pressing Confirm rebooking set the booking to Rebooked with SIM-CONF-MOCK-CASE-1-opt-1a; a follow-up question was answered from the app's result and stayed labeled simulated.
- Finding: before the card was pressed the agent said 'reply yes to confirm', but confirmation is the button, not a chat message. A prompt or app-notice wording fix, to agree with Jian.
- Finding: the agent filtered the 4 PM option itself and said the service had not checked the limits. The limits filter (harness/limits.py) is still not built, so this relies on the model's own judgment.
- Not tried live: the `wrong_currency` fault in the dev panel.
