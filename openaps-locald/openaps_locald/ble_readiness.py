"""Read-only deployment readiness: never accept a previous process's health."""
import argparse
import json
import time


def readiness_failure(health, expected_pid, characteristic):
    if health.get("pid") != expected_pid:
        return "health_process_mismatch"
    if health.get("gatt_registered") is not True:
        return "gatt_not_registered"
    if characteristic not in health.get("characteristics", []):
        return "required_characteristic_missing"
    return None


def wait_until_ready(read_health, expected_pid, characteristic, timeout=90,
                     monotonic=time.monotonic, sleep=time.sleep):
    if expected_pid <= 0 or not 1 <= timeout <= 180:
        raise ValueError("invalid_readiness_bounds")
    deadline = monotonic() + timeout
    failure = "health_unavailable"
    while monotonic() < deadline:
        try:
            health = read_health()
            failure = readiness_failure(health, expected_pid, characteristic)
        except (IOError, ValueError, TypeError, AttributeError):
            failure = "health_unavailable"
        if failure is None:
            return
        sleep(min(1, max(0, deadline - monotonic())))
    raise RuntimeError("ble_readiness_timeout:" + failure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--health-path", required=True)
    parser.add_argument("--expected-pid", type=int, required=True)
    parser.add_argument("--required-characteristic", required=True)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    def read_health():
        with open(args.health_path) as handle:
            return json.load(handle)

    try:
        wait_until_ready(read_health, args.expected_pid,
                         args.required_characteristic, args.timeout)
    except (ValueError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")
    print("ble_readiness_verified")


if __name__ == "__main__":
    main()
