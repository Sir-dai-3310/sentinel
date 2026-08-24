"""Shared runtime-environment helpers.

Security-sensitive switches must default to the SAFE side and only relax in
explicitly local modes. Previously checks like
``os.getenv("ENVIRONMENT") == "production"`` failed OPEN: forgetting to set
``ENVIRONMENT`` (or typoing it as ``prod``) silently disabled JWT secret
validation, CSP/HSTS and the CORS wildcard guard.
"""

import os

LOCAL_MODES = {"", "development", "dev", "local"}


def is_local_mode() -> bool:
    """True only for explicitly local environments.

    Any other value (production, staging, prod, ...) is treated as
    production-grade: fail-closed behaviour for insecure defaults.
    """
    return os.getenv("ENVIRONMENT", "").strip().lower() in LOCAL_MODES
