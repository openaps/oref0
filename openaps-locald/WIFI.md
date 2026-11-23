# Wi-Fi setup over Bluetooth

The iOS Sync screen can scan for nearby networks and add WPA2 Personal or open
networks through the rig's admitted TLS channel, including the Bluetooth TLS
relay when the rig has no IP connectivity. Enroll/authorize the phone and rig
before going offline. Existing admission freshness requirements still apply.
Enterprise, WEP, WPA-only, WPA3-only, and captive-portal login are unsupported.

Update both locald and the iOS app. The rig needs its existing wpa_supplicant
service, a control socket, and `update_config=1` in its supplicant configuration.
The standard root locald service can access the socket and save configuration.
Enable `ble_authorization_tls_relay_enabled` in locald configuration for offline
access. These settings can be overridden in openaps-locald.json:

```json
{
  "wifi_setup_enabled": true,
  "wifi_control_socket": "/var/run/wpa_supplicant/wlan0",
  "wifi_lock_path": "/run/openaps-locald-wifi.lock"
}
```

Only admitted TLS requests expose these paths; legacy bearer HTTP and BLE event
routes do not accept Wi-Fi credentials. All requests remain destination-bound
and recheck live authorization. Credentials never become therapy events.

* `GET /v1/wifi`: supplicant state, current SSID, whether it has an IP address,
  and supported security modes. This does not prove Internet connectivity.
* `POST /v1/wifi/scan` with `{}`: request a scan, throttled to once per 10 seconds.
* `GET /v1/wifi/networks`: latest scan results, strongest first, deduplicated by
  SSID/security; unsupported networks are labeled. Results may be from the prior
  scan while a scan is still running.
* `POST /v1/wifi/networks`: exactly `ssid`, `security` (`wpa2_personal` or `open`),
  `password` (empty for open), and boolean `hidden`. SSID is 1–32 UTF-8 bytes;
  WPA2 passwords are 8–63 printable ASCII characters. Whitespace is preserved.

Credentials go directly to the supplicant Unix socket, never to command-line
arguments or application logs. WPA2 passphrases are derived into PSKs locally.
Existing user profiles are retained. Re-adding an app-managed SSID replaces only
its app-managed profile after the new profile saves. Failed initial saves remove
the new profile and do not request a connection switch. A later failure returns
`saved: true, connection_requested: false`; read status before retrying. A lost
Bluetooth reply can also leave a successfully saved profile: check status first.
The daemon does not restart networking, alter DHCP, or reboot the rig.

Validation without hardware:

```sh
PYTHONPATH=. python3 -m unittest discover -s tests -p 'test_wifi.py'
```

On a test rig, verify scan/select/save, wrong-password status, hidden/open
networks, persistence across reboot, recovery onto an existing network, and BLE
provisioning with no IP route. Do not use production credentials in fixtures or
publish supplicant configuration or raw scan results.
