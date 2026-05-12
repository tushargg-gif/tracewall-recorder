from __future__ import annotations

from pathlib import Path

import pytest

from agentproof.paths import safe_project_path


def test_safe_project_path_allows_project_relative_path(tmp_path: Path):
    assert safe_project_path(tmp_path, "reports/out.md") == tmp_path / "reports" / "out.md"


def test_safe_project_path_blocks_traversal_and_absolute_paths(tmp_path: Path):
    with pytest.raises(ValueError):
        safe_project_path(tmp_path, "../secret.txt")
    with pytest.raises(ValueError):
        safe_project_path(tmp_path, "/etc/passwd")
