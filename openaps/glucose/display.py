class Display(object):
    """
        Round Glucose values for display, so that they are consistent in
        all OpenAPS apps

        Example:

            from openaps.glucose.display import Display
            print(Display.display('mmol/L', 5.5))
            print(Display.display('mg/dL', 100))
    """
    @classmethod
    def display(klass, unit, val):
        assert unit in ['mmol/L', 'mg/dL']

        if unit == 'mg/dL':
            return int(round(val))
        elif unit == 'mmol/L':
            return round(val, 1)
