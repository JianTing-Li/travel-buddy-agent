# Jian work log

## 2026-10-15: airline-change check, mock extras, dev panel and the Duffel path (branch feature/duffel-client)
Done
- Airline-change check: `POST /bookings/{id}/changes/check` is application code (not the agent). It returns each change once per session (ids are remembered) and queues an `[App notice]` for the agent's next turn. The open booking page polls it every 8 seconds and shows a banner. Shared `AirlineChange` model in `services/airline_change.py`.
- Mock extras: six fault switches (`unknown_eligibility`, `wrong_currency`, `unavailable_option`, `changed_details`, `tool_failure`, `uncertain_completion`) that change what the mock reports, never its data; delay and cancellation simulation; runtime bookings; a seeded generator (`services/mock/generator.py`, same seed gives the same booking, or an eval case under a new id).
- Dev endpoints (`/dev/bookings`, `/dev/bookings/{id}/disrupt`, `/dev/bookings/{id}/faults`, `/dev/duffel-bookings`) exist only when the app is created with `dev=True`: `uvicorn backend.app.api.main:dev_app --no-access-log`. The UI dev panel needs `VITE_DEV_PANEL=true`. Both are test tools, not traveler features, and not in the PRD.
- Duffel path: `DuffelService` (`services/duffel/service.py`) has the same methods as `MockService` for Duffel TEST orders. `ord_...` ids route to it and `MOCK-...` ids to the mock, in the router, tools, sessions and API; an option's `data_source` must match its booking's service, so a mock option never reaches Duffel. Shared errors and checks moved to `services/errors.py` and `services/validation.py`.
- Verified live with the real model and Duffel's test API: create a test order, poll (no stray changes), simulate a change, search, prepare, confirm (a repeat is refused), status becomes rebooked. 365 backend tests pass; frontend build and lint pass.

Handoff for Cheich
- `get_tool_source("real")` now serves both sources. A Duffel booking is created from the dev panel; the agent's tools, your gate and `/confirm` work the same for it.
- The gate treats a dropped connection while completing as pending; for Duffel that is the `DuffelTransportError` (not a `ServiceError`), and the mock's `uncertain_completion` fault produces the same case for your automated checks. Faults can be set per mock booking with `POST /dev/bookings/{id}/faults` (or `MockService.set_faults`).
- Reminders still open on your side: the gate drops `changes_to_review` on a changed option, the `max_tokens` cut-off in `decide.py`, the limits filter hook (`build_tools(limits_filter=...)`), and `confirmed_needs` injection for `escalate_to_support`.
- Mapping rules for Duffel (eligibility, validity, cost) are provisional until we agree the contract models; they are in one place (`services/duffel/service.py`) with the allowed values in `services/mock/provisional.py`.

Not done
- Contract models are still a DRAFT; frontend ownership, the router (`react-router`), and the dev panel scope are still to agree (see TASKS.md).
- Deployment items (in-memory sessions need one worker or a store), a Duffel airline-change accept through the app, and the `PATCH` update.
- Duffel offers are all one flat cost and the same few departure times, so the cost and arrival cases of the evals still use mock data.

## 2026-10-15: API and types.ts (branch feature/duffel-client)
Done
- `api/`: FastAPI app. `POST /sessions` (random session id, per-session MockService, tools and gate), `GET /bookings`, `GET /bookings/{id}`, `POST /chat` (runs your `run_turn`), `POST /confirm` (your `ConfirmationGate`). Every call except `/sessions` and `/health` needs the `X-Session-Id` header; a booking outside the session gets the same 404 as an unknown one. Logs hold only request id, method, route template, status and duration; unexpected errors return a generic 500. CORS allows only the Vite dev server. In-memory sessions: restart drops them, idle sessions expire after 12 hours, at most 200.
- `frontend/src/app/types.ts`: mirrors the contract models and API schemas, plus `ChatSlotProps` (bookingId, messages, sending, onSend) as the chat component's interface. A backend test (`tests/unit/api/test_types_ts.py`) fails if field names drift. `npm run build` passes.
- Live check with claude-haiku-5-5: two real chat turns worked end to end; the model loaded the booking, said it was simulated, and asked clarifying questions. No confirm card was reached yet.

