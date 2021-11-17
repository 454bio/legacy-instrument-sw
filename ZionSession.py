import os
import time
from operator import itemgetter
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import keyboard
from ZionCamera import ZionCamera
from ZionGPIO import ZionGPIO
from ZionEvents import check_led_timings, ZionProtocol
from ZionGtk import ZionGUI
from picamera.exc import PiCameraValueError, PiCameraAlreadyRecording, PiCameraMMALError
import threading

class ZionSession():

    def __init__(self, session_name, Frame_Rate, Binning, Initial_Values, PWM_freq, overwrite=False):

        self.Name=session_name
        currSuffix = 1
        while os.path.exists(session_name+"_{:02}".format(currSuffix)):
            currSuffix+=1
        self.Dir = session_name+"_{:02}".format(currSuffix)
        print('Creating directory '+str(self.Dir))
        os.mkdir(self.Dir)
        
        self.GPIO = ZionGPIO(PWM_freq, parent=self)
        
        self.Camera = ZionCamera(Frame_Rate, Binning, Initial_Values, parent=self)
        self.CaptureCount = 0
        self.SplitterCount = 0
        self.ProtocolCount = 0
        self.SplitterCount = 0

        self.LoadProtocolFromFile('ZionDefaultProtocol.txt')
        self.gui = ZionGUI(Initial_Values, self)
                
        self.TimeOfLife = time.time()

    def CaptureImage(self, cropping=(0,0,1,1), group=None, verbose=False, comment='', protocol=True):
        group = '' if group is None else group
        if not protocol:
            filename = os.path.join(self.Dir, str(group)+'_'+self.Name)
        else:
            filename = os.path.join(self.Dir, str(self.ProtocolCount).zfill(2)+'_'+str(group)+'_'+self.Name)
        self.CaptureCount += 1
        filename += '_'+str(self.CaptureCount).zfill(3)+'_'+str(round(1000*(time.time()-self.TimeOfLife)))
        if verbose:
            self.gui.printToLog('Writing image to file '+filename+'.jpg')
        try:
            self.SplitterCount += 1
            self.Camera.capture(filename, cropping=cropping, splitter=self.SplitterCount % 4)
            ret = 0
            if group=='P':
                self.SaveParameterFile(comment, False)
        except PiCameraValueError or PiCameraAlreadyRecording:
            print('Camera Busy! '+filename+' not written!')
            if verbose:
                self.gui.printToLog('Camera Busy! '+filename+' not written!')
            ret = 1
        except PiCameraAlreadyRecording:
            print('Camera Busy! '+filename+' not written!')
            if verbose:
                self.gui.printToLog('Camera Busy! '+filename+' not written!')
            ret = 1
        # ~ except PiCameraMMALError:
            # ~ print('Camera Busy! '+filename+' not written!')
            # ~ if verbose:
                # ~ self.gui.printToLog('Camera Busy! '+filename+' not written!')
            # ~ ret = 1
        return ret
        
    def SaveParameterFile(self, comment, bSession):
        params = self.Camera.get_all_params()
        params['comment'] = comment
        if bSession:
            filename = os.path.join(self.Dir, self.Name)
        else:
            filename = os.path.join(self.Dir, 'P_'+self.Name)		
            filename += '_'+str(self.CaptureCount).zfill(3)+'_'+str(round(1000*(time.time()-self.TimeOfLife)))	
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
        
    def SaveProtocolFile(self, default=False):
        if default:
            filename = 'Zion_Default_Protocol'
        else:
            self.ProtocolCount += 1
            filename = os.path.join(self.Dir, self.Name+'_Protocol_'+str(self.ProtocolCount).zfill(2))
        with open(filename+'.txt', 'w') as f:
            f.write('N='+str(self.EventList.N)+'\n')
            for event in self.EventList.Events:
                f.write(str(event)+'\n')
        return filename+'.txt'

    def LoadProtocolFromFile(self, filename):
        self.EventList = ZionProtocol(filename)
        return self.EventList
        
    def LoadProtocolFromGUI(self, N, events):
        self.EventList = ZionProtocol()
        self.EventList.N = N
        self.EventList.Events = events
        return self.EventList

    def CreateProgram(self, blue_timing, orange_timing, uv_timing, capture_times, repeatN=0):
        check_led_timings(blue_timing, orange_timing, uv_timing)
        self.EventList = None #EventList(blue_timing, orange_timing, uv_timing, capture_times, N=repeatN)

    def RunProgram(self, stop):
        self.TimeOfLife = time.time()
        for n in range(self.EventList.N+1):
            if stop():
                break
            time.sleep(self.EventList.Events[0][0]/1000.)
            for e in range(len(self.EventList.Events)-1):
                if stop():
                    break
                event = self.EventList.Events[e]
                self.EventList.performEvent(event, self.Camera, self.GPIO)
                time.sleep((self.EventList.Events[e+1][0]-event[0])/1000.)
            if not stop():
                self.EventList.performEvent(self.EventList.Events[-1], self.Camera, self.GPIO)
        # ~ self.gui.runProgramButton.set_active(False)
        # ~ self.gui.runProgramButton.set_sensitive(True)

    def InteractivePreview(self, window):
        self.Camera.start_preview(fullscreen=False, window=window)
        Gtk.main()
        self.Camera.stop_preview()

    def QuitSession(self):
        # ~ self.GPIO.cancel_PWM()
        self.Camera.quit()
