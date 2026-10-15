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
- [x] Mock service + scenarios for the 4 eval cases (services/mock/, data/mock/scenarios/); fault modes for the automated checks still to do
- [ ] Mock booking store and disruption simulator, labeled simulated (services/mock/) (proposed)
- [x] Tools: get_trip_context, search_replacements, prepare_rebooking, escalate_to_support, plus registry (mock bookings only; Duffel path open)
- [ ] Source tagging so each option uses its matching validation and confirmation service
- [ ] FastAPI app: chat and confirm endpoints, booking access check, log redaction (api/main.py)
- [ ] Dev/booking endpoints: list, get, generate test booking (seeded scenarios), simulate disruption; dev flag and test-token only, scoped to the current traveler (api/) (proposed)
- [ ] Airline-change check while the app is open (PRD "Application responsibilities")
- [x] Unit tests for tools
- [ ] frontend/src/app/types.ts mirroring the contract models

## UI shell (extra, proposed: needs agreement before starting; Jian shell, Cheich features/chat)
- [ ] Agree: frontend ownership, booking summary type for the list page, chat-slot interface (messages in, onSend out), dev panel in MVP 1 scope, and react-router (routes / and /bookings/:id; CLAUDE.md requires agreement)
- Design decided by Jian (Cheich to confirm): plain CSS with CSS variables, light and dark mode, app name "Travel Buddy", persistent "Simulated environment" badge, source pill (Duffel test or Mock) on every booking
- [ ] Shell built on fixtures typed by types.ts: bookings list, booking detail with disruption banner, confirm card with simulated label, placeholder where the chat goes
- [ ] Dev panel: generate test booking (seeded scenario picker) and simulate disruption, labeled simulated
- [ ] Wire the shell to the real API once the chat/confirm and dev/booking endpoints exist
- [ ] Cheich's chat plugs into the chat slot

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
