from __future__ import print_function

import os
import re
import sqlite3
import stat
import threading

from .authorization_protocol import AuthorizationError


REPLAY_KINDS = set(["hello", "event"])
DEFAULT_MAXIMUM_PER_KIND = 1024
DEFAULT_MAXIMUM_TOTAL = 2048
_AUTHORITY_CONTEXT = re.compile(r"^ns_[0-9a-f]{64}$")
_CREDENTIAL_ID = re.compile(r"^[0-9a-f]{64}$")


class AuthorizationReplayError(AuthorizationError):
    pass


class AuthorizationReplayStore(object):
    """Small cross-process, clock-free replay ledger for shadow protocol v2."""

    def __init__(
        self,
        path,
        maximum_per_kind=DEFAULT_MAXIMUM_PER_KIND,
        maximum_total=DEFAULT_MAXIMUM_TOTAL,
        # BLE and HTTP daemons initialize this shared ledger concurrently on
        # slower Edison storage. Keep startup contention bounded, but long
        # enough that a routine schema transaction does not disable one side.
        busy_timeout_seconds=5.0,
    ):
        self.path = os.path.abspath(path)
        self.maximum_per_kind = int(maximum_per_kind)
        self.maximum_total = int(maximum_total)
        if (
            self.maximum_per_kind < 1 or
            self.maximum_total < self.maximum_per_kind
        ):
            raise AuthorizationReplayError("authorization replay bounds are invalid")
        directory = os.path.dirname(self.path)
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, 0o700)
            except OSError:
                if not os.path.isdir(directory):
                    raise AuthorizationReplayError("authorization replay directory is unavailable")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags, 0o600)
            try:
                metadata = os.fstat(descriptor)
                if not stat.S_ISREG(metadata.st_mode):
                    raise AuthorizationReplayError("authorization replay path is invalid")
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
            self._lock = threading.Lock()
            self._connection = sqlite3.connect(
                self.path,
                timeout=float(busy_timeout_seconds),
                check_same_thread=False,
                isolation_level=None,
            )
            with self._lock:
                self._connection.execute("PRAGMA journal_mode=DELETE")
                self._connection.execute("PRAGMA synchronous=FULL")
                self._connection.execute(
                    "PRAGMA busy_timeout=%d" % max(1, int(float(busy_timeout_seconds) * 1000))
                )
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    self._connection.execute(
                        """
                        CREATE TABLE IF NOT EXISTS authorization_replay (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          kind TEXT NOT NULL,
                          authority_context_id TEXT NOT NULL,
                          credential_id TEXT NOT NULL,
                          message_id TEXT NOT NULL,
                          ack_digest TEXT NOT NULL,
                          UNIQUE (
                            kind,
                            authority_context_id,
                            credential_id,
                            message_id,
                            ack_digest
                          )
                        )
                        """
                    )
                    self._connection.execute("COMMIT")
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
            os.chmod(self.path, 0o600)
            directory_descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except AuthorizationReplayError:
            raise
        except Exception as exc:
            raise AuthorizationReplayError("authorization replay store is unavailable") from exc

    @staticmethod
    def _validate(kind, authority_context_id, credential_id, message_id, ack_digest):
        if kind not in REPLAY_KINDS:
            raise AuthorizationReplayError("authorization replay kind is invalid")
        if (
            not isinstance(authority_context_id, str) or
            not _AUTHORITY_CONTEXT.match(authority_context_id)
        ):
            raise AuthorizationReplayError("authorization replay authority is invalid")
        if not isinstance(credential_id, str) or not _CREDENTIAL_ID.match(credential_id):
            raise AuthorizationReplayError("authorization replay credential is invalid")
        if not isinstance(message_id, str) or not message_id or len(message_id) > 128:
            raise AuthorizationReplayError("authorization replay message is invalid")
        if kind == "hello":
            if ack_digest not in (None, ""):
                raise AuthorizationReplayError("authorization hello replay digest is invalid")
            return ""
        if not isinstance(ack_digest, str) or not _CREDENTIAL_ID.match(ack_digest):
            raise AuthorizationReplayError("authorization event replay digest is invalid")
        return ack_digest

    def consume(
        self,
        kind,
        authority_context_id,
        credential_id,
        message_id,
        ack_digest=None,
    ):
        ack_digest = self._validate(
            kind,
            authority_context_id,
            credential_id,
            message_id,
            ack_digest,
        )
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    self._connection.execute(
                        """
                        INSERT INTO authorization_replay (
                          kind, authority_context_id, credential_id,
                          message_id, ack_digest
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            kind,
                            authority_context_id,
                            credential_id,
                            message_id,
                            ack_digest,
                        ),
                    )
                except sqlite3.IntegrityError:
                    self._connection.execute("ROLLBACK")
                    raise AuthorizationReplayError("authorization message was replayed")
                self._prune_locked(kind)
                self._connection.execute("COMMIT")
                return True
            except AuthorizationReplayError:
                raise
            except Exception as exc:
                try:
                    self._connection.execute("ROLLBACK")
                except Exception:
                    pass
                raise AuthorizationReplayError("authorization replay store is unavailable") from exc

    def _prune_locked(self, kind):
        cutoff = self._connection.execute(
            """
            SELECT id FROM authorization_replay
            WHERE kind = ? ORDER BY id DESC LIMIT 1 OFFSET ?
            """,
            (kind, self.maximum_per_kind - 1),
        ).fetchone()
        if cutoff is not None:
            self._connection.execute(
                "DELETE FROM authorization_replay WHERE kind = ? AND id < ?",
                (kind, cutoff[0]),
            )
        total_cutoff = self._connection.execute(
            """
            SELECT id FROM authorization_replay
            ORDER BY id DESC LIMIT 1 OFFSET ?
            """,
            (self.maximum_total - 1,),
        ).fetchone()
        if total_cutoff is not None:
            self._connection.execute(
                "DELETE FROM authorization_replay WHERE id < ?",
                (total_cutoff[0],),
            )

    def counts(self):
        with self._lock:
            rows = self._connection.execute(
                "SELECT kind, count(*) AS count FROM authorization_replay GROUP BY kind"
            ).fetchall()
        result = {"hello": 0, "event": 0}
        for kind, count in rows:
            result[kind] = count
        result["total"] = sum(result.values())
        return result

    def close(self):
        with self._lock:
            self._connection.close()
