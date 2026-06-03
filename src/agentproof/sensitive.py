"""Single source of truth for what counts as a sensitive path.

Both the post-hoc verifier (which *flags* sensitive-file changes) and the
real-time enforcer (which *blocks* sensitive-file access) read from here, so the
two can never disagree about what "sensitive" means.
"""

from __future__ import annotations

# Substrings / suffixes that mark a path as holding secrets or credentials.
# A trailing "/" denotes a directory marker (the dir and everything under it).
SECRET_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.",
    ".pem",
    ".key",
    "id_rsa",
    "id_dsa",
    "credentials",
    "secrets/",
)


def looks_secret_path(path: str) -> bool:
    """True if ``path`` looks like a secret/credential file by name."""
    lowered = path.lower()
    return any(marker in lowered for marker in SECRET_PATTERNS)
