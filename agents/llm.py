import os
import sys
import time
from google.genai import errors

def generate_with_resilience(client, model, **kwargs):
    """
    Wraps client.models.generate_content with production resilience.
    - Up to 3 retries on 503 UNAVAILABLE with exponential backoff (4s, 8s, 16s).
    - If it still fails, falls back to FALLBACK_MODEL if defined in environment.
    - Other errors propagate immediately.
    """
    max_retries = 3
    base_backoff = 4
    
    for attempt in range(1, max_retries + 1):
        try:
            return client.models.generate_content(
                model=model,
                **kwargs
            )
        except errors.ServerError as e:
            if e.code == 503:
                if attempt == max_retries:
                    break  # Exit loop to trigger fallback if available
                
                backoff = base_backoff * (2 ** (attempt - 1))
                print(f"model busy, retry {attempt}/{max_retries} in {backoff}s...", file=sys.stderr)
                time.sleep(backoff)
            else:
                # Other ServerErrors propagate immediately
                raise e
        except Exception as e:
            # Client errors (like 429) or other exceptions propagate immediately
            raise e
            
    # If we exhausted retries for 503, try fallback model if available
    fallback_model = os.getenv("FALLBACK_MODEL")
    if fallback_model:
        print(f"Primary model {model} persistently unavailable. Switching to FALLBACK_MODEL: {fallback_model}", file=sys.stderr)
        return client.models.generate_content(
            model=fallback_model,
            **kwargs
        )
    
    # If no fallback model is set, raise the last encountered error
    raise Exception(f"Failed to generate content after {max_retries} retries with model {model} (503 UNAVAILABLE) and no FALLBACK_MODEL configured.")
