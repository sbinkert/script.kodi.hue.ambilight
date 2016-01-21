import sys
import xbmcaddon

__addon__ = sys.modules["__main__"].__addon__

class settings():
    def __init__(self, **kwargs):
        self.readxml()
        self.addon = xbmcaddon.Addon()

    def readxml(self):
        self.defaultHue = float(__addon__.getSetting("default_hue"))
        self.defaultSat = float(__addon__.getSetting("default_sat"))
        self.defaultBri = float(__addon__.getSetting("default_bri"))
        self.colorBias = int(__addon__.getSetting("color_bias"))
        self.debug = __addon__.getSetting("debug") == "true"
        self.fullSpectrum = __addon__.getSetting("full_spectrum") == "true"

    def update(self, **kwargs):
        self.__dict__.update(**kwargs)
        for k, v in kwargs.iteritems():
            self.addon.setSetting(k, v)
