from __future__ import print_function

import json
import base64
from collections import OrderedDict
import fcntl
import hashlib
import math
import os
import random
import re
import tempfile
import threading
import time
import uuid
try:
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote, urlencode, urlparse, urlunparse
    from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
except ImportError:
    from urllib2 import HTTPError, URLError, Request, urlopen, build_opener, HTTPRedirectHandler
    from urllib import quote, urlencode
    from urlparse import urlparse, urlunparse

from .authorization_protocol import (
    AuthorizationError,
    LEGACY_V1_AUTHENTICATED_CARRIER,
    build_enrollment_record,
    realm_id_for_nightscout,
    registry_identifier,
    validate_enrollment_document,
)
from .device_identity import (
    P256_SPKI_PREFIX,
    credential_id_for_public_key,
    validate_public_key_der,
)


JWT_MAX_LIFETIME_SECONDS = 8 * 60 * 60
JWT_MIN_USABLE_SECONDS = 30
JWT_BACKOFF_SECONDS = 5 * 60
HTTP_TIMEOUT_SECONDS = 20
DUPLICATE_AUDIT_LIMIT = 100
PEER_NEGATIVE_CACHE_SECONDS = 5 * 60
AMBIGUOUS_CREATE_RETRY_SECONDS = 6 * 60 * 60
MAX_PEER_NEGATIVE_CACHE_ENTRIES = 128
MAX_SHADOW_STATE_BYTES = 1024 * 1024
SHADOW_STATE_SCHEMA_V1 = "openaps.auth-shadow-state.v1"
SHADOW_STATE_SCHEMA_V2 = "openaps.auth-shadow-state.v2"
_AUTHORITY_CONTEXT_RE = re.compile(r"^ns_[0-9a-f]{64}$")
_CREDENTIAL_ID_RE = re.compile(r"^[0-9a-f]{64}$")
_TRUST_DEVICE_KINDS = set(["phone", "rig"])


def _positive_integral_timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        numeric = float(value)
    except (OverflowError, ValueError):
        return False
    return math.isfinite(numeric) and value > 0 and numeric.is_integer()


def _persisted_elapsed_is_within(now, then, interval):
    if (
        isinstance(now, bool) or
        isinstance(then, bool) or
        not isinstance(now, (int, float)) or
        not isinstance(then, (int, float))
    ):
        return False
    try:
        elapsed = float(now) - float(then)
    except (OverflowError, ValueError):
        return False
    # Wall-clock uncertainty never suppresses a refresh. This cadence is only
    # an optimization; future or non-finite timestamps fail toward retrying.
    return math.isfinite(elapsed) and elapsed >= 0 and elapsed < float(interval)


class NightscoutAuthorizationError(Exception):
    def __init__(self, category, message=None, status=None):
        Exception.__init__(self, message or category)
        self.category = category
        self.status = status


def _redacted_origin(value):
    parsed = urlparse(value)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _result_body(payload):
    if isinstance(payload, dict) and "result" in payload:
        return payload.get("result")
    return payload


def _decode_jwt_payload(token):
    if not isinstance(token, str) or not token or len(token) > 16 * 1024:
        raise NightscoutAuthorizationError("invalid_jwt_exchange")
    segments = token.split(".")
    if len(segments) != 3 or not segments[1] or len(segments[1]) > 32 * 1024:
        raise NightscoutAuthorizationError("invalid_jwt_exchange")
    encoded = segments[1].replace("-", "+").replace("_", "/")
    remainder = len(encoded) % 4
    if remainder == 1:
        raise NightscoutAuthorizationError("invalid_jwt_exchange")
    encoded += "=" * ((4 - remainder) % 4)
    try:
        decoded = base64.b64decode(encoded.encode("ascii"), validate=True)
        if len(decoded) > 16 * 1024:
            raise ValueError("oversized JWT payload")
        payload = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise NightscoutAuthorizationError("invalid_jwt_exchange") from exc
    if not isinstance(payload, dict):
        raise NightscoutAuthorizationError("invalid_jwt_exchange")
    return payload


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class URLTransport(object):
    def __init__(self, base_url, timeout=HTTP_TIMEOUT_SECONDS, opener=None,
                 response_limit=1024 * 1024, require_https=False,
                 allow_insecure_http=False):
        if type(response_limit) is not int or not 0 < response_limit <= 1024 * 1024:
            raise NightscoutAuthorizationError("invalid_response_limit")
        strict_proof = require_https or allow_insecure_http
        if strict_proof:
            parsed = urlparse(base_url)
            allowed_schemes = ("https", "http") if allow_insecure_http else ("https",)
            if (parsed.scheme not in allowed_schemes or not parsed.hostname or parsed.username is not None or
                    parsed.password is not None or parsed.query or parsed.fragment):
                raise NightscoutAuthorizationError("insecure_proof_authority")
        self.base_url = _redacted_origin(base_url)
        self.timeout = timeout
        # Injection is exclusively a test seam; production secure requests use
        # default certificate verification and never forward credentials on redirects.
        self.opener = opener or (build_opener(_RejectRedirects()).open if strict_proof else None)
        self.response_limit = response_limit
        self.require_https = require_https
        self.reject_redirects = strict_proof

    def _url(self, path, query=None):
        parsed = urlparse(self.base_url)
        base_path = parsed.path.rstrip("/")
        endpoint = path if path.startswith("/") else "/" + path
        query_text = urlencode(query or {})
        return urlunparse((parsed.scheme, parsed.netloc, base_path + endpoint, "", query_text, ""))

    def request(self, method, path, body=None, bearer=None, query=None, api_secret=None):
        status, raw = self.request_bytes(method, path, body=body, bearer=bearer, query=query, api_secret=api_secret)
        if not raw:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise NightscoutAuthorizationError("malformed_response") from exc

    def request_bytes(self, method, path, body=None, bearer=None, query=None, api_secret=None):
        """Bound bytes during reads; proof envelopes must use their strict decoder.

        Timeout is the existing socket timeout, not a whole-workflow deadline.
        The proof owner must enforce its suspend-aware overall deadline separately.
        """
        headers = {"Accept": "application/json"}
        data = None
        if bearer:
            headers["Authorization"] = "Bearer " + bearer
        if api_secret:
            headers["api-secret"] = api_secret
        if body is not None:
            data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._url(path, query=query), data=data, headers=headers)
        request.get_method = lambda: method
        try:
            response = (self.opener or urlopen)(request, timeout=self.timeout)
            try:
                status = response.getcode()
                raw = response.read(self.response_limit + 1)
            finally:
                response.close()
        except HTTPError as exc:
            status = exc.code
            try:
                raw = exc.read(self.response_limit + 1)
            finally:
                exc.close()
        except (URLError, OSError) as exc:
            raise NightscoutAuthorizationError("network", "Nightscout request failed") from exc
        if len(raw) > self.response_limit:
            raise NightscoutAuthorizationError("oversized_response")
        if self.reject_redirects and 300 <= status < 400:
            raise NightscoutAuthorizationError("proof_redirect_rejected", status=status)
        return status, raw


