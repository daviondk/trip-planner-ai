from langfuse import Langfuse
from app.config.settings import settings
from typing import Callable, Any
from functools import wraps

# Initialize Langfuse client
try:
    langfuse_client = Langfuse(
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST
    )
except Exception:
    # If Langfuse initialization fails, create a mock client
    langfuse_client = None


def observe(func: Callable | None = None) -> Callable:
    """
    Decorator to observe function calls with Langfuse.
    If Langfuse is not available, the function runs without tracing.
    
    Can be used as @observe or @observe()
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            return f(*args, **kwargs)
        return wrapper
    
    if func is not None:
        # Called as @observe
        return decorator(func)
    else:
        # Called as @observe()
        return decorator


# Monkey-patch the observe method onto the client if it doesn't exist
if langfuse_client is not None and not hasattr(langfuse_client, 'observe'):
    langfuse_client.observe = observe
