# Tasks

Status: [ ] todo · [~] in progress · [x] done. Update in the same PR as the work.

## 0. Setup (Shared)
- [~] Scaffold repo (branch setup/scaffold): backend/, frontend/, CODEOWNERS, docs
- [x] Contract v1 for backend/app/contract/models.py: deadline arrive_by, budget currency, allowed values, typed flight details, itinerary, passengers and disruption (decided 2026-10-16; either owner may change it)
- [x] Frontend ownership: Jian owns frontend/ except features/chat/, which is Cheich's (CLAUDE.md, CODEOWNERS)
- [ ] Decide: UI scope for MVP 1 and deadline

## Cheich: agent and harness
- [x] System Prompt v0 from PRD 3b (agent/prompts/)
- [x] Tool-use loop with Claude (agent/loop.py), tested with stub tools (agent/stub_tools.py)
- [x] Requirement extraction: required limits vs preferences, clarifying questions. Code rule (harness/requirements.py, enforced in agent/loop.py) refuses a search unless all five required limits are present and valid; prompt v1 adds the ask-first and floated-budget rules; scored by tests/evals/requirements_suite.py on 9 cases: 25 of 27 live runs correct (93%), PRD target 90% met
- [x] Limits filter: budget, arrive_by, connections (harness/limits.py), plugged into the live session tools (api/sessions.py, one line) and tested with the 4 PRD scenarios; a search without complete limits is now refused by the requirement check
- [x] Explicit-confirmation gate and duplicate-attempt tracking (harness/confirmation.py), mock completer for now. Strict mode is ON in the live app (api/sessions.py, 2026-10-16): nothing can be prepared or confirmed before a search checked by code has confirmed the limits
- [x] Guards: untrusted tool content, block rebooking when eligibility or cost unknown (harness/guards.py)
- [x] Unit tests for harness: 99% line and branch coverage of harness/ and agent/ (measured with coverage, installed locally only); every safety rule has tests
- [x] Eval cases 1-4 from PRD 3d (tests/evals/cases/) and the eval runner (tests/evals/runner.py): scripted mode is free and repeatable and tests the code around the model; live mode uses the real model, you choose --runs N. Judged by code only. Live results against the PRD 2c metrics are not collected yet
- [x] Automated checks: unknown eligibility, wrong cost/currency, unavailable option, changed details, tool failure, duplicates, other traveler's booking, mock/Duffel mixing. Mine: tests/unit/harness/test_safety_checks.py, test_gate_limits.py and the runner's bad-agent tests; changed details, duplicates, other booking and mock/Duffel mixing are also covered by Jian's gate tests

## Jian: tools, services and API
- [x] Find what Duffel's test API supports; record in docs/duffel-notes.md
- [x] Duffel client (services/duffel/client.py)
- [x] Duffel follow-up: LHR to LTN airline-initiated change scenario (Duffel docs "Test your integration"), fetch/accept calls, LHR to DXB connections and LHR to STN price-change routes; correct docs/duffel-notes.md and extend the client if they work (proposed)
- [x] Mock service + scenarios for the 4 eval cases (services/mock/, data/mock/scenarios/); fault modes for the automated checks are in `MockService.set_faults`
- [x] Mock booking store, disruption simulator, seeded generator and fault modes, labeled simulated (services/mock/) (proposed)
- [x] Tools: get_trip_context, search_replacements, prepare_rebooking, escalate_to_support, plus registry (mock and Duffel test bookings)
- [x] Source tagging so each option uses its matching validation and confirmation service (booking id routes to the mock or Duffel service; option data_source must match)
- [x] FastAPI app: chat and confirm endpoints, booking access check, log redaction (api/main.py); sessions are in memory
- [x] Dev/booking endpoints: generate test booking (seeded scenarios, Duffel test order), simulate disruption, set faults, reset this session's test data; only with dev_app, scoped to the session (api/) (proposed)
- [x] Richer generated booking options (3 to 5 per booking, always a $0 option that leaves later, pricier earlier options, a one-connection option and a nonstop one; services/mock/generator.py)
- [ ] Optional experiment: book a real airline's Duffel sandbox offer (e.g. British Airways) in test mode and check whether its order-change offers vary in cost and time, unlike Duffel Airways' flat 125 USD. Airline sandboxes can be down or out of seats, so results may not be repeatable; record findings in docs/duffel-notes.md
- [x] Airline-change check while the app is open (PRD "Application responsibilities"); polls every 8 seconds, mock and Duffel
- [x] Unit tests for tools
- [x] frontend/src/app/types.ts mirroring the contract models (and the API schemas)

