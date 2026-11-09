# Linux process management and systemd lab

A Python heartbeat worker used to practice Linux processes, signals, service supervision, diagnostics, and resource limits. The worker runs directly under systemd, without Docker or another process manager.

## Files

| Path | Purpose |
| --- | --- |
| [`app.py`](app.py) | Heartbeats, graceful shutdown, simulated failure, and memory test |
| [`testpress-worker.service`](testpress-worker.service) | systemd unit for the worker |
| [`experiments.md`](experiments.md) | Commands, expectations, observations, explanations, and evidence links |
| [`learnings.md`](learnings.md) | Short Q&A notes and demonstration answers |
| [`evidence/`](evidence/) | Original screenshots from the Linux lab |

## Requirements

- Linux with systemd as PID 1 (`ps -p 1 -o comm=` should show `systemd`). The lab was run on Ubuntu under WSL.
- `/usr/bin/python3` and `sudo` access for installing the service.
- The repository must be readable by the dedicated `testpress-worker` user. If it is under a private home directory, grant that user directory traversal permission as shown below.

## Try the worker directly

```bash
cd /path/to/linux-management
/usr/bin/python3 app.py                  # Ctrl+C: graceful shutdown
DIE_AFTER=3 /usr/bin/python3 app.py      # exits with status 1 after 3 heartbeats
echo $?                                  # 1 for the simulated crash
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `HEARTBEAT_INTERVAL` | `5` | Seconds between heartbeats |
| `DIE_AFTER` | `0` | Exit with status 1 after this many heartbeats; `0` disables the crash |
| `MEMORY_TEST_MB` | `0` | Allocate and touch this many MiB at startup; `0` disables the test |

## Install the systemd service

1. Create a dedicated account, if it does not already exist:

   ```bash
   id testpress-worker || sudo useradd --system --no-create-home --shell /usr/sbin/nologin testpress-worker
   ```

2. The committed unit uses `/home/reshma/linux-management`. If your checkout is elsewhere, edit **both** `WorkingDirectory=` and the script path in `ExecStart=` in `testpress-worker.service` to match your absolute path. Keep `/usr/bin/python3` as the executable unless your system Python is elsewhere.

3. If the checkout is below a home directory that other users cannot traverse, install ACL support if needed and grant the service account access to that home directory. For this lab's path:

   ```bash
   sudo apt install acl
   sudo setfacl -m u:testpress-worker:x /home/reshma
   sudo -u testpress-worker /usr/bin/python3 /home/reshma/linux-management/app.py
   # Press Ctrl+C after a few heartbeats.
   ```

   On another machine, replace `/home/reshma` and the script path with your own paths. The worker also needs read access to `app.py` and traversal access to every directory in its path.

4. Create the environment file used by the unit:

   ```bash
   sudo tee /etc/testpress-worker.env >/dev/null <<'EOF'
   HEARTBEAT_INTERVAL=5
   DIE_AFTER=0
   MEMORY_TEST_MB=0
   EOF
   sudo chmod 644 /etc/testpress-worker.env
   ```

5. Install and start the unit:

   ```bash
   sudo cp testpress-worker.service /etc/systemd/system/
   sudo systemd-analyze verify /etc/systemd/system/testpress-worker.service
   sudo systemctl daemon-reload
   sudo systemctl enable --now testpress-worker
   systemctl status testpress-worker --no-pager
   journalctl -u testpress-worker -n 20 --no-pager
   ```

The unit runs as `testpress-worker`, sends stdout and stderr to journald, restarts after failures, and starts at boot. It has `CPUQuota=50%`, `MemoryMax=60M`, and `MemorySwapMax=0`.

## Change settings and investigate failures

After editing `/etc/testpress-worker.env`, restart the service so its new process receives the values:

```bash
sudo systemctl restart testpress-worker
```

After editing `/etc/systemd/system/testpress-worker.service`, reload the unit definition first:

```bash
sudo systemctl daemon-reload
sudo systemctl restart testpress-worker
```

Useful checks:

```bash
systemctl status testpress-worker --no-pager
journalctl -u testpress-worker -b -n 50 --no-pager
systemctl show testpress-worker -p MainPID -p NRestarts -p MemoryMax -p MemoryCurrent
```

See [experiments.md](experiments.md) for the failure tests and their observed results. Restore `DIE_AFTER=0` and `MEMORY_TEST_MB=0` after testing. If repeated failures hit the start limit, fix the cause, then run `sudo systemctl reset-failed testpress-worker` before restarting.

## Reboot check on WSL

From Windows PowerShell, run `wsl --shutdown`, then reopen Ubuntu and check:

```bash
uptime -s
systemctl status testpress-worker --no-pager
journalctl -b -u testpress-worker -n 20 --no-pager
```

Compare the boot time with the service start time. The [reboot experiment](experiments.md#8-start-after-a-reboot) distinguishes its original automatic-start evidence from a later manual restart.
