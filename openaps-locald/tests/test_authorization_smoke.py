from __future__ import print_function

import os
import unittest

try:
    from importlib.machinery import SourceFileLoader
except ImportError:
    SourceFileLoader = None


HERE = os.path.dirname(os.path.realpath(__file__))
SMOKE_PATH = os.path.realpath(
    os.path.join(HERE, "..", "..", "bin", "openaps-locald-authorization-smoke")
)


def _load_smoke_module():
    if SourceFileLoader is not None:
        return SourceFileLoader("openaps_authorization_smoke_test", SMOKE_PATH).load_module()
    import imp
    return imp.load_source("openaps_authorization_smoke_test", SMOKE_PATH)


smoke = _load_smoke_module()


class AuthorizationSmokeTests(unittest.TestCase):
    def test_checkout_package_precedes_installed_package(self):
        previous = os.environ.pop("OPENAPS_LOCALD_ROOT", None)
        try:
            candidates = smoke._candidate_package_paths()
        finally:
            if previous is not None:
                os.environ["OPENAPS_LOCALD_ROOT"] = previous

        checkout_package = os.path.join(
            os.path.dirname(smoke.HERE), "openaps-locald"
        )
        self.assertLess(
            candidates.index(checkout_package),
            candidates.index("/usr/local/src/oref0/openaps-locald"),
        )

    def test_passive_btmon_parser_retains_only_link_aggregates(self):
        metrics = smoke._new_active_link_metrics()
        context = 0
        for line in [
            "> HCI Event: LE Meta Event (0x3e) plen 31",
            "      LE Connection Complete (0x01)",
            "      ATT: Exchange MTU Request (0x02) len 2",
            "        Client RX MTU: 185",
            "      ATT: Exchange MTU Response (0x03) len 2",
            "        Server RX MTU: 247",
            "> HCI Event: Encryption Change (0x08) plen 4",
            "        Encryption: Enabled (0x01)",
        ]:
            context = smoke._observe_btmon_line(metrics, line, context)

        metrics["state"] = "observed"
        self.assertEqual(metrics["le_connection_events"], 1)
        self.assertEqual(metrics["encryption_change_events"], 1)
        self.assertEqual(metrics["encryption_enabled_events"], 1)
        self.assertEqual(metrics["mtu_exchange_events"], 2)
        self.assertEqual(metrics["negotiated_att_mtu_values"], [185, 247])
        self.assertEqual(smoke._active_link_status(metrics), "enabled_observed")
        self.assertEqual(smoke._att_mtu_status(metrics), "observed")
        self.assertFalse(any("raw" in key or "payload" in key for key in metrics))

    def test_passive_btmon_no_connection_is_not_a_smoke_failure(self):
        metrics = smoke._new_active_link_metrics()
        metrics["state"] = "observed"
        self.assertEqual(smoke._active_link_status(metrics), "no_active_connection_observed")
        self.assertEqual(smoke._att_mtu_status(metrics), "no_active_connection_observed")


if __name__ == "__main__":
    unittest.main()
