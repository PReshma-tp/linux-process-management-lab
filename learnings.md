# Linux processes and systemd: quick learning notes

These answers summarize the concepts tested in [`experiments.md`](experiments.md). They use the worker in [`app.py`](app.py) as the running example.

## Basics

**What is a program?**

- A **program** is a set of instructions stored on disk. `app.py` is a Python program.
- Think of it as a recipe written in a book.

**What is a process?**

- A **process is an instance of a program that has been started and is being managed by the operating system**. Running `python app.py` creates one.
- The OS gives it a process ID (PID) and manages its execution state and resources. It exists until it terminates, although it may briefly remain as a zombie until its parent collects its exit status.
- It can sleep or wait between heartbeats without using the CPU. Think of a cook waiting for water to boil: the cooking has not finished.

**What is a system?**

- A **system** is a computer or server running an operating system, along with the programs and resources it manages. A computer running Ubuntu is a Linux system.

**What is a service?**

- A **service is a program managed to provide a particular function**, usually in the background. Nginx serves web requests, PostgreSQL provides database functionality, and a Celery worker processes background tasks.
- A *daemon* is a background program that provides a service. The `.service` file tells systemd how to run this worker.

**What is systemd?**

- **systemd is a system and service manager used in Linux.** It helps initialize the system during boot and starts, stops, and restarts services.
- It can restart a failed worker and start an enabled service after reboot. In this lab, it manages `app.py`.

**What are Linux process management tools?**

- Commands for viewing, monitoring, and controlling processes:
  - `ps` shows processes; `top` monitors processes and resource usage.
  - `pgrep` finds PIDs by name; `kill` sends a signal to a PID, including termination signals.

**Where do Docker and Kubernetes fit?**

- Linux manages processes and system resources; systemd manages system services.
- Docker runs applications in isolated containers; Kubernetes orchestrates containers across machines.
- Applications in Docker containers are still Linux processes. Process behavior helps explain how these tools handle execution and failures.

**How is a shell job different from a process?**

- A process is tracked by the OS with a PID. A job is a command or pipeline tracked by one shell for foreground/background control. One job can contain several processes.

**Why use environment variables?**

- `app.py` reads `HEARTBEAT_INTERVAL`, `DIE_AFTER`, and `MEMORY_TEST_MB` through `os.getenv()`. systemd loads their values from `EnvironmentFile=` when starting the service. Editing that file requires a service restart so the new process receives the new values.

## Signals and exit status

**SIGTERM versus SIGKILL?**

- `SIGTERM` asks a process to terminate. This app catches it, logs shutdown, and exits with status 0.
- `SIGKILL` stops it immediately; the app cannot catch it or run its Python cleanup. systemd sees `status=9/KILL` and restarts the unit under `Restart=on-failure`.

**Why did `echo $?` show 1 or 137?**

- `$?` is the previous shell command's exit status. The simulated crash calls `sys.exit(1)`, so the direct run returns 1.
- Shells commonly report `128 + signal number` for a signal-killed command: SIGKILL is 9, so the shell reported 137. This is a shell convention; the journal showed the signal directly as `status=9/KILL`.

**What is a zombie?**

- A child that has exited but whose parent has not yet collected its exit status. It is marked `Z` in `ps`. `waitpid()` collects it; it is not a live worker consuming CPU.

## Managing the service

**Why doesn't `nohup` give the same reliability as systemd?**

- `nohup` helps a command survive a terminal hangup. It does not by itself restart it after a crash, start it at boot, enforce unit limits, or provide a service status. systemd handles those through the unit configuration.

**What happens after repeated crashes?**

- `Restart=on-failure` and `RestartSec=2` try again after failure. `StartLimitBurst=3` within `StartLimitIntervalSec=30` stops a rapid loop. The unit can then be `failed` with `Start request repeated too quickly`.

**What is the difference between restarting a process and restarting a service?**

- A crashed process can be replaced automatically by systemd according to `Restart=`. `systemctl restart` explicitly stops and starts the *unit*, using its loaded settings and a new process. Unit file edits need `daemon-reload` first; environment file edits need a restart.

**Why does enabling the unit start it on boot?**

- `WantedBy=multi-user.target` names the boot target that should pull in the service. `systemctl enable` creates a link under that target's `.wants` directory. `enable --now` also starts it immediately.

**What happens to child processes when a systemd service stops?**

- Normally systemd stops the processes in the service's cgroup, not just its main PID. A parent should still handle shutdown and reap its own children cleanly. The submitted worker creates no child processes.

**How would a Celery worker finish its current task before shutdown?**

- Give it a graceful SIGTERM and enough `TimeoutStopSec` time for the current task to finish. Verify the worker's own shutdown behavior and task settings; after the timeout, systemd may force termination.

## Limits, diagnostics, and extras

**What did the resource tests teach?**

- `CPUQuota=50%` throttles CPU use; it does not kill the worker. `MemoryMax=60M` limits cgroup memory. A successful `100 MiB` allocation message alone did not prove an OOM kill in the first test; check `memory.events` and the journal. `MemorySwapMax=0` disables swap for this unit.

**Where should I look when a service fails?**

- `systemctl status` for state and result; `journalctl -u testpress-worker -b` for the first error and restart sequence; `systemctl cat` for unit text; `systemctl show` for loaded properties; `systemd-analyze verify` for unit syntax and `systemd-analyze blame` for boot timing.

**What do the service types mean?**

- `Type=simple`: systemd considers the service started after launching its command.
- `Type=exec`: startup waits until the executable has been invoked, so an invalid executable is reported at startup.
- `Type=notify`: the app sends `READY=1`; it can also send `WATCHDOG=1` to prove it is responsive when a watchdog is configured.

**How is a systemd timer like a cron entry?**

- Both schedule work. A cron entry is a schedule plus command in a crontab; a systemd timer activates a separate unit. In the lab, a timer repeatedly started a short `date` service, which exited successfully after each run.
