# Duffel notes

What Duffel's test API does and does not support for Travel Buddy. Owner: Jian.

Everything marked **Verified** was observed by running `backend/app/services/duffel/probe.py` against Duffel's test API on 2026-10-14 (test token, `live_mode: false`). Anything not observed is marked **Untested** or **Docs only**. Nothing here is guessed.

Re-run: `python -m backend.app.services.duffel.probe --create-orders --confirm-change` (flags and safety checks are in the script's docstring).

## Setup facts (verified)
- Base URL `https://api.duffel.com`. Headers: `Authorization: Bearer <token>`, `Duffel-Version: v2`, `Accept: application/json`, `Content-Type: application/json`. Request bodies are wrapped as `{"data": {...}}` and responses as `{"data": ...}`.
- Test tokens start with `duffel_test_`. An invalid token returns `401` with `authentication_error` / `access_token_not_found`.
- Rate limit headers (`ratelimit-limit`, `ratelimit-remaining`, `ratelimit-reset`) are returned. Limit was `30` on `POST /air/offer_requests` and `120` on every other call tried. The length of the window was not measured.
- Errors have the shape `{"errors": [{"type", "code", "title", "message"}]}`. Failures seen are listed under "Error codes seen".
- The only airline we can book in test mode is Duffel Airways (`ZZ`). The probe only books `ZZ` offers.
- Test data rules learned: passenger `family_name` must not contain digits (`422 validation_format`).

## Call results

| # | Call | Result | Notes |
|---|---|---|---|
| 1 | `POST /air/offer_requests?return_offers=true` | **Works** (201) | JFK to LAX, 30 days out, economy. 1 passenger returned 15 offers (AA, BA, CM, IB, SY, ZZ). 3 passengers returned 41 offers (adds AS). Exactly one `ZZ` offer each time. |
| 2 | `POST /air/orders` | **Works** (201) | `ZZ` offer, `payments: [{type: "balance", currency, amount}]` with the offer's total, no `type` field sent. Returned `type: "instant"`. Worked for 1 and for 3 passengers. |
| 3 | `GET /air/orders/{id}` | **Works** (200) | Includes `available_actions`, `slices` (with ids), `passengers`, `conditions`, `changes` and `airline_initiated_changes` (both arrays, empty here), `total_amount`, `total_currency`, `owner`. |
| 4 | `GET /air/airline_initiated_changes` (all, and `?order_id=`) | **Works** (200) | Returned an empty list in every run. |
| 5 | `GET /air/airline_initiated_changes/{id}` | **Untested** | No airline-initiated change exists to fetch. The docs pages I could read did not show this path, so it is only a candidate. |
| 6 | Accept an airline-initiated change (candidate `POST .../{id}/actions/accept`) | **Untested** | Nothing to accept. Duffel's docs I could read do not give the accept path. |
| 7 | `PATCH /air/airline_initiated_changes/{id}` (`action_taken`) | **Untested, docs only** | Documented, but needs an existing change. |
| 8 | `POST /air/order_change_requests` | **Works** (201) | Remove the order's slice by `slice_id`, add origin/destination/date/`cabin_class`. Date +1 day gave offers on the first try; +2 and +3 days were never needed. Response embeds `order_change_offers`. |
| 9 | `GET /air/order_change_offers?order_change_request_id=` | **Works** (200) | Also with `sort=change_total_amount`. |
| 10 | `GET /air/order_change_offers/{id}` | **Works** (200) | |
| 11 | `POST /air/order_changes` (pending change) | **Works** (201) | Body `{selected_order_change_offer}`. `confirmed_at` is null and `expires_at` is set. |
| 12 | `POST /air/order_changes/{id}/actions/confirm` | **Works** (200) | Only with a `payment` object (see below). Sets `confirmed_at`. |
| 13 | Confirm the same change a second time | **Rejected** (422) | `invalid_state_error` / `order_change_already_confirmed`. Duffel itself blocks a duplicate confirm. |
| 14 | A second change on an already-changed order | **Rejected** (422) | `invalid_state_error` / `order_not_changeable`, "This order cannot be changed through the API." |

## Order-change details (verified)

### Cost fields
Each order change offer, the pending change and the confirmed change carry:
- `change_total_amount` + `change_total_currency`: what the traveler pays or gets back for the change.
- `penalty_total_amount` + `penalty_total_currency`: the airline's change penalty.
- `new_total_amount` + `new_total_currency`: the price of the new flight as if bought new.
- `refund_to` (offers: `original_form_of_payment`; pending and confirmed change: `null`) and `expires_at`.
- `conditions.change_before_departure` and `conditions.refund_before_departure`, each with `allowed`, `penalty_amount`, `penalty_currency`.

PRD rule: the additional cost is `change_total_amount`, never `new_total_amount`. In our runs, 1 passenger had `new_total_amount` 273.75 and 3 passengers had 619.21, while `change_total_amount` was 125.00 in both.

### What the test airline returned
- All 9 offers on both orders had the same `change_total_amount` (125.00 USD), the same penalty (25.00 USD) and the same `new_total_amount`. The 1-passenger and 3-passenger requests both showed 125.00, so a per-passenger vs whole-booking meaning cannot be told apart from this data.
- The 9 offers were three departure times repeated three times each (06:00, 12:00 and 18:00 on the next day), all one segment (nonstop), all `PT5H52M` flight duration. The ISO timestamps carry no UTC offset; time zones come from the airport objects.
- No offer had a zero or negative `change_total_amount`, so a free change, a refund and the "no payment needed" path were never exercised.
- The probe did not check whether the 9 offers are real duplicates or differ in fare brand or conditions.

### Payment on confirm
- Confirming a change with `change_total_amount` 125.00 and **no** `payment` failed: `422 validation_required`, "Field 'payment' can't be blank".
- Confirming with `payment: {type: "balance", currency: "USD", amount: "125.00"}` (the pending change's own amount and currency) succeeded.
- The confirm response lists `available_payment_types` (2 values, not recorded) and `selected_services` (empty).

### Order state after a confirmed change
- `available_actions` went from `[cancel, change, update]` to `[cancel, update]`, and the slice id changed. So in test mode an order can be changed once; the next change request returns `order_not_changeable`.
- For repeat test runs, create a fresh order each time (the probe does).

## Airline-initiated changes
- The list endpoint works but is always empty in test mode. I found no way to create one, and Duffel's test-mode docs I could read do not describe one.
- Fetching a single change, accepting one, and the `PATCH` update are therefore **untested**.
- The order object has an `airline_initiated_changes` array. It was empty, so a populated one has never been seen.
- Duffel's docs say the API accept flow applies to orders on Managed Content or the merchant's own agency agreement. Not checked here.

## What this means for Travel Buddy (inferences, not observations)
- **get_trip_context**: order, passengers, slices and `airline_initiated_changes` can come from `GET /air/orders/{id}`. A real airline-change disruption cannot be produced in test mode, so cancellation scenarios need the mock service.
- **Eligibility**: Duffel returns no eligibility field. Signals available: `available_actions` contains `change`, `conditions.change_before_departure.allowed`, and whether any offers come back. The harness must decide how those map; an unknown must block rebooking.
- **search_replacements / prepare_rebooking**: `order_change_requests` + offers work. Re-fetching the offer (`GET .../order_change_offers/{id}`) is available to recheck cost and `expires_at`.
- **Completion**: pending change + confirm works for a Duffel test order, but only once per order and only with a payment object sized to `change_total_amount`.
- **Duplicate attempts**: Duffel rejects a repeat confirm (`order_change_already_confirmed`). App-level tracking is still needed for uncertain results (e.g. a timeout), because a retry's outcome could not be tested.
- **Cannot be reproduced with Duffel test data, so mock is needed**: eval case 1 (specific arrival times of 1, 2 and 4 PM; free changes), case 2 (missed flight; a $80 vs $140 cost spread), case 3 (different costs and an expensive early option), case 4 (embedded instructions). Duffel Airways gave one flat cost, three departure times, and nonstop only.
- **Not tested at all**: connecting flights as replacements, other cabins, other routes, `max_connections` values, other airlines' sandboxes, expired offers, changing an order for a different date range than +1 day, multi-slice orders.

## Error codes seen

| Call | Status | type / code | When |
|---|---|---|---|
| any | 401 | `authentication_error` / `access_token_not_found` | invalid token |
| `POST /air/orders` | 422 | `validation_error` / `validation_format` | digits in `family_name` |
| confirm | 422 | `validation_error` / `validation_required` | no `payment` object with a positive change total |
| confirm | 422 | `invalid_state_error` / `order_change_already_confirmed` | second confirm |
| `POST /air/order_change_requests` | 422 | `invalid_state_error` / `order_not_changeable` | order already changed once |
