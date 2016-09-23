class Convert(object):
    """
        How to convert from mg/dL (World Wide format) to mmol/L (mostly UK
        and ex-UK colonies)

        Please note that rounding of these values is a *view* related
        function, and should happen at the very last point before data is
        being viewed, not here. See http://physics.stackexchange.com/a/63330

        This code *could* be used for mathematical processing of results by
        someone down the line, so we take pain to avoid throwing away
        potentially significant data by rounding.
    """

    MMOLL_CONVERT_FACTOR = 18.0

    @classmethod
    def mmol_l_to_mg_dl(klass, mmol_l):
        return mmol_l * klass.MMOLL_CONVERT_FACTOR

    @classmethod
    def mg_dl_to_mmol_l(klass, mg_dl):
        return mg_dl / klass.MMOLL_CONVERT_FACTOR
