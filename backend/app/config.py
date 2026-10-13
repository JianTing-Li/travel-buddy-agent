"""Loads environment variable names (ANTHROPIC_API_KEY, DUFFEL_ACCESS_TOKEN, MODEL) via python-dotenv. Owner: Shared."""
import os

from dotenv import load_dotenv

load_dotenv()

ENV_VAR_NAMES = ("ANTHROPIC_API_KEY", "DUFFEL_ACCESS_TOKEN", "MODEL")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DUFFEL_ACCESS_TOKEN = os.getenv("DUFFEL_ACCESS_TOKEN")
MODEL = os.getenv("MODEL")
