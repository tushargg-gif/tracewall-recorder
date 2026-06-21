# macOS validation (P0.2 + daemon)

The daemon runtime and the service-file generation are tested in CI and were smoke-tested live on Linux (ping + a `cat .env` → `deny` decision at ~0.16 ms warm). The two things that can **only** be confirmed on a real Mac are: `launchctl` actually loading the LaunchAgent, and it **auto-starting on login**. This is that checklist — copy-paste each block and compare against "expect".

Prereqs: Python 3.10+, this repo checked out. Takes ~5 minutes.

## 1. Install

```bash
cd /path/to/agent-performance-monitor
pip install -e .
mkdir -p /tmp/ap-demo && cd /tmp/ap-demo
tracewall init
printf 'SECRET=hunter2\n' > .env        # a fake secret for the smoke test
```

**Expect:** `init` prints that it created `.tracewall/`.

## 2. Install the daemon as a launchd service

```bash
tracewall daemon install
ls ~/Library/LaunchAgents/dev.tracewall.daemon.plist
launchctl list | grep tracewall
```

**Expect:** the install prints "installed as a launchd service and started" (or, if `launchctl` is fussy, the path + a manual `launchctl load` hint); the plist exists; `launchctl list` shows a `dev.tracewall.daemon` row with a PID.

## 3. Confirm it's running and answering

```bash
tracewall daemon status
printf '{"tool_name":"Bash","tool_input":{"command":"cat .env"}}' \
  | tracewall hook --source claude-code
```

**Expect:** `status` shows `"running": true` with a socket path; the hook returns JSON whose `permissionDecision` is **`deny`** (reading `.env` is blocked by default) — and it should feel instant (the warm daemon, no Python cold start).

## 4. The real test — auto-start on login

```bash
# Option A (fast): kill the process, confirm launchd respawns it (KeepAlive)
kill "$(launchctl list | awk '/dev.tracewall.daemon/{print $1}')"
sleep 2 && tracewall daemon status      # expect: still running (new PID)

# Option B (full): log out and back in (or reboot), then:
tracewall daemon status                 # expect: running, without you starting it
```

**Expect:** the daemon is running again **without you starting it** — that's `KeepAlive`/`RunAtLoad` doing their job, and the proof that governance is independent of any editor.

## 5. Guard (macOS sandbox-exec) — optional but worth it

```bash
tracewall guard -- bash -c 'cat /tmp/ap-demo/.env'
tracewall flow                          # look for an os.file.denied entry
```

**Expect:** the read is denied by the OS sandbox and shows up as an `os.file.denied` action in the flow — ground-truth enforcement, no agent cooperation needed. (If `sandbox-exec` is unavailable, `guard` fails closed rather than running unprotected.)

## 6. Clean up

```bash
tracewall daemon uninstall
rm -rf /tmp/ap-demo
```

**Expect:** "Removed launchd unit"; `launchctl list | grep tracewall` is now empty.

---

If any step diverges from "expect", capture the command + output — that's the bug report. The most likely friction point is step 2 (`launchctl load` semantics vary across macOS versions); if `install` reports it couldn't auto-load, run the printed `launchctl load -w …` line by hand and re-check step 3.
