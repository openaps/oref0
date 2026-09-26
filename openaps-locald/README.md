# openaps-locald

`openaps-locald` is the rig-side local event store and BLE/HTTP bridge used by
OpenAPS-iOS. It stores phone-originated events durably, deduplicates them by
`event_id`, materializes supported events into oref0 inputs, and exposes pump,
device-status, and BG data for offline phone-to-rig sync.

This tree reconciles the previously untracked field copies from the deployed
rigs. Variant selection is deliberate:

- collector control uses exact process matching, ignores zombie processes,
  migrates legacy managed cron entries, and restarts only when configuration or
  process multiplicity requires it;
- pump-history reads skip empty or temporarily malformed candidate files;
- device-status reads include pump status plus freshness-gated clock,
  reservoir, and battery data;
- installed services execute the stable `/usr/local/bin` wrappers, while the
  installer copies this package to `/usr/local/src/oref0/openaps-locald`;
- the installer reproduces both the carb merge and pump-status refresh hooks
  observed on the newer deployments.

## Contract

The HTTP API is rooted at `/v1`. The BLE service and characteristic UUIDs are
defined in `openaps_locald/ble_server.py`; UUID suffixes `0001` through `0008`
cover the service, rig info, status, event write, acknowledgement, pump history,
device status, and BG readings respectively. BLE writes use version-1 JSON
envelopes with base64 chunks.

External event JSON uses `openaps.local.event.v1` and snake_case keys. In
particular, `set_cgm_config` accepts the full OpenAPS-iOS payload while retaining
compatibility with the older transmitter-only payload. BG trend rate accepts
both the legacy `trend_rate_mgdl_min` key and the iOS
`trend_rate_mgdl_minute` key.

Existing rigs retain the deployed Nightscout-derived `patient_id` so upgrades
do not strand queued events or split a fleet. When that primary ID is derived
rather than explicitly configured, the daemon also accepts the equivalent
OpenAPS-iOS canonical host+port ID. A manually configured patient ID remains
exact-only.

Device authorization runs in observational `shadow` mode. Each phone and rig
creates a private P-256 signing key locally, publishes only its signed public
enrollment record through the Nightscout credential it already has, and proves
possession during direct BLE or HTTP sessions. Previously confirmed peer keys
remain usable while Nightscout is temporarily unavailable; direct contact
refreshes continuity without a wall-clock-dependent handshake.

No new token, pairing code, fingerprint comparison, or User ID comparison is
required. The rig reads the existing token from `ns.ini` in memory and does not
copy it into `openaps-locald.json` or logs. OpenAPS-iOS uses its existing saved
Nightscout settings and stores its private key in the device-only Keychain.

Shadow verification does not yet replace the deployed BLE write-key allow/deny
decision. It exercises and records the new path while the legacy path remains
operational. Fail-closed activation remains blocked on the documented
Nightscout durability, atomic identifier uniqueness, revocation semantics, and
deployed-image interoperability gates.

## Test

From the oref0 checkout:

```sh
python3 -m unittest discover -s openaps-locald/tests -p 'test*.py'
```

For a disposable Nightscout compatibility environment with placeholder
create/read/delete and read-only subjects, run the live carrier harness with
environment variables rather than command-line token arguments:

```sh
PYTHONPATH=openaps-locald \
OPENAPS_NS_LAB_URL=http://127.0.0.1:1338 \
OPENAPS_NS_INSECURE_LAB_URL=http://127.0.0.1:1339 \
OPENAPS_NS_PRUNE_LAB_URL=http://127.0.0.1:1340 \
OPENAPS_NS_LAB_TOKEN=placeholder-create-read-delete-token \
OPENAPS_NS_LAB_READ_ONLY_TOKEN=placeholder-read-only-token \
python3 openaps-locald/tests/live_nightscout_authorization.py
```

The live harness creates, soft-deletes, races, prunes, and fault-injects a
lost enrollment response/read-back followed by process restart recovery.
Never point it at a user's Nightscout database.

## Install

Before installation, run the read-only compatibility check from the checkout:

```sh
bin/openaps-locald-authorization-smoke --require-bluez --require-systemd
```

It creates its P-256 test identity only in a temporary directory, does not read
or print Nightscout configuration, and does not change Bluetooth, systemd, or
daemon state. Its JSON report includes the observed crypto CPU/peak-memory
snapshot and the compiled message, chunk, session, and admission limits. Link
encryption and negotiated ATT MTU remain explicitly pending until a phone has
an active BLE session.

When a normal phone-to-rig BLE connection is expected, the optional bounded
passive observation mode records only aggregate connection, encryption, and
ATT-MTU metrics; it retains neither packets nor device identifiers and does not
change Bluetooth state:

```sh
bin/openaps-locald-authorization-smoke --require-bluez --require-systemd \
  --active-link-seconds 300
```

`--active-link-seconds` is capped at 900 seconds. A window with no connection
is reported as `no_active_connection_observed`, not as a failed smoke test.

From the oref0 checkout on a rig:

```sh
sudo bin/openaps-locald-install.sh /root/myopenaps
```

The installer preserves an existing JSON configuration where possible, copies
the package and wrappers into their stable installed paths, installs systemd and
D-Bus definitions, and enables the applicable services and loop hooks.

For the additive phone-to-rig authorization rollout, explicitly enable the
dormant admission, TLS, recovery, and BLE-relay providers during installation:

```sh
sudo OPENAPS_LOCALD_ENABLE_AUTHORIZATION_PROVIDERS=true \
  bin/openaps-locald-install.sh /root/myopenaps
```

This option keeps secure-mode enforcement and BLE authentication requirements
off, so existing legacy HTTP and BLE clients remain compatible.

### BLE service recovery

The local sync service starts its BLE transport, and the BLE transport starts
its external advertiser. `PartOf` propagates planned restarts down this chain;
`Wants` brings dependents back after automatic failure recovery or a subsequent
start. The advertiser remains bound to BLE so it stops when GATT is unavailable.
This prevents a sync/BLE restart from leaving an enabled advertiser stopped
until reboot or manual intervention. Existing `advertise_enabled` configuration
still controls whether the advertiser transmits.

After installing updated units, run `systemctl daemon-reload`. Restarting
`openaps-locald` should bring all three services back without separately starting
BLE or advertising. No phone update or re-enrollment is required for this fix.

On a systemd host, the following root-only integration check exercises startup,
planned restarts, forced process failures, and stop/start recovery using isolated
sleep processes. It does not run the daemon, access Bluetooth, or read rig data:

```sh
sudo python3 openaps-locald/tests/integration/check_systemd_recovery.py openaps-locald/systemd
```
