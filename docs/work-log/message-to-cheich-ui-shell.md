# Draft message to Cheich: UI shell (delete after sending)

Hey Cheich, I'd like to build a small web UI shell now, in parallel with the tools, so we have something to show and your chat can sit on top of it. Nothing is built yet. Five things I need your OK on (they're in TASKS.md under "UI shell"):

1. Frontend ownership. I'd own the shell (bookings list, booking detail, confirm card, dev panel). You'd own `frontend/src/features/chat`. CLAUDE.md lists `frontend/` as unassigned, so this needs both of us.
2. Router. CLAUDE.md says no router without agreement. I'd add `react-router` only, with two routes: `/` (bookings list) and `/bookings/:id` (detail with the chat slot and confirm card). No state library or UI kit; plain CSS with variables, light and dark mode.
3. Chat-slot interface. The detail page renders your chat component with a small prop contract. My proposal: `messages` in, `onSend(text)` out, plus the booking id. You tell me what shape you need from your loop and I'll match it.
4. Booking summary type. The contract has `TripContext` but nothing for a list row. I'd add a small `BookingSummary` (id, route, departure, traveler count, reference, status, data_source). It would live in `types.ts` until we agree it belongs in `contract/`, which needs both of us.
5. Dev panel. Not in the PRD: "generate test booking" (seeded scenarios matching the 4 eval cases, or random from them) and "simulate disruption". Behind a dev flag, test token only, always labeled simulated. Duffel can simulate an airline change on LHR to LTN; everything else would come from the mock service. OK to include in MVP 1 scope?

Also, the contract models (`models.py`) are still a DRAFT and block my tools. When can we go through the TODOs together (`eligibility`, `validity`, `flight_details`, cost types)?

Design mockup: I can share the three screens (bookings list, booking detail with the chat slot, confirm card) if you want to see them first.
