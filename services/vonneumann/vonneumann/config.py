"""Centralized configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

# Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# API authentication
VN_API_KEY = os.environ.get("VN_API_KEY", "dev-key")

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
