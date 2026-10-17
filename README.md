# Travel Buddy

**An AI agent that rebooks travelers after a canceled, delayed or missed flight, and can't book anything the traveler didn't confirm.**

![Travel Buddy: the traveler's limits in plain words, flight options as cards with a recommended pick, and a rebooking receipt](docs/images/booking-page.jpg)

- **AI with guardrails in code.** Claude understands the traveler and explains the options. Application code enforces their limits, the price and the final Confirm button. The model has no tool that can book.
- **Measured, not assumed.** An eval runner, judged by code, replays scenarios against the live model. Latest run: **12 of 12** PRD scenarios completed with **0 rule violations**, and **97%** requirement understanding (target 90%) across 15 cases, including typos, Spanish and a group that disagrees.
- **Built like a product.** Option cards with a recommended pick, a receipt after booking, clear messages when the AI or server is down, test data that never goes stale, and a demo mode.
- **Stack:** Python (FastAPI), React + TypeScript, Claude (Anthropic API), Duffel test API. 680+ backend tests.

Everything is simulated: no real tickets are bought. Built by [Jian Ting Li](https://github.com/JianTing-Li) (API, tools, Duffel, frontend) and [Cheich Toure](https://github.com/Cheicht) (agent, safety harness, evals).

---

<details>
<summary><strong>Run it</strong></summary>

Put `ANTHROPIC_API_KEY`, `MODEL` and a Duffel **test** `DUFFEL_ACCESS_TOKEN` in a local `.env`, then:

```bash
python3.14 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt   # first time only
.venv/bin/uvicorn backend.app.api.main:dev_app --port 8000 --no-access-log
cd frontend && npm install && VITE_DEV_PANEL=true npm run dev   # http://localhost:5173
```

The "Dev tools" switch in the header hides the test tools for a demo.
</details>

<details>
<summary><strong>Check it</strong></summary>

```bash
.venv/bin/python -m pytest backend/tests/unit                                            # unit tests, no network
.venv/bin/python -m backend.tests.evals.runner --mode scripted                           # PRD scenarios, free
.venv/bin/python -m backend.tests.evals.runner --mode live --runs 3                      # real model (costs credit)
.venv/bin/python -m backend.tests.evals.runner --mode live --suite requirements --runs 2  # requirement understanding
```

The runner judges with code only, never with a second model.
</details>

<details>
<summary><strong>Out of scope for MVP 1</strong></summary>

- **No real tickets or payments.** Duffel's test mode and labeled mock data only.
- **One itinerary per booking.** A group always stays together.
- **Simulated support handoff.** No real staff follow up.
- **Prompt-injection defense is best effort.** Code enforces the limits and the confirmation, so a planted instruction can't book anything. Tested with `claude-haiku-5-5` only.
- **Memory only.** Sessions live in memory, so run one backend process. To deploy (Render + Vercel, with an access code and rate limits), see [docs/deploy.md](docs/deploy.md).
</details>

<details>
<summary><strong>Bookings list</strong></summary>

![Bookings list with disrupted and on-time test bookings](docs/images/bookings-list.jpg)
</details>
