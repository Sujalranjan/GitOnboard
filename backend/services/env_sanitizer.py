"""
Shared secret-stripping helper for anything that spawns a subprocess or container
on behalf of AI-generated / agent-driven execution (SandboxManager, DockerVerificationRunner).
"""
from __future__ import annotations

import os
from typing import Dict

# Environment variable keys that must never reach a spawned subprocess or container.
SENSITIVE_ENV_KEYS = {
    "JWT_SECRET",
    "GITHUB_CLIENT_SECRET",
    "AZURE_STORAGE_ACCOUNT_KEY",
    "AZURE_STORAGE_CONNECTION_STRING",
    "LOCAL_DATABASE_URL",
    "PROD_DATABASE_URL",
    "DATABASE_URL",
    "GITHUB_ACCESS_TOKEN",
}


def get_sanitized_env(extra: Dict[str, str] | None = None) -> Dict[str, str]:
    """Returns a copy of os.environ with sensitive secrets stripped, optionally merged with extra vars."""
    clean_env = {k: v for k, v in os.environ.items() if k.upper() not in SENSITIVE_ENV_KEYS}
    if extra:
        clean_env.update(extra)
    return clean_env
