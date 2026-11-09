# Linux process and systemd experiments

This is a record of the commands and results shared during the lab on 6–8 November 2026. The worker is [`app.py`](app.py), managed by [`testpress-worker.service`](testpress-worker.service). Temporary changes used for tests were restored; the committed unit has `Restart=on-failure`, `CPUQuota=50%`, `MemoryMax=60M`, and `MemorySwapMax=0`.

> **Evidence:** The linked images in `evidence/` are the original screenshots from the Windows Screenshots folder, renamed by experiment. They were not edited. The CPU quota and zombie tests still have no matching screenshot here. The reboot evidence was captured across separate lab sessions; see experiment 8.

## Core experiments

### 1. Find the running process

- **Action:** Run `python3 app.py` in one terminal; inspect it from another with `pgrep -af app.py`, `ps`, `top`, and `pstree`.
- **Expected:** The worker has a PID and appears in process listings.
- **Observed:** `pgrep -af app.py` showed the Python command and its PID; `pstree` showed process ancestry. `top` showed live CPU and memory information.
- **Why:** Each launch creates a process that the kernel tracks until it exits. A process can be sleeping between heartbeats and still be running.
- **Evidence:** [PID lookup and signal commands](evidence/03-process-pids-and-signal-commands.png).

### 2. Running systemd service

- **Action:** Start the installed unit with `sudo systemctl start testpress-worker`, then run `systemctl status testpress-worker`.
- **Expected:** An active service with a main PID and heartbeat logs.
- **Observed:** The unit showed `active (running)`, main PID `19901`, the command under `/system.slice/testpress-worker.service`, and `Lub Dub` journal lines.
- **Why:** systemd launched the configured Python command as the dedicated service user and attached its output to the journal.
- **Evidence:** [Running service status](evidence/04-systemd-service-running.png).

### 3. Graceful termination: SIGTERM

- **Action:** Start the service, get its PID with `systemctl status testpress-worker`, then run `sudo kill -SIGTERM <PID>`.
- **Expected:** The Python handler logs shutdown and exits cleanly.
- **Observed:** PID `17323` logged `Shut down - Patient dead... (Graceful shutdown)` and `Cleanup done`; systemd showed `status=0/SUCCESS` and `inactive (dead)`. An unprivileged `kill` first returned `operation not permitted` because the service runs as `testpress-worker`.
- **Why:** The handler catches SIGTERM and lets the loop finish. With `Restart=on-failure`, this successful exit does not trigger a restart.
- **Evidence:** [Service SIGTERM and clean exit](evidence/05-systemd-sigterm-graceful.png); [manual shutdown output](evidence/01-manual-graceful-shutdown.png).

### 4. Forced termination: SIGKILL

- **Action:** Restart the service, then run `sudo kill -SIGKILL <MainPID>`.
- **Expected:** No Python cleanup; systemd treats the death as a failure and restarts it.
- **Observed:** PID `22132` was killed. The journal reported `status=9/KILL` and `Failed with result 'signal'`; after `RestartSec=2`, a new worker ran as PID `22359`.
- **Why:** SIGKILL cannot be handled by Python. systemd sees an unexpected signal termination and applies the restart policy.
- **Evidence:** [Changed PID after SIGKILL](evidence/06-systemd-sigkill-auto-restart.png); [journal failure and restart](evidence/07-sigkill-journal-restart.png); [manual SIGKILL output](evidence/02-manual-sigkill.png).

### 5. Simulated nonzero exit

- **Action:** Set `DIE_AFTER=5` in `/etc/testpress-worker.env`, then `sudo systemctl restart testpress-worker`.
- **Expected:** The fifth heartbeat ends with exit status 1, followed by an automatic restart.
- **Observed:** The worker logged `Murder successful! Patient dead after 5 heartbeats. (Simulated crash)`; systemd recorded `status=1/FAILURE` and started a new PID.
- **Why:** `sys.exit(1)` marks an application failure. The message goes to stderr and appears in the journal.
- **Evidence:** [Crash message and automatic restart](evidence/08-simulated-crash-auto-restart.png).

### 6. Invalid executable and script paths

- **Action:** Temporarily change `ExecStart` to `/usr/bin/python-not-exist ...`, run `sudo systemctl daemon-reload`, then restart. A separate test used a wrong `app.py` path.
- **Expected:** Startup fails, and the journal identifies the bad path.
- **Observed:** The missing interpreter produced `Failed at step EXEC` and `status=203/EXEC`. The wrong script path let Python start, but Python reported `can't open file` and exited with status 2.
- **Why:** A missing executable prevents systemd from launching the command; a missing script is an error *inside* a successfully launched Python process. Unit edits require `daemon-reload` before restart; the journal showed a warning when this was skipped.
- **Evidence:** [Invalid script path](evidence/09-invalid-script-path.png); [invalid executable and restart limit](evidence/10-invalid-executable-rate-limit.png); [failed status with `203/EXEC` and error logs](evidence/15-invalid-executable-failed-status.png). The correct paths were restored afterward.

### 7. Repeated crashes and rate limiting

