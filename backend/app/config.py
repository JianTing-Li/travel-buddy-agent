"""Loads the app's environment variables via python-dotenv. Owner: Shared.

ANTHROPIC_API_KEY, DUFFEL_ACCESS_TOKEN (test token only) and MODEL are secrets or model settings. For a deployment,
ALLOWED_ORIGINS lists the frontend address(es) allowed to call the API (comma-separated), and DEMO_ACCESS_CODE, when
set, is required to start a session, so a shared link can't be used by anyone who finds it.
"""
import os

from dotenv import load_dotenv

load_dotenv()

ENV_VAR_NAMES = ("ANTHROPIC_API_KEY", "DUFFEL_ACCESS_TOKEN", "MODEL", "ALLOWED_ORIGINS", "DEMO_ACCESS_CODE")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DUFFEL_ACCESS_TOKEN = os.getenv("DUFFEL_ACCESS_TOKEN")
MODEL = os.getenv("MODEL")
# e.g. "https://travel-buddy.vercel.app"; empty means the local Vite dev server only
ALLOWED_ORIGINS = tuple(o.strip().rstrip("/") for o in (os.getenv("ALLOWED_ORIGINS") or "").split(",") if o.strip())
DEMO_ACCESS_CODE = os.getenv("DEMO_ACCESS_CODE") or None
