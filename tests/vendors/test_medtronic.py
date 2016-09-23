from unittest import TestCase
from mock import Mock

from openaps.vendors.units import bg_targets


class BgTargetsTestCase(TestCase):
    """Test openaps.vendor.units bg_targets"""

    def mg_dl_pump_response(self):
        return {'units': 'mg/dL', 'targets': [
                    {'high': 200, 'low': 100},
                    {'high': 300, 'low': 200}
                ]}.copy()

    def mmol_l_pump_response(self):
        return {'units': 'mmol/L', 'targets': [{'high': 6, 'low': 5}]}.copy()

    class MockMethod():
        pass

    class MockParent():
        device = 'irrelevant'

    def test_read_bg_targets_from_mg_dl_pump(self):
        instance = bg_targets(None, BgTargetsTestCase.MockParent())

        instance.units = 'mg/dL'
        instance.to_unit = instance.CONVERTERS[instance.units]
        response = instance.convert(self.mg_dl_pump_response( ))

        expected_response = dict({
            'targets': [{'high': 200, 'low': 100}, {'high': 300, 'low': 200}],
            'units': 'mg/dL',
            'user_preferred_units': 'mg/dL',
        })

        self.assertEqual(response, expected_response)

    def test_read_bg_targets_from_mmol_l_pump(self):
        instance = bg_targets(None, BgTargetsTestCase.MockParent())

        instance.units = 'mg/dL'
        instance.to_unit = instance.CONVERTERS[instance.units]
        response = instance.convert(self.mmol_l_pump_response( ))

        expected_response = {
            'targets': [{'high': 108, 'low': 90}],
            'units': 'mg/dL',
            'user_preferred_units': 'mmol/L',
        }


        self.assertEqual(response, expected_response)
