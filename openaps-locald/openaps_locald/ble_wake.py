"""Optional, data-free BLE scheduling hints. No clinical or trust state."""
import threading


def wake_interval(config):
    value = config.get("ble_background_wake_interval_seconds", 60)
    try:
        if isinstance(value, bool):
            return 60
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        return 60
    return min(300, max(30, value))


class BackgroundWakeTicker(object):
    """Own one GLib source; a retired subscription cannot emit again.

    The injected scheduler must enqueue callbacks, never invoke them inline.
    Production callbacks run on the existing GLib loop. The lock also orders
    shutdown from the service owner against a callback already in progress.
    """
    def __init__(self, interval, add_timeout, remove_source, emit):
        self.interval = interval
        self.add_timeout = add_timeout
        self.remove_source = remove_source
        self.emit = emit
        self.lock = threading.RLock()
        self.source = None
        self.epoch = 0
        self.counter = 0
        self.closed = False

    def start(self):
        with self.lock:
            if self.closed:
                return False
            if self.source is not None:
                return True
            self.epoch += 1
            epoch = self.epoch
            self.source = self.add_timeout(self.interval, lambda: self._tick(epoch))
            return True

    def _tick(self, epoch):
        with self.lock:
            if self.closed or self.source is None or epoch != self.epoch:
                return False
            self.counter = (self.counter + 1) % 256
            try:
                # Version, process-local rolling tick. Neither byte represents
                # data availability, identity, authorization, or clinical data.
                self.emit(bytes(bytearray((1, self.counter))))
            except Exception:
                # A failed notification retires this source; do not create a
                # retry loop or let a stale callback survive resubscription.
                self.source = None
                self.epoch += 1
                return False
            return True

    def stop(self):
        with self.lock:
            self.epoch += 1
            source, self.source = self.source, None
            if source is not None:
                self.remove_source(source)

    def close(self):
        with self.lock:
            self.closed = True
            self.stop()
