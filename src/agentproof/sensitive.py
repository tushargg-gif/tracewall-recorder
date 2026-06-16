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


def looks_secret_token(token: str) -> bool:
    """Stricter check for whether a *command argument* names a secret file.

    ``looks_secret_path`` substring-matches, which is fine for real file paths
    but produces false positives on arbitrary command tokens — e.g. ``.env`` is
    a substring of ``os.environ``. This matches on the basename / extension so
    ``grep os.environ`` is not mistaken for reading a secret.
    """
    t = token.strip().strip("'\"").lower()
    if not t:
        return False
    if "secrets/" in t:
        return True
    base = t.rsplit("/", 1)[-1]
    for ext in (".env", ".pem", ".key"):
        if base == ext or base.startswith(ext) or base.endswith(ext):
            return True
    return any(name in base for name in ("id_rsa", "id_dsa", "credentials"))
