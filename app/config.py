"""Configuration settings for Project Chrysalis."""
import logging
import os
import warnings
from typing import Dict, Any


def _resolve_gcp() -> tuple:
    """Resolve (project_id, credentials_available).

    Project: $GOOGLE_CLOUD_PROJECT, else Application Default Credentials / gcloud config.
    Credentials: whether ADC can be loaded at all. Without them every Gemini call would fail, so
    agents skip straight to their deterministic offline fallbacks (set CHRYSALIS_OFFLINE=1 to force).
    """
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    credentials_available = False
    if os.getenv("CHRYSALIS_OFFLINE", "").lower() not in ("1", "true", "yes"):
        try:
            import google.auth

            _, adc_project = google.auth.default()
            credentials_available = True
            project = project or adc_project
        except Exception:
            pass
    return project or "your-gcp-project-id", credentials_available


# Google Cloud / Vertex AI Settings
PROJECT_ID, VERTEX_AI_AVAILABLE = _resolve_gcp()
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
# Number of live LLM attempts per agent invocation (0 => deterministic offline fallback only)
LLM_MAX_ATTEMPTS = 3 if VERTEX_AI_AVAILABLE else 0

# Ensure Vertex AI routing for google-genai and google-adk.
# GOOGLE_GENAI_USE_ENTERPRISE supersedes the deprecated GOOGLE_GENAI_USE_VERTEXAI in
# google-adk >= 2.9 / google-genai >= 2.x; both are set (consistently) for compatibility.
os.environ.setdefault("GOOGLE_GENAI_USE_ENTERPRISE", "True")
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = os.environ["GOOGLE_GENAI_USE_ENTERPRISE"]
os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID
os.environ["GOOGLE_CLOUD_LOCATION"] = LOCATION


class _DropAdkCacheHint(logging.Filter):
    """Suppress ADK's advisory 'no context_cache_config' hint (performance tip, not an error)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "context_cache_config" not in record.getMessage()


logging.getLogger("google_adk.google.adk.runners").addFilter(_DropAdkCacheHint())
warnings.filterwarnings("ignore", message=r"\[EXPERIMENTAL\] feature FeatureName\.JSON_SCHEMA_FOR_FUNC_DECL")

# Unified LLM Model Configuration
# Primary: Gemini 4.0 Argon on Vertex AI
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-4-argon")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-004")

# Target Environment Constants (Compact Mode)
CACHE_MAX_KEYS = int(os.getenv("CACHE_MAX_KEYS", "5"))
DB_MAX_CONNECTIONS = int(os.getenv("DB_MAX_CONNECTIONS", "2"))
DB_PROCESSING_DELAY_SEC = float(os.getenv("DB_PROCESSING_DELAY_SEC", "0.100"))  # 100ms
DB_ACQUISITION_TIMEOUT_SEC = float(os.getenv("DB_ACQUISITION_TIMEOUT_SEC", "0.500"))  # 500ms

# System Health & Credit Attribution Constants (AgentEvolver Formulations)
TARGET_P99_LATENCY_MS = float(os.getenv("TARGET_P99_LATENCY_MS", "50.0"))
HEALTH_WEIGHT_LATENCY = float(os.getenv("HEALTH_WEIGHT_LATENCY", "0.35"))
HEALTH_WEIGHT_5XX = float(os.getenv("HEALTH_WEIGHT_5XX", "0.40"))
HEALTH_WEIGHT_POOL = float(os.getenv("HEALTH_WEIGHT_POOL", "0.25"))

CREDIT_ALPHA = float(os.getenv("CREDIT_ALPHA", "1.2"))
CREDIT_BETA = float(os.getenv("CREDIT_BETA", "0.1"))

# Server Configuration
SERVER_HOST = os.getenv("CHRYSALIS_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("CHRYSALIS_SERVER_PORT", "8008"))
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
