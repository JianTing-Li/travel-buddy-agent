# Deploying Travel Buddy

Backend on Render, frontend on Vercel. Deploy the backend first: the frontend needs its address at build time, and
the backend needs the frontend's address to allow it (CORS). Owner: Jian.

## Before you share a link
- **Set a spending limit on the Anthropic API key** (Anthropic console, Limits). The app's rate limits help, but
  this is the real cap.
- **Set `DEMO_ACCESS_CODE`.** Without it, anyone with the link can chat on your key.
- Use a Duffel **test** token only (`duffel_test_...`).

## 1. Backend on Render
1. In Render, New > Blueprint, and pick this repository. It reads `render.yaml` (Python 3.14 from `.python-version`,
   one worker, `main:app` without the dev endpoints).
2. Fill in the secrets it asks for: `ANTHROPIC_API_KEY`, `DUFFEL_ACCESS_TOKEN`, `DEMO_ACCESS_CODE`. Leave
   `ALLOWED_ORIGINS` empty for now.
3. When it is live, open `https://<your-service>.onrender.com/health`. It should say `{"status":"ok"}`.

## 2. Frontend on Vercel
1. In Vercel, Add New > Project, pick this repository, and set **Root Directory** to `frontend`. Vercel detects Vite
   (build `npm run build`, output `dist`).
2. Add the environment variable `VITE_API_URL` = your Render address (no trailing slash). Anything starting with
   `VITE_` is public, so never put a key there. Leave `VITE_DEV_PANEL` unset: the dev tools stay out of the public site.
3. Deploy, and copy the address Vercel gives you.

## 3. Connect them
1. Back in Render, set `ALLOWED_ORIGINS` to the Vercel address (e.g. `https://travel-buddy.vercel.app`; several
   addresses can be separated by commas), and redeploy.
2. Open the Vercel address, enter the access code, and check that a chat works.

## Good to know
- **Rate limits** (in `backend/app/api/rate_limit.py`): 20 new sessions per address per hour, 20 messages per address
  per minute, 80 messages per session.
- **Memory only.** A restart or deploy wipes all sessions and chats. On Render's free plan the service sleeps when idle,
  so the first visit after a while is slow and starts fresh.
- The app uses a hash router (`#/bookings/...`), so Vercel needs no rewrite rules.
