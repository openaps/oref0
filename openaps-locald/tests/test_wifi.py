import os
import tempfile
import threading
import unittest

from openaps_locald.wifi import WiFiService, WiFiError, validate_network, decode_ssid
from openaps_locald.clinical_dispatch import ClinicalReadDispatcher
from openaps_locald.tls_clinical import TLSClinicalSession


class Control(object):
    def __init__(self, fail=None):
        self.commands, self.fail = [], fail

    def command(self, value):
        self.commands.append(value)
        if self.fail and value.startswith(self.fail):
            raise WiFiError("supplicant_rejected")
        return {
            "LIST_NETWORKS": "network id / ssid / bssid / flags\n0\tHome\tany\t[CURRENT]\n1\tDisabled\tany\t[DISABLED]",
            "ADD_NETWORK": "2",
            "STATUS": "wpa_state=COMPLETED\nssid=Meeting\nip_address=192.0.2.10\npsk=never-return-this",
            "SCAN_RESULTS": "bssid / frequency / signal level / flags / ssid\n"
                "00:00:00:00:00:01\t2412\t-50\t[WPA2-PSK-CCMP][ESS]\tMeeting\n"
                "00:00:00:00:00:02\t2412\t-70\t[WPA2-PSK-CCMP][ESS]\tMeeting\n"
                "00:00:00:00:00:03\t2412\t-55\t[WPA2-EAP-CCMP][ESS]\tEnterprise\n"
                "00:00:00:00:00:04\t2412\t-60\t[ESS]\tCafe\\x20Guest\n"
                "00:00:00:00:00:05\t2412\t-60\t[ESS]\t",
        }.get(value, "OK")


class WiFiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = {"wifi_lock_path": os.path.join(self.directory.name, "lock")}
        self.control = Control()
        self.service = WiFiService(self.config, self.control)
        self.network = {"ssid": 'Meeting "Room"', "security": "wpa2_personal",
                        "password": "example-password", "hidden": True}

    def request(self, method, path, body=None, authorize=lambda: None):
        return self.service.request(method, path, body, authorize)

    def test_add_derives_psk_preserves_existing_and_disabled_profiles(self):
        status, body = self.request("POST", "/v1/wifi/networks", self.network)
        self.assertEqual((status, body), (200, {"saved": True, "connection_requested": True}))
        commands = self.control.commands
        self.assertFalse(any("example-password" in command for command in commands))
        self.assertIn("SET_NETWORK 2 ssid " + self.network["ssid"].encode().hex(), commands)
        self.assertIn("SET_NETWORK 2 scan_ssid 1", commands)
        self.assertIn("SET_NETWORK 2 proto RSN", commands)
        self.assertLess(commands.index("SAVE_CONFIG"), commands.index("SELECT_NETWORK 2"))
        self.assertIn("ENABLE_NETWORK 0 no-connect", commands)
        self.assertNotIn("ENABLE_NETWORK 1 no-connect", commands)
        self.assertNotIn("ENABLE_NETWORK all", commands)
        self.assertNotIn("REMOVE_NETWORK 0", commands)

    def test_failed_save_removes_only_new_profile_and_never_switches(self):
        self.control.fail = "SAVE_CONFIG"
        with self.assertRaises(WiFiError):
            self.request("POST", "/v1/wifi/networks", self.network)
        self.assertEqual(self.control.commands[-1], "REMOVE_NETWORK 2")
        self.assertNotIn("SELECT_NETWORK 2", self.control.commands)

    def test_failed_connect_reports_saved_without_claiming_connection(self):
        self.control.fail = "SELECT_NETWORK"
        _, body = self.request("POST", "/v1/wifi/networks", self.network)
        self.assertEqual(body, {"saved": True, "connection_requested": False})
        self.assertIn("ENABLE_NETWORK 0 no-connect", self.control.commands)

    def test_invalid_inputs_have_no_side_effects(self):
        for update in ({"ssid": "x" * 33}, {"ssid": "bad\nssid"}, {"password": "short"},
                       {"security": "enterprise"}, {"hidden": "false"}, {"extra": True}):
            with self.assertRaises(WiFiError):
                self.request("POST", "/v1/wifi/networks", dict(self.network, **update))
        self.assertEqual(self.control.commands, [])

    def test_utf8_boundary_and_open_network(self):
        validate_network(dict(self.network, ssid="é" * 16))
        with self.assertRaises(WiFiError):
            validate_network(dict(self.network, ssid="é" * 17))
        self.request("POST", "/v1/wifi/networks", dict(self.network, security="open", password=""))
        self.assertIn("SET_NETWORK 2 key_mgmt NONE", self.control.commands)
        self.assertFalse(any(" psk " in command for command in self.control.commands))

    def test_revoked_authorization_never_touches_supplicant(self):
        def revoked():
            raise RuntimeError("revoked")
        with self.assertRaises(RuntimeError):
            self.request("POST", "/v1/wifi/networks", self.network, revoked)
        self.assertEqual(self.control.commands, [])

    def test_mid_write_revocation_rolls_back(self):
        calls = [0]
        def authorize():
            calls[0] += 1
            if calls[0] == 4:
                raise RuntimeError("revoked")
        with self.assertRaises(RuntimeError):
            self.request("POST", "/v1/wifi/networks", self.network, authorize)
        self.assertEqual(self.control.commands[-1], "REMOVE_NETWORK 2")
        self.assertNotIn("SAVE_CONFIG", self.control.commands)

    def test_scan_deduplicates_decodes_and_marks_enterprise_unsupported(self):
        _, result = self.request("GET", "/v1/wifi/networks")
        self.assertEqual(result["networks"], [
            {"ssid": "Meeting", "security": "wpa2_personal", "signal_dbm": -50},
            {"ssid": "Enterprise", "security": "unsupported", "signal_dbm": -55},
            {"ssid": "Cafe Guest", "security": "open", "signal_dbm": -60}])

    def test_scan_throttle_and_status_redaction(self):
        self.request("POST", "/v1/wifi/scan", {})
        self.request("POST", "/v1/wifi/scan", {})
        self.assertEqual(self.control.commands.count("SCAN"), 1)
        _, result = self.request("GET", "/v1/wifi")
        self.assertTrue(result["has_ip_address"])
        self.assertNotIn("psk", result)
        self.assertNotIn("ip_address", result)

    def test_legacy_read_cannot_reach_wifi(self):
        reads = ClinicalReadDispatcher(self.config, None, {}, threading.RLock())
        reads.wifi = self.service
        self.assertEqual(reads.read_legacy("/v1/wifi", {}), (404, {"error": "not_found"}))
        self.assertEqual(self.control.commands, [])

    def test_tls_destination_and_authorization_gate(self):
        class TLS(object):
            ready, binding = True, ("phone", "rig")
            def tick(self):
                pass
            def write(self, response):
                self.response = response
        tls = TLS()
        reads = ClinicalReadDispatcher(self.config, None, {}, threading.RLock())
        reads.wifi = self.service
        session = TLSClinicalSession(tls, None, reads)
        request = {"schema": "openaps.tls.request.v1", "request_id": "test",
                   "destination_credential_id": "wrong", "method": "POST",
                   "path": "/v1/wifi/networks", "query": {}, "body": self.network}
        with self.assertRaises(Exception):
            session._dispatch(request)
        self.assertEqual(self.control.commands, [])
        request["destination_credential_id"] = "rig"
        session._dispatch(request)
        self.assertIn(b'"saved":true', tls.response)

    def test_real_tls_provisioning_and_status_without_therapy_events(self):
        from tests.test_clinical_dispatch import ClinicalDispatchTests
        fixture = ClinicalDispatchTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        fixture.handler.clinical_reads.wifi = self.service
        with fixture.tls_pair() as (identity, session, client, incoming, outgoing):
            request = fixture.tls_request(identity, "POST", "/v1/wifi/networks", self.network)
            result = fixture.exchange(session, client, incoming, outgoing, request)
            self.assertEqual(result["body"], {"saved": True, "connection_requested": True})
            result = fixture.exchange(session, client, incoming, outgoing,
                                      fixture.tls_request(identity, "GET", "/v1/wifi"))
            self.assertEqual(result["body"]["state"], "COMPLETED")
            self.assertEqual(fixture.handler.db.list_events(), [])

    def test_busy_and_disabled_have_no_side_effects(self):
        with self.service.serialized():
            other = WiFiService(self.config, self.control)
            with self.assertRaises(WiFiError) as error:
                other.request("GET", "/v1/wifi", None, lambda: None)
            self.assertEqual(error.exception.code, "wifi_busy")
        self.service.enabled = False
        with self.assertRaises(WiFiError):
            self.request("GET", "/v1/wifi")
        self.assertEqual(self.control.commands, [])

    def test_scan_escaped_names_round_trip(self):
        self.assertEqual(decode_ssid('Meeting\\\\Room\\"A\\"'), 'Meeting\\Room"A"')
        self.assertEqual(decode_ssid('Caf\\xc3\\xa9'), 'Café')


if __name__ == "__main__":
    unittest.main()
