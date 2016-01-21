import xbmc
import xbmcgui
import xbmcaddon
import json
import sys
import colorsys
import os
import math
import threading

__addon__ = xbmcaddon.Addon()
__cwd__ = __addon__.getAddonInfo('path')
__resource__ = xbmc.translatePath(os.path.join(__cwd__, 'resources', 'lib'))

sys.path.append(__resource__)

from settings import *
from tools import *
import web

class REST_Server(threading.Thread):
    def run(self):
        urls = ('/color', 'REST_Server')
        app = web.application(urls, globals())
        app.run()

    def GET(self):
        web.header('Content-Type', 'application/json')
        output = json.dumps(currentColor)
        return output


xbmc.log("Kodi Hue service started, version: %s" % get_version())

capture = xbmc.RenderCapture()
fmt = capture.getImageFormat()
# BGRA or RGBA
# xbmc.log("Hue Capture Image format: %s" % fmt)
fmtRGBA = fmt == 'RGBA'



class MyMonitor(xbmc.Monitor):
  def __init__(self, *args, **kwargs):
    xbmc.Monitor.__init__(self)

  def onSettingsChanged(self):
    logger.debuglog("Settings changed")
    settings.readxml()
    defaultColor["h"] = settings.defaultHue
    defaultColor["s"] = settings.defaultSat
    defaultColor["v"] = settings.defaultBri
    logger.debuglog("Hue: %s  Sat: %s  Bri: %s" % (settings.defaultHue, settings.defaultSat, settings.defaultBri))

monitor = MyMonitor()

class MyPlayer(xbmc.Player):
  duration = 0
  playingvideo = None

  def __init__(self):
    xbmc.Player.__init__(self)
  
  def onPlayBackStarted(self):
    if self.isPlayingVideo():
      self.playingvideo = True
      self.duration = self.getTotalTime()
      logger.debuglog("Playback started")

      #start capture when playback starts
      capture_width = 32 #100
      capture_height = int(capture_width / capture.getAspectRatio())
      logger.debuglog("capture %s x %s" % (capture_width, capture_height))
      capture.capture(capture_width, capture_height, xbmc.CAPTURE_FLAG_CONTINUOUS)

  def onPlayBackPaused(self):
    if self.isPlayingVideo():
      self.playingvideo = False

  def onPlayBackResumed(self):
    if self.isPlayingVideo():
      self.playingvideo = True

  def onPlayBackStopped(self):
    if self.playingvideo:
      self.playingvideo = False
      currentColor = defaultColor.copy()

  def onPlayBackEnded(self):
    if self.playingvideo:
      self.playingvideo = False
      currentColor = defaultColor.copy()

class HSVRatio:
  cyan_min = float(4.5 / 12.0)
  cyan_max = float(7.75 / 12.0)

  def __init__(self, hue=0.0, saturation=0.0, value=0.0, ratio=0.0):
    self.h = hue
    self.s = saturation
    self.v = value
    self.ratio = ratio

  def average(self, h, s, v):
    self.h = (self.h + h) / 2
    self.s = (self.s + s) / 2
    self.v = (self.v + v) / 2

  def averageValue(self, overall_value):
    if self.ratio > 0.5:
      self.v = self.v * self.ratio + overall_value * (1 - self.ratio)
    else:
      self.v = (self.v + overall_value) / 2
    

  def hue(self, fullSpectrum):
    if fullSpectrum != True:
      if self.s > 0.01:
        if self.h < 0.5:
          #yellow-green correction
          self.h = self.h * 1.17
          #cyan-green correction
          if self.h > self.cyan_min:
            self.h = self.cyan_min
        else:
          #cyan-blue correction
          if self.h < self.cyan_max:
            self.h = self.cyan_max

    #h = int(self.h * 65535) # on a scale from 0 <-> 65535
    #s = int(self.s * 255)
    #v = int(self.v * 255)
    h = self.h # on a scale from 0 <-> 65535
    s = self.s
    v = self.v

    #if v < hue.settings.ambilight_min:
    #  v = hue.settings.ambilight_min
    #if v > hue.settings.ambilight_max:
    #  v = hue.settings.ambilight_max
    return h, s, v

  def __repr__(self):
    return 'h: %s s: %s v: %s ratio: %s' % (self.h, self.s, self.v, self.ratio)