## UI shell (extra, proposed: needs agreement before starting; Jian shell, Cheich features/chat)
- [ ] Agree: booking summary type for the list page, chat-slot interface (messages in, onSend out), dev panel in MVP 1 scope (frontend ownership is settled; react-router moved to Future improvements)
- Design decided by Jian (Cheich to confirm): plain CSS with CSS variables, light and dark mode, app name "Travel Buddy", persistent "Simulated environment" badge, source pill (Duffel test or Mock) on every booking
- [x] Shell built on fixtures typed by types.ts: bookings list, booking detail with disruption banner, confirm card with simulated label, placeholder where the chat goes
- [x] Dev panel: generate test booking (seeded scenario picker, Duffel test order) and simulate disruption, labeled simulated; shown only with VITE_DEV_PANEL=true
- [x] Wire the shell to the real API once the chat/confirm and dev/booking endpoints exist
- [x] UI polish from a design review: booking cards with city names, time, airline and action; recovery workspace layout; conversation and airline-change banners kept across navigation; "Checking your rebooking" state for uncertain confirmations; plain-language footer
- [ ] Structured comparison: up to three flight cards from validated tool results with a reason derived from code facts (needs an API addition and Cheich's limits filter), editable requirement chips fed by the agent's confirmed limits, progress stepper, no-options screen. Not a requirements form: the PRD has the agent capture needs from everyday language
- [x] Cheich's chat plugs into the chat slot (features/chat: messages, thinking indicator, example prompts, safe formatting; checked in the browser, light and dark, phone width)
- [x] Booking page layout: full-width flight card on top (new flight leads after a rebooking, original shown as replaced), full-width chat with the confirm card above the input; one app-wide "Simulated environment" label, source pills in dev mode only
- [x] Errors and outages: a message that gets no answer shows an app notice (can't reach the server, assistant unavailable, too slow) with Try again, never a fake reply; after two failures it points to the airline with the booking ref. Model calls time out after 45 s (one retry); requests time out in the browser. Loading skeletons on the list and booking pages
- [x] Dev panel rework: add a generated booking that is on time, canceled, delayed or missed (or a PRD case), a Duffel test booking, "Back to normal" per mock booking (clears changes, faults, rebooking and chat), plain-language fault names. Default sessions also start with two on-time bookings (MOCK-ONTIME-1 and -2)

## Deployment (later, after the demo; proposed)
- [ ] Decide hosting (Vercel alone is not enough for this project; it needs two services): backend on a long-running host (Render, Railway or Fly) with ONE worker (`--workers 1`), frontend on Vercel or Netlify. Sessions, chat history, the confirmation gate and mock state live in memory, so serverless functions or several workers would lose them between requests. The alternative is moving that state to Redis or a database (a feature of its own, not in the PRD)
- [ ] Set the same variable names in the host's dashboard as secrets (ANTHROPIC_API_KEY, DUFFEL_ACCESS_TOKEN, MODEL; Duffel must stay a `duffel_test_` token). `.env` is not deployed and `load_dotenv` does not override real environment variables
- [ ] Make the allowed CORS origin configurable for the deployed frontend URL (needs one new env var such as ALLOWED_ORIGINS, or a deploy entry point passing `allowed_origins` to `create_app`; CLAUDE.md allows only three env var names, so agree first and update .env.example, which Jian owns)
- [ ] Frontend: read the API address from a build-time `VITE_API_URL` (public, never put keys in it); add a rewrite-all-to-index.html rule (`vercel.json` or Netlify `_redirects`) if react-router is used
- [ ] Check the host offers Python 3.14 (CLAUDE.md) BEFORE choosing it, or agree an older version with Cheich. Start the backend with `--no-access-log` and with `backend.app.api.main:app`, never `dev_app` (its /dev endpoints create test orders and must not be public)
- [ ] Public demo protection: anyone with the link can use the Anthropic key through POST /chat and create Duffel test orders. Before sharing a live URL add a simple guard (a shared access code the page sends, plus a per-session and per-IP rate limit and a cap on chat turns), and set a spending limit on the Anthropic key. Nothing like this is built yet

## Future improvements (not MVP 1)
- [ ] react-router: replace the small hash router (`frontend/src/app/route.ts`, URLs like `#/bookings/ID`) with react-router for clean URLs (`/bookings/ID`), more pages and "not found" handling. Needs a rewrite-all-to-index.html rule on the host (see Deployment). The swap is one file; worth it once the app has more than two screens

## Integration (Shared)
- [x] Happy path end to end (eval case 1): checked in the real app and by the live eval (3 of 3 runs)
- [x] Cases 2-4, no-options flow, failure and simulated handoff: checked in the real app on all 4 bookings and by the live eval
- [x] Run all 4 evals; check against PRD 2c success metrics. Final live run (claude-haiku-5-5, 12 conversations): 12 of 12 completed (target 70%), median 13 to 24 s per conversation (target under 5 minutes), 0 rule violations (target 0), 0 rebookings without explicit confirmation, shown costs match the service. Requirement understanding 93% (target 90%). One model only; one partial slip recorded in docs/work-log/cheich.md
- [ ] Frontend: chat and booking views (owner TBD)

## Open decisions
- UI scope and deadline for MVP 1
- Dev panel (generate booking, simulate disruption) is not in the PRD: agree it is in MVP 1 scope
