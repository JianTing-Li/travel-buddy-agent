# Jian work log

## 2026-10-30: loading state while the demo server starts (branch codex/readme-demo-gif)
- Keep the booking skeleton visible and show a startup hint after 4 seconds on both the bookings list and booking detail. Say the server may be waking up, since the browser cannot confirm that it is asleep.
- Allow 90 seconds for the first server response; normal requests return to 20 seconds after a response, and chat keeps its 100-second timeout.
- If loading fails, explain the possible startup delay and keep the existing Try again action. Offline devices get connection guidance; other server errors remain generic. Chat and confirmation error handling are unchanged.
- Checked: production frontend build and lint; browser checks with simulated time verified the delayed hint on both screens, the 90-second startup timeout, successful retry and the 20-second timeout after a response.

## 2026-10-30: animated README demo (branch codex/readme-demo-gif)
- Replaced the main README screenshot with `docs/images/travel-buddy-demo.gif`, a 42-second recording using real AI responses and simulated rebooking.
- The paragraph covers three travelers, a $100 total extra-cost limit, arrival before 6 PM, a nonstop preference and permission for one connection. The flow selects the recommended $90 nonstop, reviews the flight, explicitly confirms and displays the receipt.
- The GIF and README disclose that AI waiting time was shortened. The existing bookings-list image and original screenshot are retained.
- Checked the README image path, GIF dimensions and duration, decoded all GIF frames, and ran `git diff --check`. No application code changed.
