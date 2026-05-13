# src/utils/env_check.py
#
# Early validation of required environment variables.
# Call assert_env() at the top of main.py and each module runner that
# makes LLM calls, so failures are caught immediately with a clear message
# instead of crashing mid-pipeline with a KeyError.

import os
import sys
from pathlib import Path

REQUIRED_VARS = ["TF_API_KEY", "TF_BASE_URL", "TF_MODEL"]


def assert_env(extra: list[str] | None = None) -> None:
    """Exit with a clear message if any required env vars are missing."""
    check = REQUIRED_VARS + (extra or [])
    missing = [v for v in check if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing required environment variables: {missing}")
        print("Copy .env.example to .env and fill in the values.")
        sys.exit(1)


def assert_prompts(prompt_dir: Path) -> None:
    """Exit with a clear message if the prompt directory is missing."""
    if not prompt_dir.exists():
        print(f"ERROR: Prompt directory not found: {prompt_dir}")
        print("Ensure prompt/system_prompt/ is present and populated.")
        sys.exit(1)
