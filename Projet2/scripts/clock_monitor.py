#!/usr/bin/env python3
"""Detects scheduling stalls and wall-clock jumps on the host (WSL2 VM).

Hypothesis under test: the UERANSIM radio-link "signal lost" events (all UEs at once,
lost and re-detected within the same millisecond) are caused by the host, not by the
simulated radio itself: either the VM is briefly frozen (stall), or its wall clock jumps
when Hyper-V resynchronises time. UERANSIM's heartbeat timeout would then fire for every
UE at once.

Every 0.2 s the script compares:
  - the elapsed monotonic time  -> a large value means the process was frozen (stall)
  - the elapsed wall-clock time -> if it differs from the monotonic one, the clock jumped

Events are written in UTC (same time base as the Open5GS/UERANSIM container logs) to
../results/clock-events.log. Run it in the background during the measurement campaign:
    nohup python3 clock_monitor.py >/dev/null 2>&1 &
"""
import datetime
import os
import time

TICK = 0.2
STALL_THRESHOLD = 1.0   # s of monotonic time between two 0.2 s ticks
JUMP_THRESHOLD = 0.5    # s of disagreement between wall clock and monotonic clock
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "clock-events.log")


def log(text):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
    with open(LOG, "a") as f:
        f.write(f"{now}  {text}\n")


log("monitor started")
prev_m, prev_w = time.monotonic(), time.time()
while True:
    time.sleep(TICK)
    m, w = time.monotonic(), time.time()
    dm, dw = m - prev_m, w - prev_w
    if dm > STALL_THRESHOLD:
        log(f"STALL      process frozen for {dm:.2f} s (monotonic)")
    if abs(dw - dm) > JUMP_THRESHOLD:
        log(f"CLOCK JUMP wall clock moved {dw - dm:+.2f} s relative to monotonic time")
    prev_m, prev_w = m, w
