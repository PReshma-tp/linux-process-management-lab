
import os
import signal
import sys
import time
import socket

running = True

HEARTBEAT_INTERVAL = float(os.getenv("HEARTBEAT_INTERVAL", "5"))
DIE_AFTER = int(os.getenv("DIE_AFTER", "0"))
MEMORY_TEST_MB = int(os.getenv("MEMORY_TEST_MB", "0"))

def notify_systemd(message):
    address = os.getenv("NOTIFY_SOCKET")
    if not address:
        return

    if address.startswith("@"):
        address = "\0" + address[1:]

    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
        sock.connect(address)
        sock.sendall(message.encode())

if MEMORY_TEST_MB > 0:
    print(f"Allocating {MEMORY_TEST_MB} MiB of memory", flush=True)
    memory = bytearray(MEMORY_TEST_MB * 1024 * 1024)
    for i in range(0, len(memory), 4096):
        memory[i] = 1
    print("Memory allocated", flush=True)

def shutdown(signum, frame):
    global running
    print("\nShut down - Patient dead... (Graceful shutdown)", flush=True)
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


notify_systemd("READY=1")

count = 0

while running:
    count += 1
    print("Lub Dub", flush=True)

    notify_systemd("WATCHDOG=1")
    if DIE_AFTER > 0 and count >= DIE_AFTER:
        print(
            f"💀 Murder successful! Patient dead after {count} heartbeats. "
            "(Simulated crash)",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    time.sleep(HEARTBEAT_INTERVAL)

print("Cleanup done", flush=True)

