# Jian work log

## 2026-10-14: Duffel test API probe and client (branch feature/duffel-client)
Done
- `services/duffel/probe.py`: re-runnable script that checks which Duffel test-mode calls work. Needs a `duffel_test_` token (refuses anything else). Flags: `--create-orders` (test orders and pending changes), `--confirm-change` (confirm, duplicate confirm, second change). Prints only status codes, error fields, field names and a few allow-listed facts.
- `docs/duffel-notes.md`: verified results from the probe. Works: search, create test order (1 and 3 passengers), get order, list airline-initiated changes (always empty), order change request, offers, pending change, confirm. Untested: get, accept and update of an airline-initiated change, because test mode never produced one.
- `services/duffel/client.py`: sync `httpx` client for the calls that worked. Returns Duffel's data unchanged, tagged `data_source: "duffel"`. Test tokens only. Never retries. `DuffelApiError` (status, type, code) and `DuffelTransportError` (flags whether the request may have reached Duffel). `contract/models.py` is unchanged.
- `tests/unit/services/duffel/test_client.py`: 18 tests with a mocked transport, no network. Run: `.venv/bin/python -m pytest backend/tests/unit -rs`.

What the notes found that affects the rest of the build
- Additional cost is `change_total_amount`, not `new_total_amount`. Duffel Airways returned one flat cost (125.00 USD) for 1 and 3 passengers, so per-passenger vs whole-booking could not be told apart.
- Confirming a positive change needs a `payment` object (`balance`, the pending change's own amount and currency); without it Duffel returns 422.
- Duffel rejects a repeat confirm (`order_change_already_confirmed`). A test order can be changed once; a second change returns `order_not_changeable`.
- Duffel has no eligibility field. The harness must decide how `available_actions`, `conditions.change_before_departure.allowed` and the presence of offers map to eligibility; unknown must block rebooking.
- The mock service must cover: cancellations and airline-initiated changes, missed flights, controlled arrival times and cost spreads (eval cases 1-4), embedded instructions. Duffel test offers were three departure times, all nonstop.

Not done / handoff
- Tools (`get_trip_context`, `search_replacements`, `prepare_rebooking`, `escalate_to_support`) and `tools/registry.py` are still open. Cheich needs `TOOLS`, `TOOL_SCHEMAS` and `complete_rebooking(booking_id, option_id)`; tools are sync, matching the client.
- The client does no mapping to `Option` / `TripContext`. That belongs in the tools, with the mapping rules for eligibility and validity still to be agreed (the contract models leave them as TODO).
- Airline-change polling while the app is open: only the list call exists to build on; fetching and accepting a change are untested.
- Mock service and its scenarios: not started.
- `tests/unit/services/` is not in the CLAUDE.md or CODEOWNERS ownership lists; add it.