Handoff for Cheich
- `decide.py`: a live reply was cut off mid-sentence ("If the…"). `max_tokens` is 1024, and a text reply that stops with `max_tokens` is returned as if complete (only tool calls are checked). Haiku writes long replies, so this will happen. Suggested: raise the limit and treat a `max_tokens` stop on a text reply as an error or ask for a continuation.
- The chat endpoint prepends `[App notice]` lines to the next traveler turn after each `/confirm` (confirmed, rejected or pending), so the agent only reports what the application did. Booking id reaches the model through an app-written line in the system prompt, not the traveler's text. History is kept per booking per session.
- `/confirm` is the traveler's explicit confirmation (the UI button); the model has no tool for it. The confirm card comes from the latest `prepare_rebooking` result, shown only when `validation_result` is `valid`.
- Chat slot proposal (needs your OK): your chat component receives `ChatSlotProps` from `types.ts`. I own the shell and the API calls; you own `features/chat`.
- Still open from the earlier handoff: the gate drops `changes_to_review` on a changed option, and limits filter / `confirmed_needs` injection need your harness.

Not done
- UI shell, dev endpoints and panel, airline-change check, Duffel path, mock fault modes (see TASKS.md).

## 2026-10-15: mock service and tool registry (branch feature/duffel-client)
Done
- `services/mock/`: scenario files for the 4 eval cases in `data/mock/scenarios/` (times are local with a day offset from today, so they never go stale), a validating loader (`scenarios.py`), and `MockService` (`mock_service.py`): trip context, replacements (all options, no limits filtering), prepare with changed-detail reporting, simulated completion once per booking, and simulated escalation. Duffel-looking ids are rejected. Provisional status values live only in `provisional.py` until the contract defines them.
- `tools/`: the four tools, `access.py` (per-session booking access and source routing) and `registry.py`. `build_tools(service, allowed_booking_ids, limits_filter)` builds a tool set per session. Module-level `TOOLS`, `TOOL_SCHEMAS` and `complete_rebooking` use all mock bookings, so `get_tool_source("real")` works and Cheich's real-tools test now passes.
- Tests: `tests/unit/services/mock/` (scenarios and service), `tests/unit/tools/test_registry.py` (tools) and `tests/unit/tools/test_registry_with_gate.py` (registry driven through the real `ConfirmationGate`, no live model). 138 unit tests pass.

Handoff for Cheich
- `get_tool_source("real")` now works: `TOOLS`, `TOOL_SCHEMAS`, `complete_rebooking` as in the `tool_source.py` docstring. The API should call `build_tools(...)` per session with only that session's booking ids; a booking outside the set gives the same error as an unknown one.
- Limits: `search_replacements` returns every option with `limits_checked_by_code: false`. Plug your filter in with `build_tools(limits_filter=fn)` where `fn(options: list[Option], limits: dict) -> list[Option]`; the flag turns true when it runs.
- `escalate_to_support` needs `confirmed_needs` with all four `Limits` fields, supplied by the model for now. The model cannot escalate before limits are confirmed. Better: the harness injects the confirmed needs per session.
- GAP IN `harness/confirmation.py`: when an option changes between prepare and confirm, the gate's re-check sees `changes_to_review`, then discards it and only says "The option is no longer valid. Review another option." The next `prepare_rebooking` returns `valid` with an empty `changes_to_review` (the change was already reported once) and the new price. The old confirmation is voided and a new one is required, so it is safe, but the traveler is never told what changed. Suggested fix: put the re-check's `changes_to_review` into the rejection reason.
- The gate treats any exception from `complete_rebooking` as pending. In the tests a failure inside completion shows as pending and is not retried, and already-rebooked is caught by the re-check as rejected.
- Tool errors reach the model as `Tool '...' failed: ToolError: <message>` through your loop. The case 4 injected text is returned only inside `flight_details.note`; it is not marked untrusted by the tools, so that guard stays with `harness/guards.py`.
- `stub_tools.py` can go once you switch. The scenario ids and numbers match your stubs.

Not done
- Source tagging stays open: only mock bookings are wired, and Duffel ids return "not supported yet". The Duffel path needs the Duffel-to-contract mapping, which waits on the contract models.
- Mock fault modes (unknown eligibility, wrong currency, option changes by itself, tool failure), booking store, disruption simulator and seeded generator.
- FastAPI chat and confirm endpoints, dev endpoints, `types.ts`, and the UI shell.
- Contract models are still a DRAFT; the provisional values are in `services/mock/provisional.py`.

