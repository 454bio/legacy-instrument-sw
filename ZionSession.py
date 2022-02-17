import os
from glob import glob
import time
from datetime import datetime
from operator import itemgetter
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import keyboard
from ZionCamera import ZionCamera
from ZionGPIO import ZionGPIO
from ZionEvents import check_led_timings, ZionProtocol, print_eventList
from ZionGtk import ZionGUI
from picamera.exc import PiCameraValueError, PiCameraAlreadyRecording, PiCameraMMALError
import threading
import json
from types import SimpleNamespace
import traceback


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
        self.EventList = ZionProtocol()

    def CaptureImageThread(self, cropping=(0,0,1,1), group=None, verbose=False, comment='', suffix='', protocol=True):
        """ This is running in a thread. It should not call any GTK functions """
        group = '' if group is None else group
        
        self.CaptureCount += 1
        self.captureCountThisProtocol += 1
        
        filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits))

        if protocol:
            filename += '_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'A_'+str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits)+'_'+group
        else:
            filename += '_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'M_'+str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits)
        
        timestamp_ms = round(1000*(time.time()-self.TimeOfLife))
        filename += '_'+str(timestamp_ms).zfill(9)
        filename = filename+'_'+suffix if not protocol else filename
        if verbose:
            GLib.idle_add(self.gui.printToLog, f"Writing image to file {filename}.jpg")

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

        if not filename.endswith('.txt'):
            filename += ".txt"

        with open(filename, 'w') as f:
            for key in params.keys():
                f.write(key + ': '+str(params[key])+'\n')
        return filename

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
            filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits)+'_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'A_Protocol')

        self.EventList.saveProtocolToFile(filename)
        # json_str = json.dumps(self.EventList.__dict__)
        # ~ print(json_str)
        # with open(filename+'.txt', 'w') as f:
        #     json.dump(f.__dict__, f, indent=1)

    def LoadProtocolFromFile(self, filename):
        # TODO: Add error handling and notify user
        self.EventList.loadProtocolFromFile(filename)

        # with open(filename) as f:
        #     self.EventList = SimpleNamespace(**json.load(f))
            # lines = f.readlines()
        # json_str = lines[0]
        # self.EventList = SimpleNamespace(**json.loads(json_str))
        # self.EventList.Events = [ tuple(event) for event in self.EventList.Events ]
        # ~ print(self.EventList.N)
        # ~ print(self.EventList.Interrepeat_Delay)
        return self.EventList
        
    def LoadProtocolFromGUI(self, N, events, interrepeat):
        # self.EventList = ZionProtocol()
        self.EventList.N = N
        self.EventList.Events = events
        self.EventList.Interrepeat_Delay = interrepeat
        # ~ print_eventList(events)
        return self.EventList

    def RunProgram(self, stop : threading.Event):
        try:
            self.frame_period = 1000./self.Camera.framerate
            self.exposure_time = self.Camera.shutter_speed/1000. if self.Camera.shutter_speed else self.frame_period
            time.sleep(0.5)
            self.TimeOfLife = time.time()
            for _ in range(self.EventList.N + 1):
                if stop.is_set():
                    break
                for event in self.EventList.Events:
                    # event = self.EventList.Events[e]
                    self.EventList.performEvent(event, self.GPIO)
                    if stop.is_set():
                        break
                    time.sleep(self.frame_period/250)
                if not stop.is_set():
                    time.sleep(self.EventList.Interrepeat_Delay)
            # ~ self.gui.runProgramButton.set_active(False)
            # ~ self.gui.runProgramButton.set_sensitive(True)
        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            print(f"RunProgram Error!!\n{tb}")
        finally:
            self.captureCountThisProtocol = 0
            if stop.is_set():
                print("RunProgram has been stopped!")
            else:
                print("RunProgram has finished")

            GLib.idle_add(self.gui.cameraPreviewWrapper.clear_image)
            GLib.idle_add(self.gui.handlers._update_camera_preview)
            GLib.idle_add(self.gui.runProgramButton.set_sensitive, True)

    def InteractivePreview(self, window):
        self.Camera.start_preview(fullscreen=False, window=window)
        Gtk.main()
        self.Camera.stop_preview()

    def StartSession(self):
        # self.Camera.start_preview(fullscreen=False, window=window)
        Gtk.main()
        self.Camera.stop_preview()

    def QuitSession(self):
        # ~ self.GPIO.cancel_PWM()
        self.Camera.quit()

        # Delete the session folder if it's empty
        if os.path.isdir(self.Dir) and not any(os.scandir(self.Dir)):
            print(f"Removing {self.Dir} since it's empty!")
            os.removedirs(self.Dir)

    def pulse_on_trigger(self, colors, pw, capture, grp, gpio, level, ticks):
        self.GPIO.callback_for_uv_pulse.cancel() #to make this a one-shot
        #entering this function ~1ms after vsync trigger
        time.sleep((self.frame_period-3)/2000)
        if capture:
            capture_thread = threading.Thread(target=self.CaptureImageThread, kwargs={'group':grp})
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
        if colors is not None:
            self.GPIO.enable_leds(colors)
        # ~ self.enable_led('Orange', 100)
            # time.sleep((pw-3)/1000)
            time.sleep((pw-3)/1000)   #
            self.GPIO.disable_leds(colors)
        # ~ self.enable_led('Orange', 0)

    def update_last_capture(self, last_capture_file):
        print(f"Updating capture with {last_capture_file}...")
        self.gui.cameraPreviewWrapper.image_path = last_capture_file
        print(f"Done!")
        # self.gui.cameraPreview.get_parent().queue_draw()
