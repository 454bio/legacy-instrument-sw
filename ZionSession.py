import os
from glob import glob
import time
from datetime import datetime
from operator import itemgetter
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import keyboard
from ZionCamera import ZionCamera
from ZionGPIO import ZionGPIO
from ZionEvents import check_led_timings, ZionProtocol, print_eventList
from ZionGtk import ZionGUI
from picamera.exc import PiCameraValueError, PiCameraAlreadyRecording, PiCameraMMALError
import threading
import json
from types import SimpleNamespace


class ZionSession():
        
    captureCountDigits = 8
    protocolCountDigits = 3
    captureCountPerProtocolDigits = 5

    def __init__(self, session_name, Binning, Initial_Values, PWM_freq, overwrite=False):

        self.Name=session_name
        now = datetime.now()
        now_date = str(now.year)+str(now.month).zfill(2)+str(now.day).zfill(2)
        now_time = str(now.hour).zfill(2)+str(now.minute).zfill(2)
        filename = now_date+'_'+now_time+'_'+self.Name
        
        listOfSessions = glob('*_'+session_name+"_*")
        #print(listOfSessions)
        #currSuffix = 1
        #while glob('*_'+session_name+"_{:04}".format(currSuffix)):
         #   currSuffix+=1
        lastSuffix = 0
        for f in glob('*_'+session_name+"_*"):
            lastHyphenIdx = f.rfind('_')
            newSuffix = int(f[(lastHyphenIdx+1):])
            lastSuffix = newSuffix if newSuffix>lastSuffix else lastSuffix
        self.Dir = filename+"_{:04}".format(lastSuffix+1)
        print('Creating directory '+str(self.Dir))
        os.mkdir(self.Dir)
        
        self.GPIO = ZionGPIO(PWM_freq, parent=self)
        
        self.Camera = ZionCamera(Binning, Initial_Values, parent=self)
        self.CaptureCount = 0
        self.SplitterCount = 0
        self.ProtocolCount = 0
        self.captureCountThisProtocol = 0
        self.SplitterCount = 0

        self.gui = ZionGUI(Initial_Values, self)
                
        self.TimeOfLife = time.time()

    def CaptureImage(self, cropping=(0,0,1,1), group=None, verbose=False, comment='', protocol=True):
        
        group = '' if group is None else group
        
        self.CaptureCount += 1
        self.captureCountThisProtocol += 1
        
        filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits))

        if protocol:
            filename += '_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'A_'+str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits)+'_'+group
        else:
            filename += '_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'M_'+str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits)
        
        timestamp_ms = round(1000*(time.time()-self.TimeOfLife))
        filename += '_'+str(timestamp_ms).zfill(8)
        if verbose:
            self.gui.printToLog('Writing image to file '+filename+'.jpg')
        # ~ try:
        self.SplitterCount += 1
        self.Camera.capture(filename, cropping=cropping, splitter=self.SplitterCount % 4)
        ret = 0
        if not protocol:
            self.SaveParameterFile(comment, False, timestamp_ms)
        # ~ except PiCameraValueError or PiCameraAlreadyRecording:
            # ~ print('Camera Busy! '+filename+' not written!')
            # ~ if verbose:
                # ~ self.gui.printToLog('Camera Busy! '+filename+' not written!')
            # ~ ret = 1
        # ~ except PiCameraAlreadyRecording:
            # ~ print('Camera Busy! '+filename+' not written!')
            # ~ if verbose:
                # ~ self.gui.printToLog('Camera Busy! '+filename+' not written!')
            # ~ ret = 1
        # ~ except PiCameraMMALError:
            # ~ print('Camera Busy! '+filename+' not written!')
            # ~ if verbose:
                # ~ self.gui.printToLog('Camera Busy! '+filename+' not written!')
            # ~ ret = 1
        return ret
        
    def SaveParameterFile(self, comment, bSession, timestamp=0):
        params = self.Camera.get_all_params()
        params['comment'] = comment
        if bSession:
            filename = filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits)+'_'+str(self.ProtocolCount+1).zfill(ZionSession.protocolCountDigits)+'A_Params')
        else:
            filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits)+'_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'M_'+str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits))
            if timestamp > 0:
                    filename += '_'+str(timestamp)
        with open(filename+'.txt', 'w') as f:
            for key in params.keys():
                f.write(key + ': '+str(params[key])+'\n')
        return filename+'.txt'

    def LoadParameterFile(self, filename):
        params = dict()
        with open(filename) as f:
            for line in f:
                linesplit = line.split(':')
                parameter_key = linesplit[0]
                parameter_value = linesplit[1][1:].strip()
                if not parameter_key=='comment': 
                    if parameter_value[0]=='-':
                        if parameter_value[1:].isdecimal():
                            params[parameter_key] = int(parameter_value)
                        else:
                            try:
                                params[parameter_key] = float(parameter_value)
                            except ValueError:
                                params[parameter_key] = parameter_value
                    else:
                        if parameter_value.isdecimal():
                            params[parameter_key] = int(parameter_value)
                        else:
                            try:
                                params[parameter_key] = float(parameter_value)
                            except ValueError:
                            #therefore it must be a string:
                                params[parameter_key] = parameter_value
        self.Camera.load_params(params)
        return params
        
    # ~ def SaveProtocolFile(self, default=False):
        # ~ if default:
            # ~ filename = 'Zion_Default_Protocol'
        # ~ else:
            # ~ self.ProtocolCount += 1
            # ~ filename = os.path.join(self.Dir, self.Name+'_Protocol_'+str(self.ProtocolCount).zfill(2))
        # ~ with open(filename+'.txt', 'w') as f:
            # ~ f.write('N='+str(self.EventList.N)+'\n')
            # ~ for event in self.EventList.Events:
                # ~ f.write(str(event)+'\n')
        # ~ return filename+'.txt'
        
    def SaveProtocolFile(self, filename=None):
        if not filename:
            self.ProtocolCount += 1
            self.captureCountThisProtocol = 0
            filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits)+'_'+str(self.ProtocolCount).zfill(3)+'A_Protocol')
        json_str = json.dumps(self.EventList.__dict__)
        # ~ print(json_str)
        with open(filename+'.txt', 'w') as f:
            f.write(json_str)

    def LoadProtocolFromFile(self, filename):
        with open(filename) as f:
            lines = f.readlines()
        json_str = lines[0]
        self.EventList = SimpleNamespace(**json.loads(json_str))
        self.EventList.Events = [ tuple(event) for event in self.EventList.Events]
        # ~ print(self.EventList.N)
        # ~ print(self.EventList.Interrepeat_Delay)
        return self.EventList
        
    def LoadProtocolFromGUI(self, N, events, interrepeat):
        self.EventList = ZionProtocol()
        self.EventList.N = N
        self.EventList.Events = events
        self.EventList.Interrepeat_Delay = interrepeat
        # ~ print_eventList(events)
        return self.EventList

    def CreateProgram(self, blue_timing, orange_timing, uv_timing, capture_times, repeatN=0):
        check_led_timings(blue_timing, orange_timing, uv_timing)
        self.EventList = None #EventList(blue_timing, orange_timing, uv_timing, capture_times, N=repeatN)

    def RunProgram(self, stop):
        self.frame_period = 1000./self.Camera.framerate
        self.exposure_time = self.Camera.shutter_speed/1000. if self.Camera.shutter_speed else self.frame_period
        time.sleep(0.5)
        self.TimeOfLife = time.time()
        for n in range(self.EventList.N+1):
            if stop():
                break
            for e in range(len(self.EventList.Events)):
                if stop():
                    break
                event = self.EventList.Events[e]
                self.EventList.performEvent(event, self.GPIO)
                time.sleep(self.frame_period/250)
            if not stop():
                time.sleep(self.EventList.Interrepeat_Delay)
        # ~ self.gui.runProgramButton.set_active(False)
        # ~ self.gui.runProgramButton.set_sensitive(True)
        self.captureCountThisProtocol = 0

    def InteractivePreview(self, window):
        self.Camera.start_preview(fullscreen=False, window=window)
        Gtk.main()
        self.Camera.stop_preview()

    def QuitSession(self):
        # ~ self.GPIO.cancel_PWM()
        self.Camera.quit()

    def pulse_on_trigger(self, colors, pw, capture, grp, gpio, level, ticks):
        self.GPIO.callback_for_uv_pulse.cancel() #to make this a one-shot
        #entering this function ~1ms after vsync trigger
        time.sleep((self.frame_period-3)/2000)
        if capture:
            capture_thread = threading.Thread(target=self.CaptureImage, kwargs={'group':grp})
            capture_thread.daemon = True
            capture_thread.start()
        time1 = (self.frame_period-6)/2000
        time2 = (3*self.frame_period-(self.exposure_time+pw+6))/2000
        # ~ time.sleep((2*self.frame_period-(self.exposure_time+pw+6)/2000)
        # ~ time.sleep(0.087+(self.frame_period-self.exposure_time)/1000) #wait for ~87 ms
        # ~ print(self.frame_period)
        # ~ print(self.exposure_time/2)
        # ~ print(pw/2)
        # ~ time.sleep((self.frame_period-(self.exposure_time+pw)/2)/1000) #wait for ~87 ms
        time.sleep(max([time1, time2]))
        self.GPIO.enable_leds(colors)
        # ~ self.enable_led('Orange', 100)
        time.sleep((pw-3)/1000)
        self.GPIO.disable_leds(colors)
        # ~ self.enable_led('Orange', 0)