- **Action:** Set `DIE_AFTER=2` and restart with `StartLimitIntervalSec=30`, `StartLimitBurst=3`, and `RestartSec=2`.
- **Expected:** Several quick failures, then systemd stops trying within the configured window.
- **Observed:** The journal showed repeated `status=1/FAILURE`, restart attempts, then `Start request repeated too quickly`; the unit entered `failed` state. After fixing the cause, `sudo systemctl reset-failed testpress-worker` and restart restored it.
- **Why:** `RestartSec` is the delay between attempts. `StartLimitIntervalSec` is the time window used to count starts; `StartLimitBurst` is the allowed number of starts in that window. `reset-failed` clears the failed state and start limit counters; it does not fix the underlying error.
- **Evidence:** [Restart attempts and rate limit](evidence/10-invalid-executable-rate-limit.png).

### 8. Start after a reboot

- **Action:** Enable the unit with `sudo systemctl enable testpress-worker`; after a WSL restart, check `systemctl is-active testpress-worker` and `journalctl -b -u testpress-worker`.
- **Expected:** The enabled unit starts in the new boot without a manual `start`.
- **Observed:** `is-active` returned `active`; the journal showed a new `-- Boot ... --` marker followed by `Started Testpress Python Heartbeat Worker` and heartbeats from new PID `209`.
- **Why:** Enabling creates a link under `multi-user.target.wants`, so systemd starts the unit when that target is reached. The boot marker distinguishes this from a normal service restart.
- **Evidence:** The [new boot marker and automatic start](evidence/11-reboot-journal-autostart.png) and [active service shortly afterward](evidence/12-service-active-after-reboot.png) document the 6 November reboot test. A separate [9 November boot time and active status](evidence/17-boot-time-and-current-status.png) shows boot at 01:39 and a service start at 21:04 after a manual restart. This later screenshot confirms the unit was active after boot; the earlier pair shows that it started automatically on the tested reboot.

### 9. CPU and memory limits

- **Action:** Set `CPUQuota=50%`, `MemoryMax=60M`, `MemorySwapMax=0`; set `MEMORY_TEST_MB=100` to make the worker allocate and touch memory. Inspect `systemctl show testpress-worker -p MemoryMax -p MemoryCurrent`, `ps -o pid,rss,vsz,cmd -p <PID>`, and cgroup counters.
- **Expected:** CPU use is throttled; memory pressure eventually triggers a cgroup out-of-memory kill.
- **Observed:** `cpu.max` showed `50000 100000`, confirming a half CPU quota. The initial memory attempt **did not** kill the worker: it kept logging heartbeats while `MemoryCurrent` sat near the limit. After further configuration changes, the screenshot shows `A process of this unit has been killed by the OOM killer` and `Failed with result 'oom-kill'`.
- **Why:** CPU quota slows an overactive process rather than terminating it. An allocation request or high virtual size alone does not prove an OOM kill; use `memory.events` (`oom`, `oom_kill`) and the journal to verify one. `MemorySwapMax=0` prevents this unit from using swap in the submitted configuration.
- **Evidence:** [Loaded 60 MiB limit, zero swap limit, and OOM journal result](evidence/16-memory-limit-and-oom-log.png); [OOM kill and service restart](evidence/13-memory-oom-kill.png).

### 10. Investigate a failed service

- **Action:** During the invalid executable and repeated crash tests, inspect `systemctl status testpress-worker` and `journalctl -u testpress-worker -n 50`.
- **Expected:** Status identifies failure; the journal shows the cause before subsequent restart messages.
- **Observed:** For the invalid executable, status showed `failed` and `203/EXEC`; the journal identified `/usr/bin/python-not-exist`. For rapid crashes, it showed `status=1/FAILURE` followed by `Start request repeated too quickly`.
- **Why:** The unit result says *how* startup failed; earlier journal lines say *what caused it*. Reading only the last restart message can hide the original error.
- **Evidence:** [Failed status and matching executable error](evidence/15-invalid-executable-failed-status.png); [first error and restart limit](evidence/10-invalid-executable-rate-limit.png).

## Bonus experiments

- **Timer:** `testpress-demo.timer` was enabled after its service unit was corrected. `systemctl list-timers --all` showed the next run, and the journal showed repeated `date` executions followed by `Finished` and `Deactivated successfully`. The one-shot command ends each time; the timer schedules its next activation. These demo units are not in this repo.
- **Zombie process:** A short `fork()` example let a child exit while its parent slept without calling `waitpid()`. The child briefly had `Z` state until the parent collected its exit status. The example was run in the chat, but its script is not retained here.
- **Service types and cgroups:** The lab compared `Type=simple`, `Type=exec`, and `Type=notify`; the submitted unit uses `Type=simple`. The active service's cgroup exposed `cpu.max = 50000 100000`. Cgroup limits apply to the unit's processes, not merely to a shell command.
- **Watchdog:** A temporary `Type=notify` configuration sent `WATCHDOG=1` from the Python app and then simulated a 30-second stall. The [watchdog screenshot](evidence/14-watchdog-timeout-restart.png) shows `Watchdog timeout (limit 10s)!`, SIGABRT, `Failed with result 'watchdog'`, and a new PID after restart. The current submitted unit has no `WatchdogSec`, so this test needs the temporary unit settings to reproduce.

## Quick diagnostic sequence

For a worker that fails just after startup:

1. `systemctl status testpress-worker --no-pager` — read state, PID, and result.
2. `journalctl -u testpress-worker -b -n 50 --no-pager` — find the first error before the restart messages.
3. `systemctl cat testpress-worker` and `systemctl show testpress-worker -p ExecStart -p Restart -p NRestarts -p MemoryMax` — compare the loaded configuration with the intended one.
4. Fix the cause; use `sudo systemctl daemon-reload` after a unit edit, then restart. Use `reset-failed` if the start limit still blocks it.
