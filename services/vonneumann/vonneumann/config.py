"""Centralized configuration loaded from environment variables."""

import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

if os.environ.get("PYTHON_DOTENV_DISABLED", "").lower() not in {"1", "true", "yes"}:
    load_dotenv()

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_AUTH_API_KEY = (
    os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
    or os.environ.get("SUPABASE_ANON_KEY", "")
    or SUPABASE_SERVICE_ROLE_KEY
)

# Browser requests use verified Supabase user tokens, never a shared API key.
VN_ENVIRONMENT = (
    os.environ.get("VN_ENVIRONMENT")
    or os.environ.get("VERCEL_ENV")
    or os.environ.get("NODE_ENV")
    or "development"
)
VN_REQUIRE_HTTPS = VN_ENVIRONMENT not in {"development", "test"}


def parse_allowed_origins(value: str) -> tuple[str, ...]:
    """Only exact origins are accepted; an empty setting permits no browsers."""
    origins = []
    for item in value.split(","):
        origin = item.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or "*" in origin
            or any(char.isspace() for char in origin)
            or (parsed.scheme == "http" and (
                VN_REQUIRE_HTTPS or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            ))
        ):
            raise ValueError("VN_ALLOWED_ORIGINS must contain exact secure browser origins")
        try:
            parsed.port
        except ValueError:
            raise ValueError("VN_ALLOWED_ORIGINS contains an invalid port") from None
        if origin not in origins:
            origins.append(origin)
    return tuple(origins)


VN_ALLOWED_ORIGINS = parse_allowed_origins(os.environ.get("VN_ALLOWED_ORIGINS", ""))

# WebSocket server
VN_WS_PORT = int(os.environ.get("VN_WS_PORT", "8765"))
VN_HOST = os.environ.get("VN_HOST", "0.0.0.0")

# Simulation defaults
VN_TICK_INTERVAL_MS = int(os.environ.get("VN_TICK_INTERVAL_MS", "1000"))
VN_INITIAL_CAPITAL = float(os.environ.get("VN_INITIAL_CAPITAL", "10000"))
VN_MAX_PROBES = int(os.environ.get("VN_MAX_PROBES", "50"))
VN_GENESIS_POPULATION = int(os.environ.get("VN_GENESIS_POPULATION", "10"))
VN_SEED_CAPITAL = float(os.environ.get("VN_SEED_CAPITAL", "100"))

# Evolution
VN_MUTATION_RATE = float(os.environ.get("VN_MUTATION_RATE", "0.20"))
VN_CHILD_COUNT = int(os.environ.get("VN_CHILD_COUNT", "2"))
VN_CAPITAL_SPLIT = float(os.environ.get("VN_CAPITAL_SPLIT", "0.45"))
VN_DIVERSITY_THRESHOLD = float(os.environ.get("VN_DIVERSITY_THRESHOLD", "0.10"))

# Circuit breaker
VN_CIRCUIT_BREAKER_DROP_PCT = float(os.environ.get("VN_CIRCUIT_BREAKER_DROP_PCT", "0.30"))

# Logging
VN_LOG_LEVEL = os.environ.get("VN_LOG_LEVEL", "INFO")
