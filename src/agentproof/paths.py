from __future__ import annotations

from pathlib import Path


def safe_project_path(project_root: Path, relative_path: str) -> Path:
    """Resolve a project-relative path without allowing traversal outside root."""
    if not relative_path:
        raise ValueError("Path is required")
    raw_path = Path(relative_path)
    if raw_path.is_absolute():
        raise ValueError(f"Path escapes project root: {relative_path}")

    root = project_root.resolve()
    candidate = (root / raw_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {relative_path}") from exc
    return candidate
