from __future__ import annotations

import sys
from pathlib import Path

from tracewall import daemon


def test_macos_spec_is_a_launchd_plist():
    path, content, loader = daemon.service_spec("Darwin", dest_dir=Path("/x"))
    assert path.name == f"{daemon.SERVICE_LABEL}.plist"
    assert "<plist" in content and daemon.SERVICE_LABEL in content
    assert sys.executable in content and "tracewall" in content
    assert loader[0] == "launchctl"


def test_linux_spec_is_a_systemd_user_unit():
    path, content, loader = daemon.service_spec("Linux", dest_dir=Path("/x"))
    assert path.name == daemon.SYSTEMD_UNIT_NAME
    assert "[Service]" in content
    assert f"{sys.executable} -m tracewall daemon run" in content
    assert loader[:2] == ["systemctl", "--user"]


def test_install_writes_unit_without_loader(tmp_path: Path):
    info = daemon.install_service(system="Linux", dest_dir=tmp_path, run_loader=False)
    unit = tmp_path / daemon.SYSTEMD_UNIT_NAME
    assert unit.exists() and "ExecStart=" in unit.read_text(encoding="utf-8")
    assert info["backend"] == "systemd" and info["loaded"] is False


def test_install_is_idempotent(tmp_path: Path):
    daemon.install_service(system="Linux", dest_dir=tmp_path, run_loader=False)
    daemon.install_service(system="Linux", dest_dir=tmp_path, run_loader=False)  # no error on re-run
    assert (tmp_path / daemon.SYSTEMD_UNIT_NAME).exists()


def test_macos_install_writes_plist(tmp_path: Path):
    info = daemon.install_service(system="Darwin", dest_dir=tmp_path, run_loader=False)
    plist = tmp_path / f"{daemon.SERVICE_LABEL}.plist"
    assert plist.exists() and "<plist" in plist.read_text(encoding="utf-8")
    assert info["backend"] == "launchd"


def test_uninstall_removes_unit(tmp_path: Path):
    daemon.install_service(system="Linux", dest_dir=tmp_path, run_loader=False)
    info = daemon.uninstall_service(system="Linux", dest_dir=tmp_path, run_loader=False)
    assert info["removed"] is True
    assert not (tmp_path / daemon.SYSTEMD_UNIT_NAME).exists()
