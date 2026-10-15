# Travel Buddy

An AI agent that helps a disrupted traveler compare replacement flights and complete a **simulated** rebooking. Claude reasons and explains. Application code enforces the rules, and the model has no tool that can book.

- **Traveler flow:** explains the disruption, asks for limits (extra cost, arrival time, connections), recommends up to three options, and rebooks only after explicit confirmation.
- **Code decides:** eligibility, cost, confirmation and duplicate-attempt checks are application code. Mock data and Duffel test data stay separate and labeled, and tool output is treated as untrusted.
- **Stack:** Python (FastAPI), React + TypeScript, Anthropic API, Duffel test API. 300+ backend tests.
- **Status:** MVP working end to end on test data (bookings, airline-change detection, chat, confirm). Agent-side limits filter, guards, evals and the chat UI are in progress. Not a production airline integration.

## Run it
Put `ANTHROPIC_API_KEY`, `MODEL` and a Duffel **test** `DUFFEL_ACCESS_TOKEN` in a local `.env`, then:

```bash
.venv/bin/uvicorn backend.app.api.main:dev_app --port 8000 --no-access-log
cd frontend && npm install && VITE_DEV_PANEL=true npm run dev   # http://localhost:5173
```

By [Jian Ting Li](https://github.com/JianTing-Li) (API, tools, Duffel, frontend) and [Cheich Toure](https://github.com/Cheicht) (agent, harness, evals). See [TASKS.md](TASKS.md).
