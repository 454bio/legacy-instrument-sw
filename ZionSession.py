from operator import attrgetter, methodcaller
import os
from glob import glob
import time
from datetime import datetime
import io
import threading
import traceback
from functools import partial
from queue import Queue
from fractions import Fraction

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from ZionCamera import ZionCamera, ZionCameraParameters
from ZionGPIO import ZionGPIO
from ZionProtocols import ZionProtocol
from ZionGtk import ZionGUI
from picamera.exc import mmal
from ZionEvents import ZionEvent

mod_path = os.path.dirname(os.path.abspath(__file__))

class ZionSession():

    captureCountDigits = 8
    protocolCountDigits = 3
    captureCountPerProtocolDigits = 5

    def __init__(self, session_name, Binning, Initial_Values, overwrite=False):

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

        self.Camera = ZionCamera(Binning, Initial_Values, parent=self)
        self.GPIO = ZionGPIO(parent=self)
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

    def _save_event_image(self, image_buffer_event_queue : Queue):
        """ Thread that will consume event buffers and save the files accordingly """
        protocol_count = str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits) + 'A'
        last_capture_with_led = None
        while True:
            buffer, event = image_buffer_event_queue.get()
            if buffer is None:
                print("_save_event_image -- received stop signal!")
                break

            # print(f"_save_event_image -- Received buffer -- len(buffer): {len(buffer)}  event: {event}")
            print(f"_save_event_image -- Received buffer -- len(buffer): {len(buffer)}  event.name: {event.name}")

            self.CaptureCount += 1
            self.captureCountThisProtocol += 1

            capture_count = str(self.CaptureCount).zfill(ZionSession.captureCountDigits)
            timestamp_ms = str(round(1000*(time.time()-self.TimeOfLife))).zfill(9)
            protocol_capture_count = str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits)
            group = event.group or ''

            filename = "_".join([
                capture_count,
                protocol_count,
                protocol_capture_count,
                group,
                timestamp_ms,
            ])
            filename += ".jpg"
            filepath = os.path.join(self.Dir, filename)
            GLib.idle_add(
                self.gui.printToLog,
                f"Writing event image to file {filepath}"
            )
            with open(filepath, "wb") as out:
                out.write(buffer)

            try:
                # Attempt to update the last capture if the event had LED illumination
                if event.leds.has_wave_id():
                    if GLib.Source.remove_by_funcs_user_data(self.update_last_capture, last_capture_with_led):
                        print("Removed previous update_last_capture call")

                    print(f"Sending {filename} to update thread")
                    GLib.idle_add(self.update_last_capture, filepath)
                    last_capture_with_led = filepath
            except Exception as e:
                tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                GLib.idle_add(self.gui.printToLog,  "ERROR Updating last capture!")
                print(f"ERROR Updating last capture!\n{tb}")

    def RunProgram(self, stop_event : threading.Event):
        # For the events. I think I want to preload all the potential waveforms
        # Load up the shared queue for the fstrobe callback with the ids
        # Check if the shared queue is empty at the end?
        # Do I unroll _all_ the events?
        # from rich import print as rprint

        try:
            self.TimeOfLife = time.time()

            events = self.Protocol.get_entries()
            GLib.idle_add(
                self.gui.printToLog,
                "Starting protocol!"
                f"   # Events and Groups: {len(events)}"
            )
            flat_events = self.Protocol.flatten()
            GLib.idle_add(
                self.gui.printToLog,
                "Starting protocol!"
                f"   # flat events: {len(flat_events)}"
            )

            # This will pre-program the pigpio with the waveforms for our LEDs
            # it will also update the LEDs fields withe wave id
            self.GPIO.load_event_led_wave_ids(flat_events)

            # Pre-allocate enough space
            seq_stream = io.BytesIO()
            buffer_queue = Queue()

            self.buffer_thread = threading.Thread(target=self._save_event_image, args=(buffer_queue, ) )
            self.buffer_thread.daemon=True  # TODO: Should make this non-daemonic so files get save even if program is shutdown
            self.buffer_thread.start()

            expected_num_frames = len(flat_events)

            # rprint(self.Camera.get_camera_props())
            for frame_ind, (event, _) in enumerate(zip(flat_events, self.Camera.capture_continuous(seq_stream, format='jpeg', burst=True, bayer=False))):
                print(f"Captured frame {frame_ind}!")
                print(f"stream_size: {seq_stream.tell()}")
                seq_stream.truncate()
                seq_stream.seek(0)
                if event.capture:
                    buffer_queue.put_nowait((seq_stream.getvalue(), event))
                    print("Put Buffer on Queue!\n")
                else:
                    print("Skipped saving...\n")

                if stop_event.is_set():
                    print("Received stop!")
                    break

            print("RunProgram Finished!!")
            # rprint(self.Camera.get_camera_props())

            num_captured_frames = frame_ind + 1
            if expected_num_frames != num_captured_frames:
                print(f"WARNING: We did not receive the expected number of frames!!  num_frames: {num_captured_frames}  expected: {expected_num_frames}")
            else:
                print(f"RunProgram Captured {num_captured_frames} frames!!")

        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            GLib.idle_add(self.gui.printToLog,  "ERROR Running Protocol!")
            print(f"RunProgram Error!!\n{tb}")
        finally:
            protocol_length = time.time() - self.TimeOfLife
            self.captureCountThisProtocol = 0
            if stop_event.is_set():
                GLib.idle_add(self.gui.printToLog,  f"Protocol has been stopped! Total Time: {protocol_length:.0f} sec")
                print("RunProgram has been stopped!")
            else:
                GLib.idle_add(self.gui.printToLog,  f"Protocol has finished! Total Time: {protocol_length:.0f} sec")
                print("RunProgram has finished")

            # Send the stop signal to the image saving thread
            buffer_queue.put((None,None))
            self.buffer_thread.join(5.0)
            if self.buffer_thread.is_alive():
                print("WARNING: buffer_thread is still alive!!!")

            GLib.idle_add(self.gui.cameraPreviewWrapper.clear_image)
            GLib.idle_add(partial(self.gui.handlers._update_camera_preview, force=True))
            GLib.idle_add(self.gui.runProgramButton.set_sensitive, True)
            GLib.idle_add(self.gui.blueSwitch.set_sensitive, True)
            GLib.idle_add(self.gui.orangeSwitch.set_sensitive, True)
            GLib.idle_add(self.gui.uvSwitch.set_sensitive, True)

    def InteractivePreview(self, window):
        self.Camera.start_preview(fullscreen=False, window=window)
        Gtk.main()
        self.Camera.stop_preview()

    def StartSession(self):
        # self.Camera.start_preview(fullscreen=False, window=window)
        Gtk.main()
        self.Camera.stop_preview()

    def QuitSession(self):
        self.Camera.quit()
        self.GPIO.quit()

        # Delete the session folder if it's empty
        if os.path.isdir(self.Dir) and not any(os.scandir(self.Dir)):
            print(f"Removing {self.Dir} since it's empty!")
            os.removedirs(self.Dir)

    def update_last_capture(self, last_capture_file):
        print(f"Updating capture with {last_capture_file}...")
        self.gui.cameraPreviewWrapper.image_path = last_capture_file
        print(f"Done!")
        # self.gui.cameraPreview.get_parent().queue_draw()
