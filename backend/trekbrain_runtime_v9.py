"""V9-only settings; never changes the behaviour of the production V8 modules."""
import os


def free_mode() -> bool:
    # Opting out is an explicit operator choice, never inferred from a key.
    return os.getenv("TREKBRAIN_FREE_MODE", "1").strip().casefold() not in {"0", "false", "off", "no"}


def seconds(name: str, default: float, maximum: float = 60.0) -> float:
    try:
        value = float(os.getenv(name, str(default)))
        if not 0.1 <= value <= maximum:
            return default
        return value
    except ValueError:
        return default
