import multiprocessing
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

try:
    from rich import print as rprint
except:
    rprint = print

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from ZionCamera import ZionCamera, ZionCameraParameters
from ZionGPIO import ZionGPIO
from ZionProtocols import ZionProtocol
from ZionGtk import ZionGUI
from picamera.exc import mmal
from ZionEvents import ZionEvent
from image_processing.ZionImage import ZionImageProcessor, ZionImage
from image_processing.raw_converter import jpg_to_raw

mod_path = os.path.dirname(os.path.abspath(__file__))

class ZionSession():

    captureCountDigits = 8
    protocolCountDigits = 3
    captureCountPerProtocolDigits = 5

    def __init__(self, session_name, Binning, Initial_Values, PID_Params=None, overwrite=False):

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
        
        self.Temperature = None
        self.Camera = ZionCamera(Binning, Initial_Values, parent=self)
        self.GPIO = ZionGPIO(parent=self, PID_Params=PID_Params)
        self.CaptureCount = 0
        self.SplitterCount = 0
        self.ProtocolCount = 0
        self.captureCountThisProtocol = 0
        self.SplitterCount = 0

        self.Protocol = ZionProtocol(camera_parameters=Initial_Values)

        self.gui = ZionGUI(Initial_Values, self)

        self.TimeOfLife = time.time()

        self.update_last_capture_path = None
        self.update_last_capture_lock = threading.Lock()

        self.image_files_queue = multiprocessing.Queue()
        self.all_image_paths = []
        self.load_image_lock = threading.Lock()
        with self.load_image_lock:
            self.load_image_enable = False

    def CaptureImageThread(self, cropping=(0,0,1,1), group=None, verbose=False, comment='', suffix='', protocol=True):
        """ This is running in a thread. It should not call any GTK functions """
        group = '' if group is None else group
        
        self.CaptureCount += 1
        self.captureCountThisProtocol += 1
        
        filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits))

        if protocol:
            filename += '_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'A_'+str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits)+'_'+group
            bayer = True
        else:
            filename += '_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'M_'+str(self.captureCountThisProtocol).zfill(ZionSession.captureCountPerProtocolDigits)
            bayer = False
        
        timestamp_ms = round(1000*(time.time()-self.TimeOfLife))
        filename += '_'+str(timestamp_ms).zfill(9)
        filename = filename+'_'+suffix if ( (not protocol) and (suffix) ) else filename
        if verbose:
            GLib.idle_add(self.gui.printToLog, f"Writing image to file {filename}.jpg")
        # ~ try:
        self.update_last_capture_path = filename+'.jpg'
        self.SplitterCount += 1
        self.Camera.capture(filename, cropping=cropping, splitter=self.SplitterCount % 4, bayer=bayer)
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
                    filename += '_'+str(timestamp).zfill(9)

        params.save_to_file(filename)

        return filename

    def LoadParameterFile(self, filename : str) -> ZionCameraParameters:
        params = ZionCameraParameters.load_from_file(filename)
        self.Camera.load_params(params)
        return params

    def SaveProtocolFile(self, filename : str = None, comment : str = "", suffix : str = ""):
        if not filename:
            self.ProtocolCount += 1
            self.captureCountThisProtocol = 0
            filename = os.path.join(self.Dir, str(self.CaptureCount).zfill(ZionSession.captureCountDigits)+'_'+str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits)+'A_Protocol')

        self.Protocol.Parameters = self.Camera.get_all_params(comment=comment)

        if filename.endswith(".txt"):
            filename = os.path.splitext(filename)[0]

        if suffix:
            self.Protocol.save_to_file(filename+"_"+suffix)
        else:
            self.Protocol.save_to_file(filename)

    def LoadProtocolFromFile(self, filename):
        # TODO: Add error handling and notify user
        self.Protocol.load_from_file(filename)

    def _convert_jpeg(self, image_file_queue:Queue):
        print("Starting load_image thread")
        while True:
            filepath_args = image_file_queue.get()
            filepath = filepath_args[0]
            if filepath is None:
                print("_convert_jpeg thread -- received stop signal!")
                break
            if self.load_image_enable:
                print(f"\n\nconverting jpeg {filepath}\n\n")

                out_dir = os.path.join(os.path.dirname(filepath), "raws")
                filename = os.path.splitext(os.path.basename(filepath))[0]
                rgbs = jpg_to_raw(filepath, os.path.join(out_dir, filename+".tif"))

            else:
                while not self.load_image_enable:
                    continue
                print(f"\n\nconverting jpeg {filepath} after wait\n\n")

                out_dir = os.path.join(os.path.dirname(filepath), "raws")
                filename = os.path.splitext(os.path.basename(filepath))[0]
                rgbs = jpg_to_raw(filepath, os.path.join(out_dir, filename+".tif"))

    def _save_event_image(self, image_buffer_event_queue : Queue):
        """ Thread that will consume event buffers and save the files accordingly """
        print("_save_event_image starting...")
        protocol_count = str(self.ProtocolCount).zfill(ZionSession.protocolCountDigits) + 'A'
        while True:
            buffer, event = image_buffer_event_queue.get()
            # buffer, event = image_buffer_event_queue.get_nowait()
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
            print(f"Writing event image to file {filepath}")

            GLib.idle_add(
                self.gui.printToLog,
                f"Writing event image to file {filepath}"
            )

            #Keep record of file saved for loading later in different thread
            self.image_files_queue.put_nowait((filepath,))
            self.all_image_paths.append(filepath)

            with open(filepath, "wb") as out:
                out.write(buffer)

            try:
                # Attempt to update the last capture (even dark ones):
                if event.captureBool:
                    if self.update_last_capture_lock.locked():
                        continue

                    with self.update_last_capture_lock:
                        call_update = self.update_last_capture_path is None
                        self.update_last_capture_path = filepath

                    print(f"Sending {filename} to update thread")
                    if call_update:
                        GLib.idle_add(self.update_last_capture)

                    # ~ if event.group and event.group != '000':


            except Exception as e:
                tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                GLib.idle_add(self.gui.printToLog,  "ERROR Updating last capture!")
                print(f"ERROR Updating last capture!\n{tb}")

    def RunProgram(self, stop_event : threading.Event):
        # For the events. I think I want to preload all the potential waveforms
        # Load up the shared queue for the fstrobe callback with the ids
        # Check if the shared queue is empty at the end?
        # Do I unroll _all_ the events?

        try:
            self.TimeOfLife = time.time()

            events = self.Protocol.get_entries()
            all_flat_events = self.Protocol.flatten()
            GLib.idle_add(
                self.gui.printToLog,
                "Starting protocol!"
                f"   # Events and Groups: {len(events)}"
                f"   # expected frames: {len(list(filter(attrgetter('capture'), all_flat_events)))}"
            )
            # rprint("[bold yellow]Events[/bold yellow]")
            # rprint(events)
            # rprint("[bold yellow]Flat Events[/bold yellow]")
            # rprint(all_flat_events)
            # Reset progress bars
            GLib.idle_add(self.gui.ProtocolProgressBar.set_fraction, 0.0)
            GLib.idle_add(self.gui.CurrentEventProgressBar.set_fraction, 0.0)

            # rprint(self.Camera.get_camera_props(props=['exposure_speed', 'shutter_speed', 'framerate']))

            # Generate groups of events which are seperated by the special wait events in our flat events list
            # A wait event is an event that has it's `is_wait` flag set and represents a wait time that is longer then
            # the time it would take to reconfigure for a new group of events (10 minimum_cycle_times?).
            # The call to .flatten() has taken care of this for us though
            grouped_flat_events = []
            events_group = []
            for event in all_flat_events:
                if event.is_wait:
                    grouped_flat_events.append(events_group)
                    grouped_flat_events.append(event)
                    events_group = []
                else:
                    events_group.append(event)

            # Need to make sure to add the last group if the last event isn't a wait
            if events_group:
                grouped_flat_events.append(events_group)

            # rprint("[bold yellow]Grouped Flat Events[/bold yellow]")
            # rprint(grouped_flat_events)
            
            #Disable toggle led waveforms:
            self.GPIO.disable_all_toggle_wf()

            # Pre-allocate enough space
            seq_stream = io.BytesIO()
            buffer_queue = multiprocessing.Queue()
            #image_files_queue = multiprocessing.Queue()

            # self.buffer_thread = multiprocessing.Process(target=self._save_event_image, args=(buffer_queue, ) )
            self.buffer_thread = threading.Thread(target=self._save_event_image, args=(buffer_queue, ) )
            self.buffer_thread.daemon=True  # TODO: Should make this non-daemonic so files get save even if program is shutdown
            self.buffer_thread.start()

            self.load_image_thread = threading.Thread(target=self._convert_jpeg, args=(self.image_files_queue, ) )
            self.load_image_thread.daemon = True
            self.load_image_thread.start()

            total_number_of_groups = float(len(grouped_flat_events))
            for gow_ind, group_or_wait in enumerate(grouped_flat_events):
                GLib.idle_add(self.gui.ProtocolProgressBar.set_fraction, gow_ind / total_number_of_groups)

                if not isinstance(group_or_wait, list):
                    # We're a wait event
                    # GLib.idle_add(
                    #     self.gui.printToLog,
                    #     f"Waiting for {group_or_wait.cycle_time / 1000} seconds..."
                    # )

                    # ~ image_files_queue.put_nowait((self.load_image_paths))
                    # ~ self.all_image_paths.extend(self.load_image_paths)
                    # ~ with self.load_image_lock:
                        # ~ self.load_image_paths = []

                    # ~ if self.load_image_lock.locked():
                        # ~ print(f"Unlocking _load_image thread")
                        # ~ self.load_image_lock.release()
                    with self.load_image_lock:
                        self.load_image_enable = True

                    group_or_wait.sleep(
                        stop_event=stop_event,
                        progress_log_func=partial(GLib.idle_add, self.gui.printToLog),
                        progress_bar_func=partial(GLib.idle_add, self.gui.CurrentEventProgressBar.set_fraction)
                    )

                    if stop_event.is_set():
                        print("Received stop!")
                        break

                else:
                    with self.load_image_lock:
                        self.load_image_enable = False
                    flat_events = group_or_wait

                    # This will pre-program the pigpio with the waveforms for our LEDs
                    # it will also update the LEDs fields withe wave id
                    self.GPIO.load_event_led_wave_ids(flat_events)

                    expected_num_frames = len(flat_events)

                    # rprint(self.Camera.get_camera_props())
                    start_fstrobe = self.GPIO.get_num_fstrobes()
                    capture_busy_event = self.GPIO.get_capture_busy_event()
                    bayer = True
                    quality = 85
                    for frame_ind, (event, _) in enumerate(zip(flat_events, self.Camera.capture_continuous(seq_stream, format='jpeg', burst=False, bayer=bayer, thumbnail=None, quality=quality))):
                        # print(f"stream_size: {seq_stream.tell()}")
                        # stream_size = seq_stream.tell()
                        # seq_stream.seek(0)

                        # if event.capture:
                        #     buffer_queue.put_nowait((seq_stream.read1(stream_size), event))
                        #     seq_stream.seek(0)
                        #     print(f"Received frame {frame_ind} for event '{event.name}'  capture: {event.capture}  buf size: {stream_size}")
                        self.GPIO.camera_trigger()
                        seq_stream.truncate()
                        stream_size = seq_stream.tell()
                        seq_stream.seek(0)

                        if event.captureBool:
                            buffer_queue.put_nowait((seq_stream.getvalue(), event))
                            print(f"Received frame {frame_ind} for event '{event.name}'  capture: {event.captureBool}  buf size: {stream_size}")
                            self.GPIO.debug_trigger()
                        elif frame_ind % 10 == 0:
                            print(f"Received frame {frame_ind} for event '{event.name}'  capture: {event.captureBool}")

                        if stop_event.is_set():
                            print("Received stop!")
                            break

                    end_fstrobe = self.GPIO.get_num_fstrobes()

                    print("Event Group Finished")
                    # rprint(self.Camera.get_camera_props())
                    # buffer_queue.put_nowait((None,None))

                    num_captured_frames = frame_ind + 1
                    if expected_num_frames != num_captured_frames:
                        print(f"WARNING: We did not receive the expected number of frames!!  num_frames: {num_captured_frames}  expected: {expected_num_frames}")
                    else:
                        print(f"Event Group Captured {num_captured_frames} frames!!")

                    num_fstrobe = end_fstrobe - start_fstrobe
                    if num_fstrobe != num_captured_frames:
                        print(f"WARNING: We did not receive all of the frames actually captured!!  num_fstrobe: {num_fstrobe}  expected: {expected_num_frames}")

            print("RunProgram Finished!")

        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            GLib.idle_add(self.gui.printToLog,  "ERROR Running Protocol!")
            print(f"RunProgram Error!!\n{tb}")
        finally:
            protocol_length = time.time() - self.TimeOfLife
            self.captureCountThisProtocol = 0
            if stop_event.is_set():
                GLib.idle_add(self.gui.printToLog,  f"Protocol has been stopped! Total Time: {protocol_length:.2f} sec")
                print("RunProgram has been stopped!")
            else:
                GLib.idle_add(self.gui.printToLog,  f"Protocol has finished! Total Time: {protocol_length:.2f} sec")
                print("RunProgram has finished")

            # Send the stop signal to the image saving thread
            buffer_queue.put((None,None))
            self.buffer_thread.join(5.0)
            if self.buffer_thread.is_alive():
                print("WARNING: buffer_thread is still alive!!!")

            GLib.idle_add(self.gui.ProtocolProgressBar.set_fraction, 1.0)
            GLib.idle_add(self.gui.CurrentEventProgressBar.set_fraction, 1.0)
            GLib.idle_add(self.gui.cameraPreviewWrapper.clear_image)
            GLib.idle_add(partial(self.gui.handlers._update_camera_preview, force=True))
            GLib.idle_add(self.gui.runProgramButton.set_sensitive, True)
            GLib.idle_add(self.gui.stopProgramButton.set_sensitive, False)
            #TODO: led switches named here
            GLib.idle_add(self.gui.uvSwitch.set_sensitive, True)
            GLib.idle_add(self.gui.blueSwitch.set_sensitive, True)
            GLib.idle_add(self.gui.greenSwitch.set_sensitive, True)
            GLib.idle_add(self.gui.orangeSwitch.set_sensitive, True)
            GLib.idle_add(self.gui.redSwitch.set_sensitive, True)

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

    def update_last_capture(self):
        with self.update_last_capture_lock:
            print(f"Updating capture with {self.update_last_capture_path}...")
            t_path = self.update_last_capture_path
            self.update_last_capture_path = None
            self.gui.cameraPreviewWrapper.image_path = t_path
        # self.gui.cameraPreview.get_parent().queue_draw()

    def get_temperature(self):
        self.Temperature = self.GPIO.read_temperature()
