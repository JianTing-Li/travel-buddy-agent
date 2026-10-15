# Tasks

Status: [ ] todo · [~] in progress · [x] done. Update in the same PR as the work.

## 0. Setup (Shared)
- [~] Scaffold repo (branch setup/scaffold): backend/, frontend/, CODEOWNERS, docs
- [ ] Review and agree the DRAFT models in backend/app/contract/models.py (both)
- [ ] Decide who owns the frontend (features/chat, features/booking)
- [ ] Decide: UI scope for MVP 1 and deadline

## Cheich: agent and harness
- [x] System Prompt v0 from PRD 3b (agent/prompts/)
- [x] Tool-use loop with Claude (agent/loop.py), tested with stub tools (agent/stub_tools.py)
- [ ] Requirement extraction: required limits vs preferences, clarifying questions (agent/decide.py)
- [ ] Limits filter: budget, arrival window, connections, passenger count (harness/limits.py)
- [ ] Explicit-confirmation gate and duplicate-attempt tracking (harness/confirmation.py)
- [ ] Guards: untrusted tool content, block rebooking when eligibility or cost unknown (harness/guards.py)
- [ ] Unit tests for harness
- [x] Eval cases 1-4 from PRD 3d, expected behavior written first (tests/evals/cases/), written as JSON; no runner yet
- [ ] Automated checks: unknown eligibility, wrong cost/currency, unavailable option, changed details, tool failure, duplicates, other traveler's booking, mock/Duffel mixing

## Jian: tools, services and API
- [x] Find what Duffel's test API supports; record in docs/duffel-notes.md
- [x] Duffel client (services/duffel/client.py)
- [x] Duffel follow-up: LHR to LTN airline-initiated change scenario (Duffel docs "Test your integration"), fetch/accept calls, LHR to DXB connections and LHR to STN price-change routes; correct docs/duffel-notes.md and extend the client if they work (proposed)
- [x] Mock service + scenarios for the 4 eval cases (services/mock/, data/mock/scenarios/); fault modes for the automated checks are in `MockService.set_faults`
- [x] Mock booking store, disruption simulator, seeded generator and fault modes, labeled simulated (services/mock/) (proposed)
- [x] Tools: get_trip_context, search_replacements, prepare_rebooking, escalate_to_support, plus registry (mock and Duffel test bookings)
- [x] Source tagging so each option uses its matching validation and confirmation service (booking id routes to the mock or Duffel service; option data_source must match)
- [x] FastAPI app: chat and confirm endpoints, booking access check, log redaction (api/main.py); sessions are in memory
- [x] Dev/booking endpoints: generate test booking (seeded scenarios, Duffel test order), simulate disruption, set faults; only with dev_app, scoped to the session (api/) (proposed)
- [ ] Optional, nice to have: richer generated booking options (3 to 5 options with a spread of costs, arrival times and connections, including a $0 option and a one-connection option) so the comparison screen has more to show; Duffel's test airline only returns one flat cost, a few departure times and nonstop flights, so this is mock-only (services/mock/generator.py)
- [x] Airline-change check while the app is open (PRD "Application responsibilities"); polls every 8 seconds, mock and Duffel
- [x] Unit tests for tools
- [x] frontend/src/app/types.ts mirroring the contract models (and the API schemas)

## UI shell (extra, proposed: needs agreement before starting; Jian shell, Cheich features/chat)
- [ ] Agree: frontend ownership, booking summary type for the list page, chat-slot interface (messages in, onSend out), dev panel in MVP 1 scope, and react-router (routes / and /bookings/:id; CLAUDE.md requires agreement)
- Design decided by Jian (Cheich to confirm): plain CSS with CSS variables, light and dark mode, app name "Travel Buddy", persistent "Simulated environment" badge, source pill (Duffel test or Mock) on every booking
- [x] Shell built on fixtures typed by types.ts: bookings list, booking detail with disruption banner, confirm card with simulated label, placeholder where the chat goes
- [x] Dev panel: generate test booking (seeded scenario picker, Duffel test order) and simulate disruption, labeled simulated; shown only with VITE_DEV_PANEL=true
- [x] Wire the shell to the real API once the chat/confirm and dev/booking endpoints exist
- [x] UI polish from a design review: booking cards with city names, time, airline and action; recovery workspace layout; conversation and airline-change banners kept across navigation; "Checking your rebooking" state for uncertain confirmations; plain-language footer
- [ ] Structured comparison: up to three flight cards from validated tool results with a reason derived from code facts (needs an API addition and Cheich's limits filter), editable requirement chips fed by the agent's confirmed limits, progress stepper, no-options screen. Not a requirements form: the PRD has the agent capture needs from everyday language
- [ ] Cheich's chat plugs into the chat slot

## Deployment (later, after the demo; proposed)
- [ ] Decide hosting (Vercel alone is not enough for this project; it needs two services): backend on a long-running host (Render, Railway or Fly) with ONE worker (`--workers 1`), frontend on Vercel or Netlify. Sessions, chat history, the confirmation gate and mock state live in memory, so serverless functions or several workers would lose them between requests. The alternative is moving that state to Redis or a database (a feature of its own, not in the PRD)
- [ ] Set the same variable names in the host's dashboard as secrets (ANTHROPIC_API_KEY, DUFFEL_ACCESS_TOKEN, MODEL; Duffel must stay a `duffel_test_` token). `.env` is not deployed and `load_dotenv` does not override real environment variables
- [ ] Make the allowed CORS origin configurable for the deployed frontend URL (needs one new env var such as ALLOWED_ORIGINS, or a deploy entry point passing `allowed_origins` to `create_app`; CLAUDE.md allows only three env var names, so agree first and update .env.example, which Jian owns)
- [ ] Frontend: read the API address from a build-time `VITE_API_URL` (public, never put keys in it); add a rewrite-all-to-index.html rule (`vercel.json` or Netlify `_redirects`) if react-router is used
- [ ] Check the host offers Python 3.14 (CLAUDE.md) BEFORE choosing it, or agree an older version with Cheich. Start the backend with `--no-access-log` and with `backend.app.api.main:app`, never `dev_app` (its /dev endpoints create test orders and must not be public)
- [ ] Public demo protection: anyone with the link can use the Anthropic key through POST /chat and create Duffel test orders. Before sharing a live URL add a simple guard (a shared access code the page sends, plus a per-session and per-IP rate limit and a cap on chat turns), and set a spending limit on the Anthropic key. Nothing like this is built yet

## Integration (Shared)
- [ ] Happy path end to end (eval case 1)
- [ ] Cases 2-4, no-options flow, failure and simulated handoff
- [ ] Run all 4 evals; check against PRD 2c success metrics
- [ ] Frontend: chat and booking views (owner TBD)

## Open decisions
- UI scope and deadline for MVP 1
- Frontend ownership
- Dev panel (generate booking, simulate disruption) is not in the PRD: agree it is in MVP 1 scope
- Whether Duffel test account and API token exist yet
