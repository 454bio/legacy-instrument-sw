import os
import time
from operator import itemgetter
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import keyboard
from ZionCamera import ZionCamera
from ZionGPIO import ZionGPIO
from ZionEvents import check_led_timings, create_event_list, performEventList
from ZionGtk import ZionGUI

# ~ class Parameter():
    # ~ def __init__(self, initValue, name=None):
        # ~ if name is not None:
            # ~ self.Name = name
        # ~ else:
            # ~ self.Name = ''
        # ~ self.Value = initValue
        
    # ~ def isValueValid(self, newval):
        # ~ return true
        # ~ #to be filled in by inherited classes
        
    # ~ def setValue(self, newval):
        # ~ if isValueValid(newval):
            # ~ self.Value = newval
        # ~ else:
            # ~ raise ValueError(str(newval)+' is not a valid choice for '+self.Name) 

# ~ class NumericParameter(Parameter):
    # ~ def __init__(self, default, minimum, maximum):
        # ~ super(NumericParameter, self).__init__(default)
        # ~ self.Min = minimum
        # ~ self.Max = maximum
        # ~ self.Def = default
        
    # ~ def isValueValid(self, newval):
        # ~ if newval <= self.Max and newval >= self.Min:
            # ~ return True
        # ~ else:
            # ~ return False

# ~ class CategoricalParameter(Parameter):
    # ~ def __init__(self, default, valueList):
        # ~ super(NumericParameter, self).__init__(default)
        # ~ self.Def = default
        # ~ self.ValueList = valueList
        
    # ~ def isValueValid(self, newval):
        # ~ if newval in self.ValueList:
            # ~ return True
        # ~ else:
            # ~ return False

# ~ class ParameterSet():
    # ~ def __init__(self, Initial_Values):
        # ~ self = {'brightness': NumericParameter(50,0,100),
                      # ~ 'contrast': NumericParameter(50,-100,100),
                      # ~ 'saturation': NumericParameter(100,-100,100),
                      # ~ 'sharpness': NumericParameter(0,-100,100),
                      # ~ 'exposure_compensation': NumericParameter(0,-25,25),
                      # ~ 'awb_gains_red': NumericParameter(red_gain,0.,8.)
                      # ~ 'awb_gains_blue': NumericParameter(blue_gain,0.,8.)
                      # ~ 'awb_mode': CategoricalParameter('off', ['off', 'auto'])
                      # ~ 'exposure_mode': CategoricalParameter(expMode, ['off', 'auto', 'night', 'nightpreview', 'backlight', 'spotlight', 'sports', 'snow', 'beach', 'verylong', 'fixedfps', 'antishake', 'fireworks']
                      # ~ 'iso': CategoricalParameter(0, list(range(0,800+1,100)))
                      # ~ 'metering_mode': CategoricalParameter('average', ['average', 'spot', 'backlit', 'matrix']),
                     # ~ }

class ZionSession():

    def __init__(self, session_name, Spatial_Res, Frame_Rate, Binning, Initial_Values, Blue_Timing, Orange_Timing, UV_Timing, Camera_Captures, RepeatN=0, overwrite=False):

        self.Name=session_name
        currSuffix = 1
        while os.path.exists(session_name+"_{:02}".format(currSuffix)):
            currSuffix+=1
        self.Dir = session_name+"_{:02}".format(currSuffix)
        print('Creating directory '+str(self.Dir))
        os.mkdir(self.Dir)
        
        self.GPIO = ZionGPIO()
        
        self.Camera = ZionCamera(Spatial_Res, Frame_Rate, Binning, Initial_Values, parent=self)
        self.CaptureCount = 0

        self.gui = ZionGUI(Initial_Values, self)
        
        self.CreateProgram(Blue_Timing, Orange_Timing, UV_Timing, Camera_Captures, RepeatN)
        
        self.TimeOfLife = time.time()
        
    def CaptureImage(self, cropping=(0,0,1,1), group=None):
        group = '' if group is None else group
        filename = os.path.join(self.Dir, str(group)+'_'+self.Name)
        self.CaptureCount += 1
        filename += '_'+str(self.CaptureCount).zfill(3)+'_'+str(round(1000*(time.time()-self.TimeOfLife)))
        return self.Camera.capture(filename, cropping=cropping)

    def CreateProgram(self, blue_timing, orange_timing, uv_timing, capture_times, repeatN=0):
        check_led_timings(blue_timing, orange_timing, uv_timing)
        self.EventList, self.NumGrps = create_event_list(blue_timing, orange_timing, uv_timing, capture_times)
        self.RepeatN = repeatN

    #TODO: adjust scope for this routine
    def RunProgram(self):
        performEventList(self.EventList, self.Camera, self.GPIO, Repeat_N=self.RepeatN, baseFilename=(self.Dir, self.Name), baseTime=self.TimeOfLife, numGrps=self.NumGrps)

    def InteractivePreview(self, window):
        self.Camera.start_preview(fullscreen=False, window=window)
        Gtk.main()
        self.Camera.stop_preview()

    def QuitSession(self):
        self.GPIO.turn_off_led('all')
        self.Camera.quit()
