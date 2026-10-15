"""Bounded recovery after the advertiser exhausts its startup retries."""
import fcntl
import json
import math
import os
import subprocess
import time

ADVERTISER = "openaps-locald-advertise.service"
BLE = "openaps-locald-ble.service"
RETRY_TIMER = "openaps-locald-bluetooth-recovery.timer"
COOLDOWN = 120


def connection_table_is_empty(output):
    lines = [line.strip() for line in output.decode("ascii").splitlines() if line.strip()]
    return lines == ["Connections:"]


def recover_once(state_path, run=subprocess.check_call,
                 capture=subprocess.check_output, now=time.monotonic):
    def defer(reason):
        try:
            run(["systemctl", "restart", RETRY_TIMER], timeout=10)
        except (OSError, subprocess.SubprocessError):
            return reason + "_retry_unavailable"
        return reason

    try:
        run(["systemctl", "is-active", "--quiet", ADVERTISER], timeout=5)
        return "already_running"
    except subprocess.CalledProcessError:
        pass
    try:
        status = capture(["systemctl", "show", ADVERTISER, "-p", "ExecMainStatus"], timeout=5)
        if status.strip() != b"ExecMainStatus=75":
            return "failure_not_controller_enable"
        links = capture(["hcitool", "con"], stderr=subprocess.STDOUT, timeout=5)
        if not connection_table_is_empty(links):
            return defer("connections_active_or_unknown")
        instant = now()
        if not math.isfinite(instant) or instant < 0:
            return defer("clock_unavailable")
        try:
            with open(state_path) as handle:
                previous = json.load(handle)["attempted_at"]
            if not math.isfinite(previous) or previous < 0 or instant < previous:
                return defer("clock_unavailable")
            if 0 <= instant - previous < COOLDOWN:
                return defer("cooldown")
        except FileNotFoundError:
            pass
        # /run is cleared on boot. Persist before restarting so a partial
        # failure cannot cause a rapid succession of controller resets.
        with open(state_path + ".new", "w") as handle:
            json.dump({"attempted_at": instant}, handle)
        os.replace(state_path + ".new", state_path)
        run(["systemctl", "reset-failed", ADVERTISER], timeout=5)
        run(["systemctl", "restart", "bluetooth.service"], timeout=30)
        run(["systemctl", "start", BLE], timeout=30)
        return "restart_requested"
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return defer("recovery_deferred")


def main():
    directory = "/run/openaps-locald-bluetooth-recovery"
    os.makedirs(directory, mode=0o700, exist_ok=True)
    with open(os.path.join(directory, "lock"), "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("bluetooth_recovery=already_in_flight")
            return 0
        outcome = recover_once(os.path.join(directory, "attempt.json"))
        print("bluetooth_recovery=" + outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