class TemporaryJWTProvider(object):
    def __init__(self, transport, access_token, monotonic=None):
        self.transport = transport
        self.access_token = (
            access_token[len("token="):] if isinstance(access_token, str) and access_token.startswith("token=")
            else access_token
        )
        self.monotonic = monotonic or time.monotonic
        self.token = None
        self.subject = None
        self.renew_at = 0.0
        self.backoff_until = 0.0
        self.generation = 0
        self._lock = threading.Lock()

    def invalidate(self):
        with self._lock:
            self.token = None
            self.renew_at = 0.0
            self.generation += 1

    def reject(self):
        with self._lock:
            self.token = None
            self.renew_at = 0.0
            self.generation += 1
            self.backoff_until = self.monotonic() + JWT_BACKOFF_SECONDS

    def invalidate_if_current(self, lease):
        with self._lock:
            if (
                not isinstance(lease, TemporaryJWTLease) or
                lease.generation != self.generation or
                lease.token != self.token
            ):
                return False
            self.token = None
            self.renew_at = 0.0
            self.generation += 1
            return True

    def reject_if_current(self, lease):
        with self._lock:
            if (
                not isinstance(lease, TemporaryJWTLease) or
                lease.generation != self.generation or
                lease.token != self.token
            ):
                return False
            self.token = None
            self.renew_at = 0.0
            self.generation += 1
            self.backoff_until = self.monotonic() + JWT_BACKOFF_SECONDS
            return True

    def get_lease(self, force=False):
        with self._lock:
            now = self.monotonic()
            if not force and self.token and now < self.renew_at:
                return TemporaryJWTLease(self.token, self.generation)
            if now < self.backoff_until:
                raise NightscoutAuthorizationError("jwt_backoff")
            if not isinstance(self.access_token, str) or not self.access_token:
                raise NightscoutAuthorizationError("missing_access_token")
            started = self.monotonic()
            try:
                status, payload = self.transport.request(
                    "GET",
                    "/api/v2/authorization/request/" + quote(self.access_token, safe=""),
                )
                round_trip = max(0.0, self.monotonic() - started)
                if status != 200 or not isinstance(payload, dict):
                    raise NightscoutAuthorizationError("jwt_exchange", status=status)
                token = payload.get("token")
                claims = _decode_jwt_payload(token)
                issued_at = payload.get("iat", claims.get("iat"))
                expires_at = payload.get("exp", claims.get("exp"))
                subject = payload.get("sub") or claims.get("sub")
                if (
                    not isinstance(token, str) or not token or
                    claims.get("accessToken") != self.access_token or
                    not isinstance(issued_at, int) or isinstance(issued_at, bool) or
                    not isinstance(expires_at, int) or isinstance(expires_at, bool) or
                    expires_at <= issued_at or
                    not isinstance(subject, str) or not subject
                ):
                    raise NightscoutAuthorizationError("invalid_jwt_exchange")
                duration = min(float(expires_at - issued_at), float(JWT_MAX_LIFETIME_SECONDS))
                safety = max(30.0, min(5 * 60.0, duration * 0.1))
                usable = duration - round_trip - safety
                if usable < JWT_MIN_USABLE_SECONDS:
                    raise NightscoutAuthorizationError("jwt_lifetime_too_short")
                self.token = token
                self.subject = subject
                self.renew_at = self.monotonic() + usable
                self.backoff_until = 0.0
                self.generation += 1
                return TemporaryJWTLease(self.token, self.generation)
            except Exception:
                self.token = None
                self.renew_at = 0.0
                self.backoff_until = self.monotonic() + JWT_BACKOFF_SECONDS
                raise

    def get(self, force=False):
        return self.get_lease(force=force).token


class TemporaryJWTLease(object):
    def __init__(self, token, generation):
        self.token = token
        self.generation = generation


