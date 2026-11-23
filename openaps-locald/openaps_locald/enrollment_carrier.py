"""One retained publication worker; never proof, admission or clinical work.

The injected callback must use the bounded own-publication proof owner. A timed
out callback cannot be force-killed safely, so its slot remains unavailable
until its thread is actually terminal. No retry spawns work behind that slot.
"""
import threading
import math
from .authorization_tls import boottime


class EnrollmentPublicationWorker(object):
    def __init__(self, publisher, clock=boottime):
        if not callable(publisher):
            raise ValueError("publication callback required")
        self.publisher, self.clock = publisher, clock
        self.lock, self.worker = threading.Lock(), None
        self.clock_lock, self.last, self.valid = threading.Lock(), None, True

    def _time(self):
        with self.clock_lock:
            now = self.clock()
            if not self.valid or not math.isfinite(now) or now < 0 or (self.last is not None and now < self.last):
                self.valid = False
                raise ValueError("publication clock unavailable")
            self.last = now
            return now

    def publish(self, challenge, deadline):
        return self.execute(lambda: self.publisher(dict(challenge)), deadline)[0]

    def execute(self, operation, deadline):
        """Shared retained slot for injected publication/reverse operations."""
        if not self.lock.acquire(False):
            return 429, None
        try:
            if self.worker is not None and self.worker.is_alive():
                return 429, None
            try:
                now = self._time()
            except Exception:
                return 503, None
            if not math.isfinite(deadline) or now >= deadline:
                return 503, None
            done, result = threading.Event(), [False, None]
            def work():
                try:
                    if self._time() < deadline:
                        result[1] = operation()
                        result[0] = True
                except Exception:
                    pass # Never expose credential-bearing exception details.
                finally:
                    done.set()
            self.worker = threading.Thread(target=work, name="enrollment-own-publication")
            self.worker.daemon = True
            try:
                self.worker.start()
            except Exception:
                self.worker = None
                return 503, None
        finally:
            self.lock.release()
        try:
            if not done.wait(max(0, deadline - self._time())):
                return 503, None
            return (202, result[1]) if result[0] and self._time() < deadline else (503, None)
        except Exception:
            return 503, None
