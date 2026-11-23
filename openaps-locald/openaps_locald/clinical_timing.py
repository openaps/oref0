"""Best-effort clinical stage durations; never include request content."""
import time


def timed_clinical_call(log, stage, operation):
    started = time.monotonic()
    try:
        return operation()
    finally:
        elapsed_ms = max(0, int((time.monotonic() - started) * 1000))
        if log is not None:
            try:
                log("clinical timing stage=%s elapsed_ms=%d" % (stage, elapsed_ms))
            except Exception:
                # Diagnostics must not change clinical results or exceptions.
                pass
