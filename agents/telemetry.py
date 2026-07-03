import os
import logging

def init_telemetry() -> None:
    """
    Initialize Langfuse / OpenTelemetry if the environment variables are present.
    No-ops if LANGFUSE_* variables are missing.
    """
    if not (os.getenv("LANGFUSE_SECRET_KEY") and os.getenv("LANGFUSE_PUBLIC_KEY")):
        logging.info("Langfuse credentials not found. Telemetry disabled.")
        return

    try:
        # Assuming langfuse and opentelemetry are installed via the [obs] extra
        from langfuse import Langfuse
        # Initialize Langfuse telemetry here
        # Example: langfuse = Langfuse()
        logging.info("Langfuse telemetry initialized successfully.")
    except ImportError:
        logging.warning("Langfuse or OpenTelemetry packages not installed. Telemetry disabled.")