class ShadowTrustStore(object):
    def __init__(
        self,
        path,
        wallclock=None,
        authority_context_id=None,
        local_credential_id=None,
        local_device_kind=None,
        identity=None,
    ):
        self.path = path
        self.lock_path = path + ".lock"
        self.wallclock = wallclock or time.time
        self.identity = identity
        self.authority_context_id = authority_context_id
        self.local_credential_id = local_credential_id
        self.local_device_kind = local_device_kind
        if identity is not None:
            if self.local_credential_id is None:
                self.local_credential_id = identity.credential_id
            elif self.local_credential_id != identity.credential_id:
                raise ValueError("local trust credential does not match identity")
        if self.authority_context_id is not None and not self._valid_authority(self.authority_context_id):
            raise ValueError("local trust authority is invalid")
        if self.local_credential_id is not None and not self._valid_credential(self.local_credential_id):
            raise ValueError("local trust credential is invalid")
        if self.local_device_kind is not None and self.local_device_kind not in _TRUST_DEVICE_KINDS:
            raise ValueError("local trust device kind is invalid")
        self._lock = threading.Lock()
        self._state = self._empty_state()
        self._persistence_blocked = False
        self._read_current()

    @staticmethod
    def _empty_state():
        return {
            "schema": SHADOW_STATE_SCHEMA_V2,
            "peers": {},
            "self": {},
            "quarantine": {"peers": {}, "self": {}, "state": {}},
        }

    @staticmethod
    def _valid_authority(value):
        return isinstance(value, str) and bool(_AUTHORITY_CONTEXT_RE.match(value))

    @staticmethod
    def _valid_credential(value):
        return isinstance(value, str) and bool(_CREDENTIAL_ID_RE.match(value))

    @classmethod
    def _storage_key(cls, authority_context_id, credential_id):
        if not cls._valid_authority(authority_context_id):
            raise ValueError("trust authority is invalid")
        if not cls._valid_credential(credential_id):
            raise ValueError("trust credential is invalid")
        return authority_context_id + ":" + credential_id

    def _require_authority(self, authority_context_id=None):
        authority_context_id = authority_context_id or self.authority_context_id
        if not self._valid_authority(authority_context_id):
            raise ValueError("trust authority scope is required")
        return authority_context_id

    def _require_local_credential(self, credential_id=None):
        credential_id = credential_id or self.local_credential_id
        if not self._valid_credential(credential_id):
            raise ValueError("local trust credential scope is required")
        return credential_id

    @staticmethod
    def _add_quarantine(target, stored_key, record):
        key = str(stored_key)
        candidate = key
        suffix = 2
        while candidate in target:
            candidate = "%s#%d" % (key, suffix)
            suffix += 1
        target[candidate] = record

    def _expected_record_kind(self, section):
        if section == "self":
            return self.local_device_kind
        if self.local_device_kind == "rig":
            return "phone"
        if self.local_device_kind == "phone":
            return "rig"
        return None

    def _validate_cached_record(self, record, section, validate_key_with_openssl=False):
        if not isinstance(record, dict):
            return None
        authority_context_id = record.get("authority_context_id")
        realm_id = record.get("realm_id")
        credential_id = record.get("credential_id")
        device_kind = record.get("device_kind")
        protocol_version = record.get("protocol_version")
        if not self._valid_authority(authority_context_id) or not self._valid_authority(realm_id):
            return None
        if not self._valid_credential(credential_id):
            return None
        if section == "self" and self.local_credential_id is not None and credential_id != self.local_credential_id:
            return None
        expected_kind = self._expected_record_kind(section)
        if (
            device_kind not in _TRUST_DEVICE_KINDS or
            (expected_kind is not None and device_kind != expected_kind) or
            not isinstance(protocol_version, int) or
            isinstance(protocol_version, bool) or
            protocol_version != 1 or
            record.get("registry_identifier") != registry_identifier(credential_id)
        ):
            return None
        encoded_public_key = record.get("public_key_der")
        if not isinstance(encoded_public_key, str):
            return None
        try:
            public_key_der = base64.b64decode(encoded_public_key.encode("ascii"), validate=True)
        except Exception:
            return None
        if (
            base64.b64encode(public_key_der).decode("ascii") != encoded_public_key or
            len(public_key_der) != 91 or
            not public_key_der.startswith(P256_SPKI_PREFIX)
        ):
            return None
        try:
            if validate_key_with_openssl:
                validate_public_key_der(
                    public_key_der,
                    self.identity.openssl_path if self.identity is not None else None,
                    self.identity.openssl_lock_path if self.identity is not None else None,
                )
            if credential_id_for_public_key(public_key_der) != credential_id:
                return None
        except Exception:
            return None
        if section == "self" and self.identity is not None and public_key_der != self.identity.public_key_der:
            return None
        classification = record.get("classification")
        if section == "self" and classification == "present":
            if (
                not _positive_integral_timestamp(record.get("last_registry_srv_created")) or
                not _positive_integral_timestamp(record.get("last_registry_srv_modified"))
            ):
                return None
        if section == "self" and classification == "ambiguous_create":
            if not _positive_integral_timestamp(record.get("ambiguous_create_srv_date")):
                return None
        nightscout_subject = record.get("nightscout_subject")
        if section == "peers":
            if (
                not isinstance(nightscout_subject, str) or
                not nightscout_subject or
                len(nightscout_subject) > 256 or
                not _positive_integral_timestamp(record.get("last_registry_srv_created")) or
                not _positive_integral_timestamp(record.get("last_registry_srv_modified"))
            ):
                return None
        return dict(record)

    def _normalize_collection(
        self,
        records,
        section,
        allow_flat_keys=False,
        allow_legacy_self_key=False,
        validate_keys_with_openssl=False,
    ):
        active = {}
        quarantine = {}
        candidates = {}
        if not isinstance(records, dict):
            self._add_quarantine(quarantine, section, records)
            return active, quarantine
        for stored_key, raw_record in records.items():
            record = self._validate_cached_record(
                raw_record,
                section,
                validate_key_with_openssl=validate_keys_with_openssl,
            )
            if record is None:
                self._add_quarantine(quarantine, stored_key, raw_record)
                continue
            canonical_key = self._storage_key(
                record["authority_context_id"],
                record["credential_id"],
            )
            allowed_key = stored_key == canonical_key
            if allow_flat_keys:
                allowed_key = allowed_key or stored_key == record["credential_id"]
            if allow_legacy_self_key:
                allowed_key = allowed_key or stored_key == "self"
            if not allowed_key:
                self._add_quarantine(quarantine, stored_key, raw_record)
                continue
            candidates.setdefault(canonical_key, []).append((stored_key, record))
        for canonical_key, grouped in candidates.items():
            if len(grouped) != 1:
                for stored_key, record in grouped:
                    self._add_quarantine(quarantine, stored_key, record)
                continue
            active[canonical_key] = grouped[0][1]
        return active, quarantine

    def _enrich_legacy_self_record(self, record):
        if (
            not isinstance(record, dict) or
            self.identity is None or
            self.local_device_kind not in _TRUST_DEVICE_KINDS
        ):
            return None
        authority_context_id = record.get("authority_context_id")
        credential_id = record.get("credential_id")
        if (
            not self._valid_authority(authority_context_id) or
            not self._valid_credential(credential_id) or
            self.authority_context_id != authority_context_id or
            credential_id != self.identity.credential_id or
            (self.local_credential_id is not None and credential_id != self.local_credential_id)
        ):
            return None
        classification = record.get("classification")
        capability = record.get("capability")
        if (
            not isinstance(classification, str) or
            not classification or
            len(classification) > 64 or
            not isinstance(capability, dict)
        ):
            return None
        for field in ("supported", "security_enabled", "read", "create"):
            if field in capability and not isinstance(capability[field], bool):
                return None
        if classification == "present" and not all(
            isinstance(capability.get(field), bool)
            for field in ("supported", "security_enabled", "read", "create")
        ):
            return None
        for field in ("last_attempt_at", "last_success_at"):
            value = record.get(field)
            if value is not None and (
                isinstance(value, bool) or
                not isinstance(value, (int, float)) or
                not math.isfinite(float(value)) or
                value < 0
            ):
                return None
        if "candidate_revocation" in record and not isinstance(record["candidate_revocation"], bool):
            return None
        if "duplicate_state" in record and not isinstance(record["duplicate_state"], str):
            return None

        enriched = dict(record)
        expected = {
            "device_kind": self.local_device_kind,
            "protocol_version": 1,
            "registry_identifier": registry_identifier(credential_id),
            "public_key_der": base64.b64encode(self.identity.public_key_der).decode("ascii"),
        }
        for field, value in expected.items():
            if field in enriched and enriched[field] != value:
                return None
            enriched[field] = value
        if "realm_id" not in enriched:
            # For a self record this is the realm used when the record was
            # enrolled. The earlier format retained that same value as its
            # stored local authority, so no current configuration is inferred.
            enriched["realm_id"] = authority_context_id
        return enriched

    def _migrate_v1(self, payload):
        migrated = self._empty_state()
        legacy_peers = payload.get("peers")
        peers, quarantined_peers = self._normalize_collection(
            legacy_peers,
            "peers",
            allow_flat_keys=True,
        )
        migrated["peers"] = peers
        migrated["quarantine"]["peers"] = quarantined_peers

        legacy_self = payload.get("self")
        if isinstance(legacy_self, dict) and any(
            field in legacy_self
            for field in ("classification", "authority_context_id", "credential_id", "capability")
        ):
            enriched_self = self._enrich_legacy_self_record(legacy_self)
            if enriched_self is not None:
                legacy_self = enriched_self
            legacy_self = {"self": legacy_self}
        self_records, quarantined_self = self._normalize_collection(
            legacy_self,
            "self",
            allow_flat_keys=True,
            allow_legacy_self_key=True,
        )
        migrated["self"] = self_records
        migrated["quarantine"]["self"] = quarantined_self
        return migrated

    def _normalize_v2(self, payload):
        normalized = self._empty_state()
        existing_quarantine = payload.get("quarantine")
        if isinstance(existing_quarantine, dict):
            for section in ("peers", "self", "state"):
                value = existing_quarantine.get(section)
                if isinstance(value, dict):
                    normalized["quarantine"][section] = dict(value)
                elif value is not None:
                    self._add_quarantine(normalized["quarantine"]["state"], section, value)
        elif existing_quarantine is not None:
            self._add_quarantine(
                normalized["quarantine"]["state"],
                "quarantine",
                existing_quarantine,
            )
        for section in ("peers", "self"):
            active, quarantined = self._normalize_collection(payload.get(section), section)
            normalized[section] = active
            for stored_key, record in quarantined.items():
                self._add_quarantine(
                    normalized["quarantine"][section],
                    stored_key,
                    record,
                )
        return normalized

    def _ensure_directory(self):
        directory = os.path.dirname(self.path) or "."
        if not os.path.exists(directory):
            try:
                os.makedirs(directory, 0o700)
            except OSError:
                if not os.path.isdir(directory):
                    raise
        os.chmod(directory, 0o700)
        return directory

    def _quarantine_malformed_state(self, raw):
        bounded = raw[:MAX_SHADOW_STATE_BYTES]
        digest = hashlib.sha256(bounded).hexdigest()[:16]
        quarantine_path = self.path + ".malformed-" + digest
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            descriptor = os.open(quarantine_path, flags, 0o600)
        except OSError:
            # Another daemon may already have preserved the same bytes.
            return
        complete = False
        try:
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(bounded):
                written = os.write(descriptor, bounded[offset:])
                if written <= 0:
                    raise IOError("authorization quarantine write failed")
                offset += written
            os.fsync(descriptor)
            complete = True
        except (IOError, OSError):
            # Preserving malformed bytes is best-effort. A full/read-only
            # filesystem must not let shadow authorization take down the
            # legacy service; the original state file remains untouched and
            # persistence stays blocked by _load().
            pass
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if not complete:
            try:
                os.unlink(quarantine_path)
            except OSError:
                pass

    def _load(self):
        try:
            with open(self.path, "rb") as handle:
                raw = handle.read(MAX_SHADOW_STATE_BYTES + 1)
        except IOError:
            return self._empty_state(), False, False
        if len(raw) > MAX_SHADOW_STATE_BYTES:
            self._quarantine_malformed_state(raw)
            state = self._empty_state()
            state["quarantine"]["state"]["oversized_json"] = {
                "source_schema": "unreadable",
                "preserved_original": True,
            }
            return state, False, True
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError):
            self._quarantine_malformed_state(raw)
            state = self._empty_state()
            state["quarantine"]["state"]["malformed_json"] = {
                "source_schema": "unreadable",
                "preserved_original": True,
            }
            return state, False, True
        if not isinstance(payload, dict):
            state = self._empty_state()
            state["quarantine"]["state"]["invalid_envelope"] = payload
            return state, True, False
        if payload.get("schema") == SHADOW_STATE_SCHEMA_V1:
            return self._migrate_v1(payload), True, False
        if payload.get("schema") == SHADOW_STATE_SCHEMA_V2:
            normalized = self._normalize_v2(payload)
            return normalized, normalized != payload, False
        state = self._empty_state()
        state["quarantine"]["state"]["unknown_schema"] = payload
        return state, True, False

    def _save(self):
        directory = self._ensure_directory()
        descriptor, temporary = tempfile.mkstemp(prefix=".auth-shadow-state-", dir=directory)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                descriptor = None
                json.dump(self._state, handle, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.rename(temporary, self.path)
            os.chmod(self.path, 0o600)
            directory_descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _with_process_lock(self, operation, save, require_persistence=False):
        with self._lock:
            self._ensure_directory()
            with open(self.lock_path, "a+") as process_lock:
                os.chmod(self.lock_path, 0o600)
                fcntl.flock(process_lock.fileno(), fcntl.LOCK_EX)
                self._state, normalized, persistence_blocked = self._load()
                self._persistence_blocked = persistence_blocked
                result = operation(self._state)
                if (save or normalized) and not persistence_blocked:
                    self._save()
                elif save and require_persistence:
                    raise IOError("authorization trust persistence is blocked")
                return result

    def _read_current(self):
        return self._with_process_lock(lambda state: state, save=False)

    def record_self(
        self,
        state,
        authority_context_id=None,
        credential_id=None,
        require_persistence=False,
    ):
        if not isinstance(state, dict):
            raise ValueError("self trust state is invalid")
        state_authority = state.get("authority_context_id")
        authority_context_id = self._require_authority(authority_context_id or state_authority)
        if state_authority is not None and state_authority != authority_context_id:
            raise ValueError("self trust authority mismatch")
        state_credential = state.get("credential_id")
        credential_id = self._require_local_credential(credential_id or state_credential)
        if state_credential is not None and state_credential != credential_id:
            raise ValueError("self trust credential mismatch")
        device_kind = state.get("device_kind") or self.local_device_kind
        if device_kind not in _TRUST_DEVICE_KINDS:
            raise ValueError("self trust device kind is invalid")
        if self.local_device_kind is not None and device_kind != self.local_device_kind:
            raise ValueError("self trust device kind mismatch")
        record = dict(state)
        record.update({
            "authority_context_id": authority_context_id,
            "credential_id": credential_id,
            "device_kind": device_kind,
            "protocol_version": 1,
            "registry_identifier": registry_identifier(credential_id),
        })
        if not record.get("realm_id"):
            record["realm_id"] = authority_context_id
        if self.identity is not None:
            record["public_key_der"] = base64.b64encode(
                self.identity.public_key_der
            ).decode("ascii")
        elif isinstance(record.get("public_key_der"), bytes):
            record["public_key_der"] = base64.b64encode(record["public_key_der"]).decode("ascii")
        record = self._validate_cached_record(
            record,
            "self",
            validate_key_with_openssl=self.identity is None,
        )
        if record is None:
            raise ValueError("self trust state failed validation")
        storage_key = self._storage_key(authority_context_id, credential_id)

        def update(current):
            current["self"][storage_key] = record
        self._with_process_lock(
            update,
            save=True,
            require_persistence=require_persistence,
        )

    def record_peer_confirmation(self, peer, duplicate_state, authority_context_id=None):
        authority_context_id = self._require_authority(authority_context_id)
        credential_id = peer["credential_id"]
        immutable = {
            "credential_id": credential_id,
            "device_kind": peer["device_kind"],
            "authority_context_id": authority_context_id,
            "realm_id": peer["realm_id"],
            "registry_identifier": peer["registry_identifier"],
            "public_key_der": base64.b64encode(peer["public_key_der"]).decode("ascii"),
            "nightscout_subject": peer.get("nightscout_subject"),
            "last_registry_srv_created": peer.get("srv_created"),
            "last_registry_srv_modified": peer.get("srv_modified"),
            "protocol_version": 1,
        }
        # Enrollment verification normally validated this key already. Any
        # defensive OpenSSL revalidation happens before the shared state flock,
        # so a slow verifier cannot block carrier-ready reads in another daemon.
        immutable = self._validate_cached_record(
            immutable,
            "peers",
            validate_key_with_openssl=True,
        )
        if immutable is None:
            raise ValueError("peer trust state failed validation")
        storage_key = self._storage_key(authority_context_id, credential_id)

        def update(current):
            existing = current["peers"].get(storage_key, {})
            now = self.wallclock()
            existing.update(immutable)
            existing.update({
                "first_nightscout_confirmed_at": existing.get("first_nightscout_confirmed_at") or now,
                "last_nightscout_confirmed_at": now,
                "last_registry_check_at": now,
                "last_registry_srv_created": immutable["last_registry_srv_created"],
                "last_registry_srv_modified": immutable["last_registry_srv_modified"],
                "registry_duplicate_state": duplicate_state,
                "candidate_revocation": existing.get("candidate_revocation"),
            })
            validated = self._validate_cached_record(
                existing,
                "peers",
            )
            if validated is None:
                raise ValueError("peer trust state failed validation")
            current["peers"][storage_key] = validated
        self._with_process_lock(update, save=True)

    def record_direct_contact(self, credential_id, authority_context_id=None):
        authority_context_id = self._require_authority(authority_context_id)
        storage_key = self._storage_key(authority_context_id, credential_id)

        def update(current):
            existing = current["peers"].get(storage_key)
            if not existing:
                return
            existing["last_direct_contact_at"] = self.wallclock()
        self._with_process_lock(update, save=True)

    def record_lookup(self, credential_id, classification, duplicate_state=None, authority_context_id=None):
        authority_context_id = self._require_authority(authority_context_id)
        storage_key = self._storage_key(authority_context_id, credential_id)

        def update(current):
            existing = current["peers"].get(storage_key)
            if not existing:
                return
            existing["last_registry_check_at"] = self.wallclock()
            if duplicate_state is not None:
                existing["registry_duplicate_state"] = duplicate_state
            if classification == "candidate_revoked":
                existing["candidate_revocation"] = {
                    "observed_at": self.wallclock(),
                    "evidence": "api-v3-selected-410",
                    "authoritative": False,
                }
        self._with_process_lock(update, save=True)

    def peer(self, credential_id, authority_context_id=None):
        authority_context_id = authority_context_id or self.authority_context_id
        if not self._valid_authority(authority_context_id) or not self._valid_credential(credential_id):
            return None
        storage_key = self._storage_key(authority_context_id, credential_id)

        def read(current):
            value = current["peers"].get(storage_key)
            return dict(value) if value else None
        return self._with_process_lock(read, save=False)

    def self_state(self, authority_context_id=None, credential_id=None):
        authority_context_id = authority_context_id or self.authority_context_id
        credential_id = credential_id or self.local_credential_id
        if not self._valid_authority(authority_context_id) or not self._valid_credential(credential_id):
            return {}
        storage_key = self._storage_key(authority_context_id, credential_id)
        return self._with_process_lock(
            lambda current: dict(current["self"].get(storage_key) or {}),
            save=False,
        )

    def quarantine_state(self):
        return self._with_process_lock(
            lambda current: json.loads(json.dumps(current.get("quarantine") or {})),
            save=False,
        )


class NightscoutDeviceAuthorizationClient(object):
    def __init__(
        self,
        base_url,
        access_token,
        identity,
        device_kind,
        state_path,
        transport=None,
        monotonic=None,
        wallclock=None,
        api_secret=None,
    ):
        self.base_url = _redacted_origin(base_url)
        self.authority_context_id = realm_id_for_nightscout(self.base_url)
        self.identity = identity
        self.device_kind = device_kind
        self.transport = transport or URLTransport(self.base_url)
        self.monotonic = monotonic or time.monotonic
        self.wallclock = wallclock or time.time
        self.api_secret = api_secret if isinstance(api_secret, str) and api_secret else None
        self.jwt = (
            None if self.api_secret else
            TemporaryJWTProvider(self.transport, access_token, monotonic=self.monotonic)
        )
        self.authorization_carrier = (
            LEGACY_V1_AUTHENTICATED_CARRIER if self.api_secret else "nightscout-v3-subject"
        )
        self.trust = ShadowTrustStore(
            state_path,
            wallclock=self.wallclock,
            authority_context_id=self.authority_context_id,
            local_credential_id=self.identity.credential_id,
            local_device_kind=self.device_kind,
            identity=self.identity,
        )
        self._reconcile_lock = threading.Lock()
        self._process_lock_path = state_path + ".reconcile.lock"
        self._negative_cache = OrderedDict()
        self._negative_cache_lock = threading.Lock()

    def _authenticated_request(self, method, path, body=None, query=None):
        if self.api_secret:
            return self.transport.request(
                method,
                path,
                body=body,
                query=query,
                api_secret=self.api_secret,
            )
        lease = self.jwt.get_lease()
        status, payload = self.transport.request(
            method,
            path,
            body=body,
            bearer=lease.token,
            query=query,
        )
        if status == 401:
            # Invalidation is conditional on the token generation used by
            # this request. If another request already refreshed it, reuse
            # that lease instead of clearing or redundantly refreshing it.
            self.jwt.invalidate_if_current(lease)
            replacement = self.jwt.get_lease()
            status, payload = self.transport.request(
                method,
                path,
                body=body,
                bearer=replacement.token,
                query=query,
            )
            if status == 401:
                # A late rejection for an older replacement must not clear a
                # newer JWT or impose its five-minute backoff.
                self.jwt.reject_if_current(replacement)
        return status, payload

    def _negative_cache_hit(self, credential_id, now=None):
        now = self.monotonic() if now is None else now
        with self._negative_cache_lock:
            for stale in [
                key for key, expiry in self._negative_cache.items()
                if now >= expiry
            ]:
                self._negative_cache.pop(stale, None)
            expiry = self._negative_cache.pop(credential_id, None)
            if expiry is None or now >= expiry:
                return False
            self._negative_cache[credential_id] = expiry
            return True

    def _remember_negative_cache(self, credential_id, expiry):
        now = self.monotonic()
        with self._negative_cache_lock:
            for stale in [
                key for key, cached_expiry in self._negative_cache.items()
                if now >= cached_expiry
            ]:
                self._negative_cache.pop(stale, None)
            self._negative_cache.pop(credential_id, None)
            if expiry <= now:
                return
            while len(self._negative_cache) >= MAX_PEER_NEGATIVE_CACHE_ENTRIES:
                self._negative_cache.popitem(last=False)
            self._negative_cache[credential_id] = expiry

    def status(self):
        path = "/api/v1/status.json" if self.api_secret else "/api/v3/status"
        status, payload = self._authenticated_request("GET", path)
        result = _result_body(payload)
        if status != 200 or not isinstance(result, dict):
            raise NightscoutAuthorizationError("status", status=status)
        server_date = result.get("serverTimeEpoch") if self.api_secret else result.get("srvDate")
        if not isinstance(server_date, int) or isinstance(server_date, bool) or server_date < 1:
            raise NightscoutAuthorizationError("server_time")
        if self.api_secret:
            result = dict(result)
            result["srvDate"] = server_date
        return result

    def probe_anonymous_enrollment_write_permissions(self, anonymous_transport=None):
        """Read-only deployment evidence, not sufficient to admit enrolled keys.

        True: known anonymous create/socket permission checks were denied.
        False: at least one check permits public writes. None: inconclusive.
        Do not reuse bearer/API-secret/cookie-bearing transport for these calls.
        """
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or parsed.username or parsed.password:
            return None
        anonymous = anonymous_transport or URLTransport(
            self.base_url, opener=build_opener(_RejectRedirects()).open)
        prefix = "/api/v2/authorization/debug/check/"
        try:
            status, body = self._authenticated_request("GET", prefix + "api:devicestatus:read")
            if status != 200 or not isinstance(body, dict) or body.get("check") is not True:
                return None
            inconclusive = False
            for permission in ("api:devicestatus:create", "api:*:create,update,delete"):
                status, body = anonymous.request("GET", prefix + permission)
                if status == 401:
                    continue
                if status == 200 and isinstance(body, dict) and body.get("check") is True:
                    return False
                inconclusive = True
            return None if inconclusive else True
        except Exception:
            return None

    def capability_probe(self, probe_id=None):
        if self.api_secret:
            return self._legacy_v1_capability_probe(probe_id)
        probe_id = probe_id or ("openaps-auth-capability-probe-" + uuid.uuid4().hex)
        path = "/api/v3/devicestatus/" + quote(probe_id, safe="")
        invalid_body = {"subject": "openaps-auth-capability-probe"}
        unauthenticated_status, _payload = self.transport.request("PUT", path, body=invalid_body)
        if unauthenticated_status != 401:
            return {
                "supported": False,
                "security_enabled": False,
                "read": False,
                "create": False,
                "probe_ordering": "unsupported",
            }
        get_status, _payload = self._authenticated_request("GET", path)
        if get_status != 404:
            return {
                "supported": False,
                "security_enabled": True,
                "read": False,
                "create": False,
                "probe_ordering": "inconclusive",
            }
        put_status, _payload = self._authenticated_request("PUT", path, body=invalid_body)
        final_status, _payload = self._authenticated_request("GET", path)
        if final_status != 404:
            return {
                "supported": False,
                "security_enabled": True,
                "read": True,
                "create": False,
                "probe_ordering": "mutated",
            }
        if put_status == 400:
            create = True
            ordering = "permission_before_validation"
        elif put_status == 403:
            create = False
            ordering = "permission_before_validation"
        else:
            create = False
            ordering = "inconclusive"
        return {
            "supported": ordering == "permission_before_validation",
            "security_enabled": True,
            "read": True,
            "create": create,
            "probe_ordering": ordering,
            "carrier": "nightscout-v3-subject",
        }

    def _legacy_v1_capability_probe(self, probe_id=None):
        probe_id = probe_id or ("openaps-auth-capability-probe-" + uuid.uuid4().hex)
        path = "/api/v1/devicestatus/"
        invalid_body = {"_id": "invalid-openaps-auth-probe"}
        unauthenticated_status, _payload = self.transport.request(
            "POST",
            path,
            body=invalid_body,
        )
        if unauthenticated_status != 401:
            return {
                "supported": False,
                "security_enabled": False,
                "read": False,
                "create": False,
                "probe_ordering": "unsupported",
                "carrier": LEGACY_V1_AUTHENTICATED_CARRIER,
            }
        get_status, get_payload = self._authenticated_request(
            "GET",
            "/api/v1/devicestatus.json",
            query={
                "count": "1",
                "find[identifier]": probe_id,
            },
        )
        read = get_status == 200 and isinstance(get_payload, list) and not get_payload
        post_status, _payload = self._authenticated_request(
            "POST",
            path,
            body=invalid_body,
        )
        final_status, final_payload = self._authenticated_request(
            "GET",
            "/api/v1/devicestatus.json",
            query={
                "count": "1",
                "find[identifier]": probe_id,
            },
        )
        unchanged = final_status == 200 and isinstance(final_payload, list) and not final_payload
        # Current Nightscout returns 400 for the deliberately invalid ObjectID.
        # Older deployed v1 handlers can surface the same post-permission
        # validation failure as 500. It is accepted only when the identical
        # unauthenticated request was 401 and both bounded reads prove that the
        # probe did not mutate the collection.
        create = post_status in (400, 500)
        ordering = (
            "permission_before_validation" if post_status in (400, 401) else
            "permission_before_legacy_500" if post_status == 500 else
            "inconclusive"
        )
        return {
            "supported": bool(
                read and unchanged and ordering in (
                    "permission_before_validation",
                    "permission_before_legacy_500",
                )
            ),
            "security_enabled": True,
            "read": read,
            "create": create,
            "probe_ordering": ordering,
            "carrier": LEGACY_V1_AUTHENTICATED_CARRIER,
        }

    def carrier_ready(self):
        state = self.trust.self_state()
        capability = state.get("capability") or {}
        return bool(
            state.get("classification") == "present" and
            state.get("authority_context_id") == self.authority_context_id and
            state.get("duplicate_state") == "one_live_non_authoritative" and
            _positive_integral_timestamp(state.get("last_registry_srv_created")) and
            _positive_integral_timestamp(state.get("last_registry_srv_modified")) and
            capability.get("supported") and
            capability.get("security_enabled") and
            capability.get("read") and
            capability.get("create")
        )

    def _validate_self_enrollment_authority(self, peer):
        if self.api_secret:
            if peer.get("authorization_carrier") != LEGACY_V1_AUTHENTICATED_CARRIER:
                raise NightscoutAuthorizationError("legacy_carrier_mismatch")
            return
        subject = peer.get("nightscout_subject")
        if not subject:
            raise NightscoutAuthorizationError("missing_server_stamped_subject")
        if subject != self.jwt.subject:
            raise NightscoutAuthorizationError("subject_mismatch")

    def _exact_path(self, credential_id):
        return "/api/v3/devicestatus/" + quote(registry_identifier(credential_id), safe="")

    def exact_lookup(self, credential_id):
        if self.api_secret:
            status, payload = self._authenticated_request(
                "GET",
                "/api/v1/devicestatus.json",
                query={
                    "count": str(DUPLICATE_AUDIT_LIMIT),
                    "find[identifier]": registry_identifier(credential_id),
                },
            )
            if status in (401, 403):
                raise NightscoutAuthorizationError("permission", status=status)
            if status != 200 or not isinstance(payload, list):
                raise NightscoutAuthorizationError("lookup", status=status)
            matching = [
                item for item in payload
                if isinstance(item, dict) and
                item.get("identifier") == registry_identifier(credential_id)
            ]
            if not matching:
                return "absent", None
            return "present", matching[0]
        status, payload = self._authenticated_request("GET", self._exact_path(credential_id))
        if status == 200:
            result = _result_body(payload)
            if not isinstance(result, dict):
                raise NightscoutAuthorizationError("malformed_record")
            return "present", result
        if status == 404:
            return "absent", None
        if status == 410:
            return "candidate_revoked", None
        if status in (401, 403):
            raise NightscoutAuthorizationError("permission", status=status)
        raise NightscoutAuthorizationError("lookup", status=status)

    def duplicate_audit(self, credential_id):
        if self.api_secret:
            status, payload = self._authenticated_request(
                "GET",
                "/api/v1/devicestatus.json",
                query={
                    "count": str(DUPLICATE_AUDIT_LIMIT),
                    "find[identifier]": registry_identifier(credential_id),
                },
            )
            if status != 200 or not isinstance(payload, list):
                return "inconclusive"
            matching = [
                item for item in payload
                if isinstance(item, dict) and
                item.get("identifier") == registry_identifier(credential_id)
            ]
            if len(payload) >= DUPLICATE_AUDIT_LIMIT:
                return "capped"
            if len(matching) > 1:
                return "multiple_live"
            if len(matching) == 1:
                return "one_live_non_authoritative"
            return "zero_live_non_authoritative"
        status, payload = self._authenticated_request(
            "GET",
            "/api/v3/devicestatus",
            query={
                "identifier$eq": registry_identifier(credential_id),
                "limit": str(DUPLICATE_AUDIT_LIMIT),
            },
        )
        result = _result_body(payload)
        if status != 200 or not isinstance(result, list):
            return "inconclusive"
        matching = [item for item in result if isinstance(item, dict) and item.get("identifier") == registry_identifier(credential_id)]
        if len(result) >= DUPLICATE_AUDIT_LIMIT:
            return "capped"
        if len(matching) > 1:
            return "multiple_live"
        if len(matching) == 1:
            return "one_live_non_authoritative"
        return "zero_live_non_authoritative"

    def _with_reconcile_process_lock(self, operation):
        with self._reconcile_lock:
            lock_directory = os.path.dirname(self._process_lock_path)
            if not os.path.exists(lock_directory):
                try:
                    os.makedirs(lock_directory, 0o700)
                except OSError:
                    if not os.path.isdir(lock_directory):
                        raise
            with open(self._process_lock_path, "a") as process_lock:
                os.chmod(self._process_lock_path, 0o600)
                fcntl.flock(process_lock.fileno(), fcntl.LOCK_EX)
                return operation()

    def _reconcile_self_recording_failure(self, cached_state=None):
        cached_state = cached_state or self.trust.self_state()
        try:
            return self._reconcile_self_locked(cached_state)
        except Exception as exc:
            # Persist a cross-process failure throttle without destroying an
            # earlier positive enrollment. Offline continuity remains usable;
            # only another registry attempt is delayed.
            latest_state = {}
            try:
                latest_state = self.trust.self_state()
            except Exception:
                pass
            if (
                latest_state.get("classification") == "ambiguous_create" and
                latest_state.get("authority_context_id") == self.authority_context_id and
                latest_state.get("credential_id") == self.identity.credential_id and
                _positive_integral_timestamp(
                    latest_state.get("ambiguous_create_srv_date")
                )
            ):
                # A create intent is written before the non-atomic PUT. Never
                # let a later transport/process failure overwrite that durable
                # retry barrier with the pre-PUT cached state.
                failure = dict(latest_state)
            else:
                failure = dict(cached_state or {})
            failure.update({
                "mode": "shadow",
                "credential_id": self.identity.credential_id,
                "authority_context_id": self.authority_context_id,
                "last_attempt_at": self.wallclock(),
                "last_attempt_error": getattr(exc, "category", "unexpected"),
            })
            if not failure.get("classification"):
                failure["classification"] = "error"
            if not isinstance(failure.get("capability"), dict):
                failure["capability"] = {}
            try:
                self.trust.record_self(failure)
            except Exception:
                pass
            raise

    def reconcile_self(self):
        return self._with_reconcile_process_lock(
            lambda: self._reconcile_self_recording_failure()
        )

    def reconcile_self_if_due(self, success_interval, failure_interval):
        def reconcile_if_due():
            cached = self.trust.self_state()
            same_scope = bool(
                cached.get("authority_context_id") == self.authority_context_id and
                cached.get("credential_id") == self.identity.credential_id
            )
            if same_scope:
                capability = cached.get("capability") or {}
                carrier_ready = bool(
                    cached.get("classification") == "present" and
                    _positive_integral_timestamp(cached.get("last_registry_srv_created")) and
                    _positive_integral_timestamp(cached.get("last_registry_srv_modified")) and
                    capability.get("supported") and
                    capability.get("security_enabled") and
                    capability.get("read") and
                    capability.get("create")
                )
                now = self.wallclock()
                if (
                    cached.get("classification") == "ambiguous_create" and
                    _persisted_elapsed_is_within(
                        now,
                        cached.get("last_attempt_at"),
                        success_interval,
                    )
                ):
                    return cached
                failed_attempt = bool(
                    cached.get("last_attempt_error") or not carrier_ready
                )
                if failed_attempt and _persisted_elapsed_is_within(
                    now,
                    cached.get("last_attempt_at"),
                    failure_interval,
                ):
                    return cached
                if carrier_ready and _persisted_elapsed_is_within(
                    now,
                    cached.get("last_success_at"),
                    success_interval,
                ):
                    return cached
            return self._reconcile_self_recording_failure(cached)

        return self._with_reconcile_process_lock(reconcile_if_due)

    def _reconcile_self_locked(self, cached_state=None):
        cached_state = cached_state or {}
        prior_ambiguous_server_date = None
        if (
            cached_state.get("classification") == "ambiguous_create" and
            cached_state.get("authority_context_id") == self.authority_context_id and
            cached_state.get("credential_id") == self.identity.credential_id and
            _positive_integral_timestamp(
                cached_state.get("ambiguous_create_srv_date")
            )
        ):
            prior_ambiguous_server_date = cached_state.get(
                "ambiguous_create_srv_date"
            )
        capability = self.capability_probe()
        state = {
            "mode": "shadow",
            "credential_id": self.identity.credential_id,
            "authority_context_id": self.authority_context_id,
            "capability": capability,
            "last_attempt_at": self.wallclock(),
        }
        if (
            not capability.get("supported") or
            not capability.get("security_enabled") or
            not capability.get("read") or
            not capability.get("create")
        ):
            if prior_ambiguous_server_date is not None:
                state.update({
                    "classification": "ambiguous_create",
                    "ambiguous_create_srv_date": prior_ambiguous_server_date,
                    "duplicate_state": cached_state.get("duplicate_state") or "inconclusive",
                    "last_success_at": None,
                    "candidate_revocation": False,
                })
            else:
                state["classification"] = "unsupported"
            self.trust.record_self(state)
            return state
        classification, document = self.exact_lookup(self.identity.credential_id)
        peer = None
        ambiguous_create_srv_date = None
        if classification == "present":
            peer = validate_enrollment_document(
                document,
                self.identity.credential_id,
                self.device_kind,
                self.identity,
            )
            self._validate_self_enrollment_authority(peer)
        elif classification == "absent" and capability.get("create"):
            server_status = self.status()
            current_server_date = server_status["srvDate"]
            create_is_held = bool(
                prior_ambiguous_server_date is not None and
                float(current_server_date) - float(prior_ambiguous_server_date) <
                float(AMBIGUOUS_CREATE_RETRY_SECONDS * 1000)
            )
            if create_is_held:
                # The exact lookup is still useful: a late completion can move
                # this record to present. While it remains absent, however, a
                # persisted server-time marker prevents another non-atomic PUT
                # across process or device restarts.
                classification = "ambiguous_create"
                ambiguous_create_srv_date = prior_ambiguous_server_date
            else:
                body = build_enrollment_record(
                    self.identity,
                    self.device_kind,
                    self.base_url,
                    current_server_date,
                    authorization_carrier=(
                        LEGACY_V1_AUTHENTICATED_CARRIER if self.api_secret else None
                    ),
                )
                if self.api_secret:
                    body.update({
                        "identifier": registry_identifier(self.identity.credential_id),
                        "created_at": server_status.get("serverTime"),
                        "srvCreated": current_server_date,
                        "srvModified": current_server_date,
                    })
                create_intent = dict(state)
                create_intent.update({
                    "classification": "ambiguous_create",
                    "ambiguous_create_srv_date": current_server_date,
                    "duplicate_state": cached_state.get("duplicate_state") or "inconclusive",
                    "last_success_at": None,
                    "candidate_revocation": False,
                })
                try:
                    # This atomic state-file replacement is the write-ahead
                    # barrier for Nightscout's non-atomic create-on-missing
                    # implementation. If it cannot be made durable, no PUT is
                    # allowed to leave this process.
                    self.trust.record_self(
                        create_intent,
                        require_persistence=True,
                    )
                except Exception as exc:
                    raise NightscoutAuthorizationError(
                        "trust_state_unavailable"
                    ) from exc
                try:
                    if self.api_secret:
                        put_status, put_payload = self._authenticated_request(
                            "POST",
                            "/api/v1/devicestatus/",
                            body=body,
                        )
                    else:
                        put_status, put_payload = self._authenticated_request(
                            "PUT",
                            self._exact_path(self.identity.credential_id),
                            body=body,
                        )
                except NightscoutAuthorizationError as exc:
                    if exc.category != "network":
                        raise
                    # The request may have reached Nightscout. The durable
                    # write-ahead marker already prevents another PUT.
                    pass
                else:
                    expected_create_status = 200 if self.api_secret else 201
                    if put_status != expected_create_status:
                        raise NightscoutAuthorizationError("create", status=put_status)
                    # Pinned Nightscout API v3 returns create metadata directly at
                    # the top level: {status, identifier, lastModified}. Do not
                    # accept a test-only nested result document here.
                    if self.api_secret:
                        if not isinstance(put_payload, list) or not put_payload:
                            raise NightscoutAuthorizationError("invalid_create_response")
                    else:
                        response_result = put_payload
                        expected_identifier = registry_identifier(self.identity.credential_id)
                        if (
                            not isinstance(response_result, dict) or
                            response_result.get("status") != 201 or
                            response_result.get("identifier") != expected_identifier or
                            not _positive_integral_timestamp(response_result.get("lastModified"))
                        ):
                            raise NightscoutAuthorizationError("invalid_create_response")
                        if response_result.get("deduplicatedIdentifier") is not None:
                            raise NightscoutAuthorizationError("deduplicated_identifier")

                # Exactly one bounded exact readback is permitted after the
                # PUT attempt. Its own network failure must not be mistaken
                # for another PUT failure and trigger a second readback.
                try:
                    classification, document = self.exact_lookup(
                        self.identity.credential_id
                    )
                except NightscoutAuthorizationError:
                    classification, document = "ambiguous_create", None
                if classification == "present":
                    peer = validate_enrollment_document(
                        document,
                        self.identity.credential_id,
                        self.device_kind,
                        self.identity,
                    )
                    self._validate_self_enrollment_authority(peer)
                else:
                    classification = "ambiguous_create"
                    document = None
                    ambiguous_create_srv_date = current_server_date
        elif prior_ambiguous_server_date is not None:
            # Only an exact, fully validated present record clears a durable
            # pre-PUT ambiguity marker. Absence, 410, and capability changes
            # remain observational while the create outcome is unresolved.
            classification = "ambiguous_create"
            ambiguous_create_srv_date = prior_ambiguous_server_date
        try:
            duplicate_state = self.duplicate_audit(self.identity.credential_id)
        except NightscoutAuthorizationError:
            if classification not in ("ambiguous_create", "present"):
                raise
            # The audit was attempted, but an unavailable registry must not
            # discard the durable ambiguity marker and reopen the PUT retry.
            duplicate_state = "inconclusive"
        state.update({
            "classification": classification,
            "duplicate_state": duplicate_state,
            "last_success_at": self.wallclock() if classification == "present" else None,
            "candidate_revocation": classification == "candidate_revoked",
        })
        if classification == "ambiguous_create":
            state["ambiguous_create_srv_date"] = ambiguous_create_srv_date
        if classification == "present":
            state.update({
                "realm_id": peer["realm_id"],
                "nightscout_subject": peer["nightscout_subject"],
                "last_registry_srv_created": peer["srv_created"],
                "last_registry_srv_modified": peer["srv_modified"],
            })
        self.trust.record_self(state)
        return state

    def lookup_peer(self, credential_id, device_kind):
        cached_peer = self.trust.peer(credential_id)
        if (
            (not cached_peer or cached_peer.get("authority_context_id") != self.authority_context_id) and
            not self.carrier_ready()
        ):
            return {"classification": "inconclusive", "peer": None, "duplicate_state": "inconclusive"}
        now = self.monotonic()
        if self._negative_cache_hit(credential_id, now=now):
            return {"classification": "negative_cached", "peer": None, "duplicate_state": "inconclusive"}
        classification, document = self.exact_lookup(credential_id)
        duplicate_state = self.duplicate_audit(credential_id)
        if classification == "present":
            peer = validate_enrollment_document(document, credential_id, device_kind, self.identity)
            if (
                not peer.get("nightscout_subject") and
                peer.get("authorization_carrier") != LEGACY_V1_AUTHENTICATED_CARRIER
            ):
                raise NightscoutAuthorizationError("missing_server_stamped_subject")
            self.trust.record_peer_confirmation(
                peer,
                duplicate_state,
                authority_context_id=self.authority_context_id,
            )
            return {"classification": classification, "peer": peer, "duplicate_state": duplicate_state}
        if classification == "candidate_revoked":
            self.trust.record_lookup(credential_id, classification, duplicate_state)
        elif classification == "absent":
            self.trust.record_lookup(credential_id, classification, duplicate_state)
            self._remember_negative_cache(
                credential_id,
                now + PEER_NEGATIVE_CACHE_SECONDS,
            )
        return {"classification": classification, "peer": None, "duplicate_state": duplicate_state}
