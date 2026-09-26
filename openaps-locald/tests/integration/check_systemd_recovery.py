#!/usr/bin/env python3
"""Root-only systemd integration check; uses isolated sleep processes, never BLE.

Usage: sudo python3 check_systemd_recovery.py /path/to/systemd/unit/templates
Compatible with the rigs' systemd 232 and Python 3.5.
"""
import os
from pathlib import Path
import subprocess
import sys
import time

PREFIX = 'openaps-recovery-test-' + str(os.getpid()) + '-'
NAMES = ['openaps-locald', 'openaps-locald-ble', 'openaps-locald-advertise']
UNITS = [PREFIX + name + '.service' for name in NAMES]
ROOT = Path('/run/systemd/system')


def ctl(*args):
    return subprocess.check_output(['systemctl'] + list(args)).decode().strip()


def pids():
    return [int(ctl('show', unit, '-p', 'MainPID').split('=', 1)[1]) for unit in UNITS]


def wait_running(previous=None, changed=()):
    deadline = time.time() + 20
    while time.time() < deadline:
        current = pids()
        active = all(ctl('show', unit, '-p', 'ActiveState') == 'ActiveState=active' for unit in UNITS)
        if active and all(current) and all(current[i] != previous[i] for i in changed):
            return current
        time.sleep(0.25)
    raise AssertionError('services did not recover: ' + str(current))


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root on a systemd host.')
    source = Path(sys.argv[1])
    try:
        for name, unit in zip(NAMES, UNITS):
            text = (source / (name + '.service')).read_text()
            # Keep the production dependency graph. Replace hardware/network
            # dependencies and all service commands with inert test processes.
            section = text.split('[Service]', 1)[0]
            section = section.replace('bluetooth.service', '').replace('network-online.target', '')
            for original, replacement in zip(NAMES[::-1], UNITS[::-1]):
                section = section.replace(original + '.service', replacement)
            (ROOT / unit).write_text(section + '[Service]\nType=simple\nExecStart=/bin/sleep infinity\nRestart=on-failure\nRestartSec=1\n')
        ctl('daemon-reload')
        ctl('start', UNITS[0])
        before = wait_running()
        print('PASS start sync starts BLE and advertiser')
        for index, changed in [(1, (1, 2)), (0, (0, 1, 2))]:
            ctl('restart', UNITS[index])
            before = wait_running(before, changed)
            print('PASS restart ' + NAMES[index])
        for index, changed in [(1, (1, 2)), (0, (0, 1, 2))]:
            ctl('kill', '--kill-who=main', '--signal=KILL', UNITS[index])
            before = wait_running(before, changed)
            print('PASS crash recovery ' + NAMES[index])
        ctl('stop', UNITS[0])
        assert pids() == [0, 0, 0], 'dependents stayed running after stop'
        ctl('start', UNITS[0])
        wait_running()
        print('PASS explicit stop/start restores dependents')
    finally:
        subprocess.call(['systemctl', 'stop'] + UNITS)
        for unit in UNITS:
            path = ROOT / unit
            if path.exists():
                path.unlink()
        ctl('daemon-reload')
        subprocess.call(['systemctl', 'reset-failed'] + UNITS, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == '__main__':
    main()
