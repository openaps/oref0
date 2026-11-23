#!/usr/bin/env python3
"""Verify startup-limit recovery wiring using inert units, never Bluetooth."""
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    if os.geteuid() != 0:
        raise SystemExit("Run on a root systemd test host.")
    prefix = "openaps-controller-test-" + str(os.getpid())
    root = Path("/run/systemd/system")
    advertiser = prefix + "-advertise.service"
    helper = prefix + "-recover.service"
    marker = Path("/run/" + prefix + "-fired")
    names = [advertiser, helper]
    def ctl(*args):
        return subprocess.check_output(["systemctl"] + list(args)).decode().strip()
    try:
        source = (Path(sys.argv[1]) / "openaps-locald-advertise.service").read_text()
        section = source.split("[Service]", 1)[0]
        section = "\n".join(line for line in section.splitlines()
                            if not line.startswith(("After=", "Requires=", "BindsTo=", "PartOf=")))
        section = section.replace("openaps-locald-bluetooth-recovery.service", helper)
        (root / advertiser).write_text(section + "\n[Service]\nType=simple\n"
                                      "ExecStart=/bin/sh -c 'exit 75'\nRestart=on-failure\nRestartSec=1\n")
        (root / helper).write_text("[Service]\nType=oneshot\nExecStart=/usr/bin/touch " + str(marker) + "\n")
        ctl("daemon-reload")
        ctl("start", advertiser)
        deadline = time.time() + 30
        while not marker.exists() and time.time() < deadline:
            time.sleep(0.25)
        assert marker.exists(), "startup-limit recovery did not fire"
        assert ctl("show", advertiser, "-p", "ExecMainStatus") == "ExecMainStatus=75"
        print("PASS repeated startup failure invokes isolated recovery and retains exit status")
    finally:
        subprocess.call(["systemctl", "stop"] + names)
        for name in names:
            path = root / name
            if path.exists():
                path.unlink()
        if marker.exists():
            marker.unlink()
        ctl("daemon-reload")
        subprocess.call(["systemctl", "reset-failed"] + names,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