## 2026-10-15: Duffel follow-up, correcting the 2026-10-14 notes (branch feature/duffel-client)
Done
- The 2026-10-14 notes said Duffel test mode cannot simulate an airline-initiated change. That was wrong: Duffel's "Test your integration" page lists a trigger. Create an order on the one-way route LHR to LTN, then list changes for it.
- `probe.py` now has `--scenario airline-change|connections|price-change|expired-offer|all` (needs `--create-orders`; `--confirm-change` also tries accept). `docs/duffel-notes.md` is corrected and has the new results.
- Verified: the fake change is a one-hour delay (removed time T, added time T+1h), not a cancellation. Every list call on that order creates another change, so listing is not read-only there. Accept works for the latest change only (older: `stale_airline_initiated_change_accept`). There is no single-change GET (404). Price changes on LHR to STN: a stale amount is rejected at order time (`payment_amount_does_not_match_order_amount`), the latest amount works. LHR to DXB replacement offers were nonstop, not connecting.
- `client.py`: added `accept_airline_initiated_change(change_id)`, with 2 more tests (43 tests pass, 1 skipped).
- Still untested: `PATCH` update and the cancel and change actions on airline-initiated changes, any airline-initiated change off the LHR to LTN route, whether the order's own departure time moves after accept.

Impact on the plan
- The "simulate disruption" dev button can use Duffel for LHR to LTN bookings (a one-hour delay only). Cancellations, missed flights and the eval-case arrival times and costs still need the mock service.
- A poller for airline changes must track change ids it already showed, because each list call on the LHR to LTN route creates a new one.

## 2026-10-14: Duffel test API probe and client (branch feature/duffel-client)

## 2026-10-14: Duffel test API probe and client (branch feature/duffel-client)
Done
- `services/duffel/probe.py`: re-runnable script that checks which Duffel test-mode calls work. Needs a `duffel_test_` token (refuses anything else). Flags: `--create-orders` (test orders and pending changes), `--confirm-change` (confirm, duplicate confirm, second change). Prints only status codes, error fields, field names and a few allow-listed facts.
- `docs/duffel-notes.md`: verified results from the probe. Works: search, create test order (1 and 3 passengers), get order, list airline-initiated changes (always empty), order change request, offers, pending change, confirm. Airline-initiated changes were first reported untested; corrected on 2026-10-15 above.
- `services/duffel/client.py`: sync `httpx` client for the calls that worked. Returns Duffel's data unchanged, tagged `data_source: "duffel"`. Test tokens only. Never retries. `DuffelApiError` (status, type, code) and `DuffelTransportError` (flags whether the request may have reached Duffel). `contract/models.py` is unchanged.
- `tests/unit/services/duffel/test_client.py`: 18 tests with a mocked transport, no network. Run: `.venv/bin/python -m pytest backend/tests/unit -rs`.

What the notes found that affects the rest of the build
- Additional cost is `change_total_amount`, not `new_total_amount`. Duffel Airways returned one flat cost (125.00 USD) for 1 and 3 passengers, so per-passenger vs whole-booking could not be told apart.
- Confirming a positive change needs a `payment` object (`balance`, the pending change's own amount and currency); without it Duffel returns 422.
- Duffel rejects a repeat confirm (`order_change_already_confirmed`). A test order can be changed once; a second change returns `order_not_changeable`.
- Duffel has no eligibility field. The harness must decide how `available_actions`, `conditions.change_before_departure.allowed` and the presence of offers map to eligibility; unknown must block rebooking.
- The mock service must cover: cancellations, missed flights (Duffel can only simulate a one-hour delay on LHR to LTN), controlled arrival times and cost spreads (eval cases 1-4), embedded instructions. Duffel test offers were three departure times, all nonstop.

Not done / handoff
- Tools (`get_trip_context`, `search_replacements`, `prepare_rebooking`, `escalate_to_support`) and `tools/registry.py` are still open. Cheich needs `TOOLS`, `TOOL_SCHEMAS` and `complete_rebooking(booking_id, option_id)`; tools are sync, matching the client.
- The client does no mapping to `Option` / `TripContext`. That belongs in the tools, with the mapping rules for eligibility and validity still to be agreed (the contract models leave them as TODO).
- Airline-change polling while the app is open: list and accept exist (see 2026-10-15); polling must track change ids already shown.
- Mock service and its scenarios: not started.
- `tests/unit/services/` is not in the CLAUDE.md or CODEOWNERS ownership lists; add it.
