import os
import sys
from pathlib import Path
from dotenv import load_dotenv

def load_environment():
    """
    Deterministically loads the .env file from the repository root
    and enforces fail-fast if critical variables are missing.

    In cloud mode (Cloud Run / Agent Engine), the .env file does not
    exist — environment variables are injected by the platform via
    Secret Manager or service configuration.  We silently skip the
    dotenv load and proceed to the fail-fast checks.
    """
    # utils/env.py is 1 level deep, so parents[1] is the repo root
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.is_file():
        load_dotenv(dotenv_path=env_path)
    else:
        # Cloud mode: env comes from the platform; no .env file expected
        pass

    # Fail fast at startup if required models are missing
    if not os.environ.get("EXTRACTOR_MODEL"):
        print("FATAL: EXTRACTOR_MODEL environment variable must be set to a valid model ID.")
        sys.exit(1)
    if not os.environ.get("WRITER_MODEL"):
        print("FATAL: WRITER_MODEL environment variable must be set to a valid model ID.")
        sys.exit(1)

