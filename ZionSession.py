import os
from glob import glob
import time
from datetime import datetime
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from ZionCamera import ZionCamera, ZionCameraParameters
from ZionGPIO import ZionGPIO
from ZionProtocols import ZionProtocol
from ZionGtk import ZionGUI
from picamera.exc import PiCameraValueError, PiCameraAlreadyRecording, PiCameraMMALError
import threading
import traceback
from functools import partial
from ZionEvents import ZionEvent

mod_path = os.path.dirname(os.path.abspath(__file__))

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

        lastSuffix = 0
        sessions_dir = os.path.join(mod_path, "sessions")

        for f in glob(os.path.join(sessions_dir, f"*_{session_name}_*")):
            lastHyphenIdx = f.rfind('_')
            newSuffix = int(f[(lastHyphenIdx+1):])
            lastSuffix = newSuffix if newSuffix>lastSuffix else lastSuffix
        self.Dir = os.path.join(mod_path, "sessions", f"{filename}_{lastSuffix+1:04d}")
        print('Creating directory '+str(self.Dir))
        os.makedirs(self.Dir)

        self.GPIO = ZionGPIO(PWM_freq, parent=self)

        self.Camera = ZionCamera(Binning, Initial_Values, parent=self)
        self.CaptureCount = 0
        self.SplitterCount = 0
        self.ProtocolCount = 0
        self.captureCountThisProtocol = 0
        self.SplitterCount = 0

        self.Protocol = ZionProtocol(camera_parameters=Initial_Values)

        self.gui = ZionGUI(Initial_Values, self)

        self.TimeOfLife = time.time()

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
        params = self.Camera.get_all_params(comment=comment)
        if bSession:
            filename = filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits)+'_'+str(self.ProtocolCount+1).zfill(ZionSession.protocolCountDigits)+'A_Params')
        else:
            filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits)+'_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'M_'+str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits))
            if timestamp > 0:
                    filename += '_'+str(timestamp)

        params.save_to_file(filename)

        return filename

    def LoadParameterFile(self, filename : str) -> ZionCameraParameters:
        params = ZionCameraParameters.load_from_file(filename)
        self.Camera.load_params(params)
        return params

    def SaveProtocolFile(self, filename : str = None, comment : str = ""):
        if not filename:
            self.ProtocolCount += 1
            self.captureCountThisProtocol = 0
            filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits)+'_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'A_Protocol')

        self.Protocol.Parameters = self.Camera.get_all_params(comment=comment)
        self.Protocol.save_to_file(filename)

    def LoadProtocolFromFile(self, filename):
        # TODO: Add error handling and notify user
        self.Protocol.load_from_file(filename)

    def RunProgram(self, stop : threading.Event):
        try:
            self.frame_period = 1000./self.Camera.framerate
            self.exposure_time = self.Camera.shutter_speed/1000. if self.Camera.shutter_speed else self.frame_period
            time.sleep(0.5)
            self.TimeOfLife = time.time()
            event_groups = self.Protocol.get_event_groups()
            GLib.idle_add(
                self.gui.printToLog,
                "Starting protocol!"
                f"   # Event Groups: {len(event_groups)}"
            )
            for eg_ind, eg in enumerate(event_groups):
                GLib.idle_add(
                    self.gui.printToLog,
                    f"Starting event group {eg_ind}..."
                    f"   # Events: {len(eg.events)}"
                    f"   # Cycles: {eg.cycles}"
                )
                for i in range(eg.cycles):
                    GLib.idle_add(self.gui.printToLog, f"Starting cycle {i}...")
                    if stop.is_set():
                        break
                    for event in eg.events:
                        GLib.idle_add(self.gui.printToLog, f"Running event: {event}...")
                        self.Protocol.performEvent(event, self.GPIO)
                        if stop.is_set():
                            break
                        time.sleep(self.frame_period/250)

        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            GLib.idle_add(self.gui.printToLog,  "ERROR Running Protocol!")
            print(f"RunProgram Error!!\n{tb}")
        finally:
            self.captureCountThisProtocol = 0
            if stop.is_set():
                GLib.idle_add(self.gui.printToLog,  "Protocol has been stopped!")
                print("RunProgram has been stopped!")
            else:
                GLib.idle_add(self.gui.printToLog,  "Protocol has finished!")
                print("RunProgram has finished")

            GLib.idle_add(self.gui.cameraPreviewWrapper.clear_image)
            GLib.idle_add(partial(self.gui.handlers._update_camera_preview, force=True))
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

    def pulse_on_trigger(self, event : ZionEvent, gpio, level, ticks):
        self.GPIO.callback_for_uv_pulse.cancel() #to make this a one-shot
        #entering this function ~1ms after vsync trigger
        if event.leds:
            pt = event.leds[0].pulsetime
            colors = event.leds
        else:
            pt = 0
            colors = []

        time.sleep((self.frame_period-3)/2000)
        if event.capture:
            capture_thread = threading.Thread(target=self.CaptureImageThread, kwargs={'group':event.group})
            capture_thread.daemon = True
            capture_thread.start()
        time1 = (self.frame_period-6)/2000
        time2 = (3*self.frame_period-(self.exposure_time+pt+6))/2000
        # ~ time.sleep((2*self.frame_period-(self.exposure_time+pw+6)/2000)
        # ~ time.sleep(0.087+(self.frame_period-self.exposure_time)/1000) #wait for ~87 ms
        # ~ print(self.frame_period)
        # ~ print(self.exposure_time/2)
        # ~ print(pw/2)
        # ~ time.sleep((self.frame_period-(self.exposure_time+pw)/2)/1000) #wait for ~87 ms
        time.sleep(max([time1, time2]))
        if colors:
            self.GPIO.enable_leds(colors)
            if pt > 3:
                time.sleep((pt-3)/1000)   #
            self.GPIO.disable_leds(colors)

    def update_last_capture(self, last_capture_file):
        print(f"Updating capture with {last_capture_file}...")
        self.gui.cameraPreviewWrapper.image_path = last_capture_file
        print(f"Done!")
        # self.gui.cameraPreview.get_parent().queue_draw()
