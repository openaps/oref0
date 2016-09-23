from unittest import TestCase
from openaps.glucose.display import Display


class DisplayTestCase (TestCase):
    """
        Checks that the display function rounds to the correct number
        of significant digits
    """

    def test_display_mmol_l(self):
        self.assertEqual(Display.display('mmol/L', 5.490000), 5.5)
        self.assertEqual(Display.display('mmol/L', 5.500001), 5.5)
        self.assertEqual(Display.display('mmol/L', 5.510000), 5.5)
        self.assertEqual(Display.display('mmol/L', 5.590000), 5.6)

    def test_display_mg_dl(self):
        self.assertEqual(Display.display('mg/dL', 147.078), 147)
        self.assertEqual(Display.display('mg/dL', 268.236), 268)
        self.assertEqual(Display.display('mg/dL', 605.970), 606)
        self.assertEqual(Display.display('mg/dL', 623.268), 623)
