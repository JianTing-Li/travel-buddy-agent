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
- [ ] Eval cases 1-4 from PRD 3d, expected behavior written first (tests/evals/cases/)
- [ ] Automated checks: unknown eligibility, wrong cost/currency, unavailable option, changed details, tool failure, duplicates, other traveler's booking, mock/Duffel mixing

## Jian: tools, services and API
- [ ] Find what Duffel's test API supports; record in docs/duffel-notes.md
- [ ] Duffel client (services/duffel/client.py)
- [ ] Mock service + scenarios for the 4 eval cases (services/mock/, data/mock/scenarios/)
- [ ] Tools: get_trip_context, search_replacements, prepare_rebooking, escalate_to_support, plus registry
- [ ] Source tagging so each option uses its matching validation and confirmation service
- [ ] FastAPI app: chat and confirm endpoints, booking access check, log redaction (api/main.py)
- [ ] Airline-change check while the app is open (PRD "Application responsibilities")
- [ ] Unit tests for tools
- [ ] frontend/src/app/types.ts mirroring the contract models

## Integration (Shared)
- [ ] Happy path end to end (eval case 1)
- [ ] Cases 2-4, no-options flow, failure and simulated handoff
- [ ] Run all 4 evals; check against PRD 2c success metrics
- [ ] Frontend: chat and booking views (owner TBD)

## Open decisions
- UI scope and deadline for MVP 1
- Frontend ownership
- Whether Duffel test account and API token exist yet