class Screenshot:
  def __init__(self, pixels, capture_width, capture_height):
    self.pixels = pixels
    self.capture_width = capture_width
    self.capture_height = capture_height

  def most_used_spectrum(self, spectrum, saturation, value, size, overall_value):
    # color bias/groups 6 - 36 in steps of 3
    #colorGroups = settings.color_bias
    colorGroups = 18
    if colorGroups == 0:
      colorGroups = 1
    colorHueRatio = 360 / colorGroups

    hsvRatios = []
    hsvRatiosDict = {}

    for i in range(360):
      if spectrum.has_key(i):
        #shift index to the right so that groups are centered on primary and
        #secondary colors
        colorIndex = int(((i + colorHueRatio / 2) % 360) / colorHueRatio)
        pixelCount = spectrum[i]

        if hsvRatiosDict.has_key(colorIndex):
          hsvr = hsvRatiosDict[colorIndex]
          hsvr.average(i / 360.0, saturation[i], value[i])
          hsvr.ratio = hsvr.ratio + pixelCount / float(size)

        else:
          hsvr = HSVRatio(i / 360.0, saturation[i], value[i], pixelCount / float(size))
          hsvRatiosDict[colorIndex] = hsvr
          hsvRatios.append(hsvr)

    colorCount = len(hsvRatios)
    if colorCount > 1:
      # sort colors by popularity
      hsvRatios = sorted(hsvRatios, key=lambda hsvratio: hsvratio.ratio, reverse=True)
      
      #return at least 3
      if colorCount == 2:
        hsvRatios.insert(0, hsvRatios[0])
      
      hsvRatios[0].averageValue(overall_value)
      hsvRatios[1].averageValue(overall_value)
      hsvRatios[2].averageValue(overall_value)
      return hsvRatios

    elif colorCount == 1:
      hsvRatios[0].averageValue(overall_value)
      return [hsvRatios[0]] * 3

    else:
      return [HSVRatio()] * 3

  def spectrum_hsv(self, pixels, width, height):
    spectrum = {}
    saturation = {}
    value = {}

    size = int(len(pixels) / 4)
    pixel = 0

    i = 0
    s, v = 0, 0
    r, g, b = 0, 0, 0
    tmph, tmps, tmpv = 0, 0, 0
    
    for i in range(size):
      if fmtRGBA:
        r = pixels[pixel]
        g = pixels[pixel + 1]
        b = pixels[pixel + 2]
      else: #probably BGRA
        b = pixels[pixel]
        g = pixels[pixel + 1]
        r = pixels[pixel + 2]
      pixel += 4

      tmph, tmps, tmpv = colorsys.rgb_to_hsv(float(r / 255.0), float(g / 255.0), float(b / 255.0))
      s += tmps
      v += tmpv

      # skip low value and saturation
      if tmpv > 0.25:
        if tmps > 0.33:
          h = int(tmph * 360)

          # logger.debuglog("%s \t set pixel r %s \tg %s \tb %s" % (i, r, g,
          # b))
          # logger.debuglog("%s \t set pixel h %s \ts %s \tv %s" % (i,
          # tmph*100, tmps*100, tmpv*100))

          if spectrum.has_key(h):
            spectrum[h] += 1 # tmps * 2 * tmpv
            saturation[h] = (saturation[h] + tmps) / 2
            value[h] = (value[h] + tmpv) / 2
          else:
            spectrum[h] = 1 # tmps * 2 * tmpv
            saturation[h] = tmps
            value[h] = tmpv

    overall_value = v / float(i)
    # s_overall = int(s * 100 / i)
    return self.most_used_spectrum(spectrum, saturation, value, size, overall_value)

def run():
  player = None
  t = REST_Server()
  t.daemon = True
  t.start()

  while not xbmc.abortRequested:
            
      if player == None:
        player = MyPlayer()
      else:
        xbmc.sleep(100)

      capture.waitForCaptureStateChangeEvent(1000 / 60)
      if capture.getCaptureState() == xbmc.CAPTURE_STATE_DONE:
        if player.playingvideo:
          screen = Screenshot(capture.getImage(), capture.getWidth(), capture.getHeight())
          hsvRatios = screen.spectrum_hsv(screen.pixels, screen.capture_width, screen.capture_height)
          h,s,v = hsvRatios[0].hue(False)
          currentColor["h"] = h
          currentColor["s"] = s
          currentColor["v"] = v
          



if (__name__ == "__main__"):
  settings = settings()
  defaultColor = { 'h':settings.defaultHue,
                's':settings.defaultSat,
                'v':settings.defaultBri}

  currentColor = defaultColor.copy()
  logger = Logger()
  if settings.debug:
    logger.debug()
  
  logger.debuglog("Default Color - Hue: %s  Sat: %s  Bri: %s" % (settings.defaultHue, settings.defaultSat, settings.defaultBri))
  args = None
  if len(sys.argv) == 2:
    args = sys.argv[1]
  run()
