"""Real-time enforcement: confine an agent's process tree so it cannot read,
write, or delete sensitive files.

AgentProof launches the agent, so it can confine the *process tree it spawns*
without any kernel driver, EDR, or elevated privilege. This module generates an
OS sandbox profile from a list of sensitive path patterns and runs a command
under it. Any read/write/unlink against a sensitive path is denied by the
kernel and surfaced as an ``enforcement_decision`` with ``action_taken="blocked"``
-- the preventive counterpart to the verifier's post-hoc ``action_taken="flagged"``.

Backends
    macOS   ``sandbox-exec`` (Seatbelt / SBPL). Present on every macOS at
            ``/usr/bin/sandbox-exec``. Apple lists the CLI as deprecated, but it
            still functions and is widely used (Chromium, Claude Code's own
            sandbox). The forward path is the EndpointSecurity framework, which
            needs an Apple-granted entitlement.
    Linux   ``bubblewrap`` (``bwrap``). Builds a mount namespace that binds the
            real filesystem, then masks sensitive paths (``--tmpfs`` over dirs,
            ``--ro-bind /dev/null`` over files). NOTE: authored but NOT yet
            verified on a Linux host from this workstation. Two honest semantic
            differences from macOS: (a) a masked file reads as *empty* rather
            than raising EPERM (no info leaks, but not a clean "blocked" signal),
            and (b) masks are enumerated at launch, so files created later that
            match a pattern are not covered. A Landlock / LD_PRELOAD backend
            would restore EPERM + pattern coverage and is the planned hardening.
    other   Unsupported. ``guard_supported()`` returns False so callers fail
            closed (refuse to start) rather than run an agent unprotected.

Scope and honest limits
    * Confines only processes this module spawns and their children. It does not
      police pre-existing processes -- it does not need to, because the agent is
      a child of AgentProof.
    * Default-deny on sensitive paths, default-allow on everything else. This is
      a guardrail against accidental/rogue access, not a containment boundary for
      a determined attacker who controls the agent binary.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentproof.sensitive import SECRET_PATTERNS

# What the enforcer blocks is, by construction, exactly what the verifier flags:
# both draw from agentproof.sensitive.SECRET_PATTERNS.
DEFAULT_SENSITIVE_PATTERNS: tuple[str, ...] = SECRET_PATTERNS

# Exit code returned when enforcement itself refuses to run (distinct from any
# code the wrapped command might produce).
ENFORCEMENT_UNAVAILABLE = 78


@dataclass
class GuardProfile:
    """A resolved set of sensitive paths to deny, anchored to a project root."""

    project_root: Path
    patterns: tuple[str, ...] = DEFAULT_SENSITIVE_PATTERNS
    extra_paths: tuple[str, ...] = ()  # absolute or root-relative paths to deny
    deny_regexes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.project_root = self.project_root.resolve()
        if not self.deny_regexes:
            self.deny_regexes = self._build_regexes()

    def _build_regexes(self) -> list[str]:
        # Anchored at the project root, then any depth of subdirs, then the
        # sensitive component. ``(/.*)?`` allows zero or more intermediate dirs
        # without double-counting the slash before the final segment.
        root = re.escape(str(self.project_root))
        regexes: list[str] = []
        for pattern in self.patterns:
            if pattern.endswith("/"):
                # directory marker, e.g. "secrets/" -> the dir and everything in it
                name = re.escape(pattern.rstrip("/"))
                regexes.append(rf"^{root}(/.*)?/{name}(/|$)")
            else:
                # filename containing the pattern, e.g. ".env", ".pem",
                # "credentials", "id_rsa" (matches ".env.local", "key.pem", ...)
                esc = re.escape(pattern)
                regexes.append(rf"^{root}(/.*)?/[^/]*{esc}[^/]*$")
        for extra in self.extra_paths:
            abs_path = (
                Path(extra).resolve()
                if Path(extra).is_absolute()
                else (self.project_root / extra).resolve()
            )
            regexes.append(rf"^{re.escape(str(abs_path))}(/|$)")
        return regexes

    def matches(self, path: Path) -> bool:
        """True if ``path`` resolves to a sensitive location under this profile."""
        target = str(path.resolve())
        return any(re.search(rx, target) for rx in self.deny_regexes)

    def sensitive_targets(self) -> tuple[list[Path], list[Path]]:
        """Enumerate existing sensitive (files, dirs) in the tree.

        Used by enumerate-at-launch backends (bubblewrap). Skips VCS/build dirs
        so the scan stays cheap. Regex backends (sandbox-exec) do not need this.
        """
        skip = {".git", ".agentproof", ".hg", ".svn", "node_modules",
                ".venv", "venv", "__pycache__", "dist", "build"}
        files: list[Path] = []
        dirs: list[Path] = []
        for path in self.project_root.rglob("*"):
            if any(part in skip for part in path.relative_to(self.project_root).parts):
                continue
            if not self.matches(path):
                continue
            (dirs if path.is_dir() else files).append(path)
        return files, dirs


@dataclass
class GuardResult:
    """Outcome of running a command under enforcement."""

    command: list[str]
    backend: str
    enforced: bool
    exit_code: int
    blocked: bool
    stdout: str = ""
    stderr: str = ""

    def to_decision(self) -> dict[str, Any]:
        return {
            "event_type": "enforcement_decision",
            "backend": self.backend,
            "enforced": self.enforced,
            "command": self.command,
            "exit_code": self.exit_code,
            "action_taken": "blocked" if self.blocked else "allowed",
        }


def guard_backend() -> str:
    """Return the enforcement backend available on this host."""
    system = platform.system()
    if system == "Darwin" and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    if system == "Linux" and shutil.which("bwrap"):
        return "bubblewrap"
    return "none"


def guard_supported() -> bool:
    return guard_backend() != "none"


def build_macos_profile(profile: GuardProfile) -> str:
    """Render an SBPL profile that denies read/write/unlink on sensitive paths.

    ``file-write*`` covers create, modify, and unlink (delete); ``file-read*``
    covers open-for-read and metadata. Everything else stays allowed so the
    agent's legitimate work is unaffected.
    """
    lines = ["(version 1)", "(allow default)"]
    if profile.deny_regexes:
        clauses = "\n".join(f'    (regex #"{rx}")' for rx in profile.deny_regexes)
        lines.append("(deny file-read* file-write*\n" + clauses + ")")
    return "\n".join(lines) + "\n"


def run_guarded(
    command: list[str],
    profile: GuardProfile,
    *,
    cwd: Path | None = None,
    timeout: float | None = None,
    require_enforcement: bool = True,
) -> GuardResult:
    """Run ``command`` confined so sensitive paths cannot be read/written/deleted.

    If no backend is available and ``require_enforcement`` is True, the command
    is refused (fail closed) rather than run unprotected.
    """
    backend = guard_backend()
    workdir = cwd or profile.project_root

    if backend == "none":
        if require_enforcement:
            return GuardResult(
                command=command,
                backend="none",
                enforced=False,
                exit_code=ENFORCEMENT_UNAVAILABLE,
                blocked=False,
                stderr="enforcement backend unavailable on this host (fail-closed)",
            )
        completed = subprocess.run(
            command, cwd=str(workdir), capture_output=True, text=True, timeout=timeout
        )
        return GuardResult(
            command=command,
            backend="none",
            enforced=False,
            exit_code=completed.returncode,
            blocked=False,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    if backend == "bubblewrap":
        wrapped = _bubblewrap_argv(command, profile, workdir)
    else:  # sandbox-exec
        wrapped = ["/usr/bin/sandbox-exec", "-p", build_macos_profile(profile), *command]

    completed = subprocess.run(
        wrapped, cwd=str(workdir), capture_output=True, text=True, timeout=timeout
    )
    return GuardResult(
        command=command,
        backend=backend,
        enforced=True,
        exit_code=completed.returncode,
        blocked=_looks_blocked(completed.returncode, completed.stderr),
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _bubblewrap_argv(command: list[str], profile: GuardProfile, workdir: Path) -> list[str]:
    """Build a ``bwrap`` argv that binds the real FS and masks sensitive paths.

    Order matters: bind the root first, then overlay masks so they win. Dirs are
    masked with an empty tmpfs; files are shadowed by a read-only /dev/null so
    reads return empty and writes/unlinks fail.
    """
    files, dirs = profile.sensitive_targets()
    argv = ["bwrap", "--die-with-parent", "--dev-bind", "/", "/"]
    for directory in dirs:
        argv += ["--tmpfs", str(directory)]
    for file in files:
        argv += ["--ro-bind", "/dev/null", str(file)]
    argv += ["--chdir", str(workdir), "--", *command]
    return argv


def _looks_blocked(exit_code: int, stderr: str) -> bool:
    if exit_code == 0:
        return False
    markers = (
        "operation not permitted",  # macOS sandbox / EPERM
        "permission denied",
        "deny file-",
        "read-only file system",  # bubblewrap masked-file write (EROFS)
        "device or resource busy",  # bubblewrap masked-mount unlink (EBUSY)
    )
    lowered = stderr.lower()
    return any(marker in lowered for marker in markers)
