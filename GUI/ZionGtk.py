#!/usr/bin/python3
import os
import time
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, GObject, GLib

from Camera.ZionCamera import ZionCameraParameters
from GPIO.ZionLED import ZionLEDs, ZionLEDColor
from GUI.ZionGtkHelpers import PictureViewFromFile, PictureViewFromMem

mod_path = os.path.dirname(os.path.abspath(__file__))

def get_handler_id(obj, signal_name):
    signal_id, detail = GObject.signal_parse_name(signal_name, obj, True)
    return GObject.signal_handler_find(obj, GObject.SignalMatchType.ID, signal_id, detail, None, None, None)

class ZionGUI():

    def __init__(self, initial_values : ZionCameraParameters, parent : 'ZionSession', glade_file=os.path.join(mod_path, 'zion_layout.glade')):
        #Create Window and Maximize:
        self.builder = Gtk.Builder.new_from_file(glade_file)
        self.mainWindow = self.builder.get_object("window1")

        # ~ Gtk.Window.maximize(self.mainWindow)
        self.mainWindow.move(633,36)
        # ~ self.mainWindow.resize(1287,712)

        self.parent = parent        # type: 'ZionSession'

        #define default values
        self.Default_Brightness = initial_values.brightness
        self.Default_Contrast = initial_values.contrast
        self.Default_Saturation = initial_values.saturation
        self.Default_Sharpness = initial_values.sharpness

        self.BrightnessScale = self.builder.get_object("brightness_scale")
        self.BrightnessEntry = self.builder.get_object("brightness_entry")
        self.BrightnessScale.set_value(initial_values.brightness)
        self.ContrastScale = self.builder.get_object("contrast_scale")
        self.ContrastEntry = self.builder.get_object("contrast_entry")
        self.ContrastScale.set_value(initial_values.contrast)
        self.SaturationScale = self.builder.get_object("saturation_scale")
        self.SaturationEntry = self.builder.get_object("saturation_entry")
        self.SaturationScale.set_value(initial_values.saturation)
        self.SharpnessScale = self.builder.get_object("sharpness_scale")
        self.SharpnessEntry = self.builder.get_object("sharpness_entry")
        self.SharpnessScale.set_value(initial_values.sharpness)

        # ~ self.AutoAwbButton = self.builder.get_object("auto_wb_switch")
        self.redGainEntry = self.builder.get_object("red_gain_entry")
        self.redGainScale = self.builder.get_object("red_gain_scale")
        self.redGainScale.set_value(initial_values.red_gain)
        self.blueGainEntry = self.builder.get_object("blue_gain_entry")
        self.blueGainScale = self.builder.get_object("blue_gain_scale")
        self.blueGainScale.set_value(initial_values.blue_gain)

        if initial_values.awb_mode == 'off':
            # ~ self.AutoAwbButton.set_active(False)
            self.redGainScale.set_sensitive(True)
            self.blueGainScale.set_sensitive(True)
        else:
            # ~ self.AutoAwbButton.set_active(True)
            self.redGainScale.set_sensitive(False)
            self.blueGainScale.set_sensitive(False)

        self.expTimeBuffer = self.builder.get_object("exposure_time_buffer")
        self.expTimeBox = self.builder.get_object("exposure_time_entry")
        self.analogGainBuffer = self.builder.get_object("analog_gain_buffer")
        self.digitalGainBuffer = self.builder.get_object("digital_gain_buffer")
        self.analogGainEntry = self.builder.get_object("analog_gain_entry")
        self.digitalGainEntry = self.builder.get_object("digital_gain_entry")
        self.frBuffer = self.builder.get_object("framerate_buffer")
        self.frEntry = self.builder.get_object("framerate_entry")

        self.uvManualEntry = self.builder.get_object("uv_led_manual_entry")
        self.blueManualEntry = self.builder.get_object("blue_led_manual_entry")
        self.greenManualEntry = self.builder.get_object("green_led_manual_entry")
        self.orangeManualEntry = self.builder.get_object("orange_led_manual_entry")
        self.redManualEntry = self.builder.get_object("red_led_manual_entry")

        self.P_Entry = self.builder.get_object("pid_P_entry")
        self.I_Entry = self.builder.get_object("pid_I_entry")
        self.TargetTempEntry = self.builder.get_object("pid_temperature_entry")
        self.PID_DeltaT_Entry = self.builder.get_object("pid_tDelta_entry")
        self.PID_EnableButton = self.builder.get_object("pid_enable_button")


        #TODO: blue and orange named switches
        self.uvSwitch = self.builder.get_object("uv_led_switch")
        self.blueSwitch = self.builder.get_object("blue_led_switch")
        self.greenSwitch = self.builder.get_object("green_led_switch")
        self.orangeSwitch = self.builder.get_object("orange_led_switch")
        self.redSwitch = self.builder.get_object("red_led_switch")

        self.logBuffer = self.builder.get_object("textbuffer_log")
        self.logView = self.builder.get_object("textview_log")
        self.logMarkEnd = self.logBuffer.create_mark("", self.logBuffer.get_end_iter(), False)

        self.temperatureBuffer = self.builder.get_object("temperature_buffer")
        self.dcBuffer = self.builder.get_object("duty_cycle_buffer")

        self.imageDenoiseButton = self.builder.get_object("denoise_button")

        self.commentBox = self.builder.get_object("comment_entry")
        self.suffixBox = self.builder.get_object("suffix_entry")

        self.paramFileChooser = self.builder.get_object('param_file_chooser_dialog')
        self.filter_protocol = Gtk.FileFilter()
        self.filter_protocol.set_name("Protocol Files")
        self.filter_protocol.add_mime_type("application/json")
        self.filter_protocol.add_pattern("*.txt")
        self.filter_parameter = Gtk.FileFilter()
        self.filter_parameter.set_name("Parameter Files")
        self.filter_parameter.add_pattern("*.txt")
        self.paramFileChooser.add_filter(self.filter_protocol)
        self.paramFileChooser.add_filter(self.filter_parameter)
        self.paramFileChooser.set_filter(self.filter_protocol)

        self.EventTreeViewGtk = self.builder.get_object("event_tree")
        self.DeleteEntryButton = self.builder.get_object("delete_entry_button")

        self.parent.Protocol.gtk_initialize_treeview(self.EventTreeViewGtk)
        # self.parent.Protocol.load_from_file(filename="brett_testing_protocol.txt")
        self.parent.Protocol.load_from_file(filename="example_v2_protocol.txt")
        # self.EventTreeViewGtk.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        self.EventTreeViewGtk.show_all()
        self.EventTreeViewGtk.expand_all()

        self.EventListScroll = self.builder.get_object("eventlist_scroll")

        self.ProtocolProgressBar = self.builder.get_object("protocol_progress_bar")
        self.CurrentEventProgressBar = self.builder.get_object("current_event_progress_bar")
        self.runProgramButton = self.builder.get_object("run_program_button")
        self.stopProgramButton  = self.builder.get_object("stop_program_button")

        self.cameraPreview = self.builder.get_object("camera_preview")
        self.cameraPreviewWrapper = PictureViewFromFile(self.cameraPreview, os.path.join(mod_path, "Logo.png"))

        self.NotebookRight = self.builder.get_object("notebook_right")
        self.IpView = self.builder.get_object("image_processing_display")
        self.IpViewWrapper = PictureViewFromFile(self.IpView, os.path.join(mod_path, "Logo.png"))
        self.Spot_A_Entry = self.builder.get_object("spot_A_entry")
        self.Spot_C_Entry = self.builder.get_object("spot_C_entry")
        self.Spot_G_Entry = self.builder.get_object("spot_G_entry")
        self.Spot_T_Entry = self.builder.get_object("spot_T_entry")
        self.SelectSpotsButton = self.builder.get_object("select_spots_button")

        self.median_ks_entry = self.builder.get_object("median_ks_entry")
        self.erode_ks_entry = self.builder.get_object("erode_ks_entry")
        self.dilate_ks_entry = self.builder.get_object("dilate_ks_entry")
        self.threshold_scale_entry = self.builder.get_object("threshold_scale_entry")
        self.spot_min_size_entry = self.builder.get_object("min_spot_size_entry")
        self.spot_max_size_entry = self.builder.get_object("max_spot_size_entry")
        self.weights_R_entry = self.builder.get_object("rgb_weights_R_entry")
        self.weights_G_entry = self.builder.get_object("rgb_weights_G_entry")
        self.weights_B_entry = self.builder.get_object("rgb_weights_B_entry")

        self.basecall_p_entry = self.builder.get_object("basecall_p_entry")
        self.basecall_q_entry = self.builder.get_object("basecall_p_entry")
        self.report_button = self.builder.get_object("report_button")
        self.cloud_button = self.builder.get_object("cloud_push_button")

        self.handlers = Handlers(self)
        self.builder.connect_signals(self.handlers)

        GLib.idle_add(self.handlers.check_fixed_settings)
        self.mainWindow.maximize()

    def printToLog(self, text):
        text_iter_end = self.logBuffer.get_end_iter()

        self.logBuffer.insert(text_iter_end, f"{text}\n")
        self.logView.scroll_to_mark(self.logMarkEnd, 0, False, 0, 0)

        # self.logBuffer.insert_at_cursor(text+'\n')
        # ~ mark = self.logBuffer.create_mark(None, self.logBuffer.get_end_iter(), False)
        # ~ self.logView.scroll_to_mark(mark, 0, False, 0,0)

    def set_file_chooser_for_protocol_files(self):
        self.paramFileChooser.set_filter(self.filter_protocol)

    def set_file_chooser_for_parameter_files(self):
        self.paramFileChooser.set_filter(self.filter_parameter)

    def load_roi_image(self, args):#filepath, queue):
        filepath = args[0]
        queue = args[1]
        print("GUI displaying ROI, enabling spot entries")
        self.NotebookRight.set_current_page(1)
        self.IpViewWrapper.image_path = filepath
        self.Spot_A_Entry.set_sensitive(True)
        self.Spot_C_Entry.set_sensitive(True)
        self.Spot_G_Entry.set_sensitive(True)
        self.Spot_T_Entry.set_sensitive(True)
        self.SelectSpotsButton.set_sensitive(True)

class Handlers:

    def __init__(self, gui : ZionGUI):
        self.parent = gui
        # ~ self.ExpModeLastChoice = self.parent.Def_row_idx if self.parent.Def_row_idx else 1
        self.updateExpParams()
        self.update_exp_params_sourceid = GObject.timeout_add(2000, self.updateExpParams)
        self.updateTemp()
        self.update_temp_sourceid = GObject.timeout_add(2500, self.updateTemp)
        self.lastShutterTime = self.parent.parent.Camera.exposure_speed
        self.run_thread = None
        self.stop_run_thread = threading.Event()
        self.camera_preview_window = (1172, 75, 720, 540)
        self.recent_protocol_file = None
        self.recent_params_file = None
        
        P = self.parent.parent.GPIO.pigpio_process.mp_namespace.P
        I = self.parent.parent.GPIO.pigpio_process.mp_namespace.I
        target_temp = self.parent.parent.GPIO.pigpio_process.mp_namespace.target_temp
        delta_t = self.parent.parent.GPIO.pigpio_process.mp_namespace.pid_delta_t
        if P is not None:
            self.parent.P_Entry.set_text(str(P))
        else:
            self.parent.P_Entry.set_text('-')
        if I is not None:
            self.parent.I_Entry.set_text(str(I))
        else:
            self.parent.I_Entry.set_text('-')
        if target_temp is not None:
            self.parent.TargetTempEntry.set_text(str(target_temp))
        else:
            self.parent.TargetTempEntry.set_text('-')
        if delta_t is not None:
            self.parent.PID_DeltaT_Entry.set_text(str(delta_t))
        else:
            self.parent.PID_DeltaT_Entry.set_text('-')
            
        self.parent.PID_EnableButton.set_active(False)
        if self.parent.parent.GPIO.pigpio_process.Temp_1W_device is None:
           self.parent.PID_EnableButton.set_sensitive(False)
        else:
            self.parent.PID_EnableButton.set_sensitive(True)

    def _update_camera_preview(self, force=False):
        (x,y,w,h) = self.parent.cameraPreviewWrapper.get_bbox()

        if self.camera_preview_window != (x, y, w, h) or force:
            # print(f"Updating preview to (x,y): ({x}, {y})  (w,h): ({w}, {h})")
            self.camera_preview_window = (x, y, w, h)
            # self.camera_preview_window = self.parent.cameraPreviewWrapper.get_bbox()
            if not self.is_program_running() or force:
                self.parent.parent.Camera.start_preview(fullscreen=False, window=self.camera_preview_window)

    def on_window1_delete_event(self, *args):
        if self.is_program_running():
            self.stop_run_thread.set()
            self.parent.printToLog('Requesting script to stop')
            print('Requesting thread to stop')
            self._stop_running_program()

        self.parent.parent.GPIO.disable_all_leds()
        # Added following line to resolve stopping toggle led thread too early
        # TODO: change this? thread-safe?
        time.sleep(1)
        GObject.source_remove(self.update_exp_params_sourceid)
        GObject.source_remove(self.update_temp_sourceid)
        
        Gtk.main_quit(*args)

    def is_program_running(self):
        return self.run_thread and self.run_thread.is_alive()

    def on_window1_focus_in_event(self, *args):
        if not self.is_program_running():
            self.parent.parent.Camera.start_preview(fullscreen=False, window=self.camera_preview_window)
        return False

    def on_window1_focus_out_event(self, *args):
        if not self.is_program_running():
            self.parent.parent.Camera.stop_preview()
        return False

    def on_window1_configure_event(self, widget, event):
        self._update_camera_preview()
        return False

    def on_script_save_button_clicked(self, button):
        self.parent.paramFileChooser.set_action(Gtk.FileChooserAction.SAVE)

        self.parent.set_file_chooser_for_protocol_files()
        if self.recent_protocol_file:
            self.parent.paramFileChooser.set_current_folder(os.path.dirname(self.recent_protocol_file))
        else:
            self.parent.paramFileChooser.set_current_folder(mod_path)

        response = self.parent.paramFileChooser.run()

        if response == Gtk.ResponseType.OK:
            filename = self.parent.paramFileChooser.get_filename()
            comment = self.parent.commentBox.get_text()
            self.recent_protocol_file = filename
            self.parent.paramFileChooser.hide()
            self.parent.parent.SaveProtocolFile(filename=filename, comment=comment)
        elif response == Gtk.ResponseType.CANCEL:
            self.parent.paramFileChooser.hide()

    # TODO: Make the naming consistent
    def on_script_load_button_clicked(self, button):
        self.parent.paramFileChooser.set_action(Gtk.FileChooserAction.OPEN)

        self.parent.set_file_chooser_for_protocol_files()
        if self.recent_protocol_file:
            self.parent.paramFileChooser.set_current_folder(os.path.dirname(self.recent_protocol_file))
        else:
            self.parent.paramFileChooser.set_current_folder(mod_path)

        response = self.parent.paramFileChooser.run()

        if response == Gtk.ResponseType.OK:
            filename = self.parent.paramFileChooser.get_filename()
            self.parent.paramFileChooser.hide()
            self.recent_protocol_file = filename
            self.parent.parent.LoadProtocolFromFile(filename)
            self.parent.EventTreeViewGtk.expand_all()
        elif response == Gtk.ResponseType.CANCEL:
            self.parent.paramFileChooser.hide()

    def updateExpParams(self):
        a_gain = float(self.parent.parent.Camera.analog_gain)
        d_gain = float(self.parent.parent.Camera.digital_gain)
        e_time = float(self.parent.parent.Camera.exposure_speed/1000.)
        fr = float(self.parent.parent.Camera.framerate)
        self.parent.analogGainBuffer.set_text("{:04.3f}".format(a_gain))
        self.parent.digitalGainBuffer.set_text("{:04.3f}".format(d_gain))
        self.parent.expTimeBuffer.set_text("{:07.3f}".format(e_time))
        self.parent.frBuffer.set_text("{:03.2f}".format(fr))
        return True
        
    def updateTemp(self):
        #get_temp_thread = threading.Thread(target=self.parent.parent.get_temperature)
        #get_temp_thread.daemon = True
        #get_temp_thread.start()
        temperature = self.parent.parent.GPIO.pigpio_process.mp_namespace.temperature
        dc = self.parent.parent.GPIO.pigpio_process.mp_namespace.dc
        if temperature is not None:
            self.parent.temperatureBuffer.set_text("{:02.1f}".format(temperature))
            self.parent.dcBuffer.set_text("{:.1f}".format(dc))
        else:
            self.parent.temperatureBuffer.set_text("-")
            self.parent.dcBuffer.set_text("0")
        return True
        
    def on_pid_enable_button_toggled(self, button):
        if button.get_active():
            self.parent.printToLog("Enabling PID")
            # also set params
            # first setpt
            try:
                val = int(self.parent.TargetTempEntry.get_text())
            except ValueError:
                self.parent.printToLog("Temperature must be integer!")
                return
            self.parent.parent.GPIO.set_target_temperature(val)
            #next P
            try:
                val = float(self.parent.P_Entry.get_text())
            except ValueError:
                self.parent.printToLog("P Value must be non-negative and numeric!")
                return
            self.parent.parent.GPIO.pigpio_process.mp_namespace.P = val
            if val<0:
                self.parent.printToLog("P Value must be non-negative numeric!")
                return
            #now I
            try:
                val = float(self.parent.I_Entry.get_text())
            except ValueError:
                self.parent.printToLog("I Value must be non-negative numeric!")
                return
            if val<0:
                self.parent.printToLog("I Value must be non-negative numeric!")
                return
            self.parent.parent.GPIO.pigpio_process.mp_namespace.I = val
            #now enable:
            self.parent.parent.GPIO.enable_PID(True)
        else:
            self.parent.printToLog("Disabling PID")
            self.parent.parent.GPIO.enable_PID(False)

    def on_pid_verbose_button_toggled(self, button):
        if button.get_active():
            self.parent.printToLog("PID is verbose")
            self.parent.parent.GPIO.pigpio_process.mp_namespace.pid_verbose = True
        else:
            self.parent.printToLog("PID is not verbose")
            self.parent.parent.GPIO.pigpio_process.mp_namespace.pid_verbose = False

    def on_pid_temperature_entry_activate(self, entry):
        try:
            val = int(entry.get_text())
        except ValueError:
            self.parent.printToLog("Temperature must be integer!")
            return
        # ~ self.parent.parent.GPIO.pigpio_process.mp_namespace.target_temp = val
        self.parent.parent.GPIO.set_target_temperature(val)

    def on_pid_P_entry_activate(self, entry):
        try:
            val = float(entry.get_text())
        except ValueError:
            self.parent.printToLog("P Value must be non-negative and numeric!")
            return
        if val<0:
            self.parent.printToLog("P Value must be non-negative numeric!")
            return
        self.parent.parent.GPIO.pigpio_process.mp_namespace.P = val

    def on_pid_I_entry_activate(self, entry):
        try:
            val = float(entry.get_text())
        except ValueError:
            self.parent.printToLog("I Value must be non-negative numeric!")
            return
        if val<0:
            self.parent.printToLog("I Value must be non-negative numeric!")
            return
        self.parent.parent.GPIO.pigpio_process.mp_namespace.I = val

    def on_pid_tDelta_entry_activate(self, entry):
        try:
            val = float(entry.get_text())
        except ValueError:
            self.parent.printToLog("t_delta Value must be numeric!")
            return
        self.parent.parent.GPIO.pigpio_process.mp_namespace.pid_delta_t = val

    def on_pid_threshold_entry_activate(self, entry):
        try:
            val = int(entry.get_text())
        except ValueError:
            self.parent.printToLog("Ramp Threshold Value must be an integer!")
            return
        self.parent.parent.GPIO.pigpio_process.pid_ramp_threshold = val

    def reset_button_click(self, *args):
        self.parent.printToLog('Setting Video Params to Defaults')
        self.parent.BrightnessScale.set_value(self.parent.Default_Brightness)
        self.parent.ContrastScale.set_value(self.parent.Default_Contrast)
        self.parent.SaturationScale.set_value(self.parent.Default_Saturation)
        self.parent.SharpnessScale.set_value(self.parent.Default_Sharpness)
        # ~ print('Brightness: '+str(self.parent.parent.Camera.brightness))
        # ~ print('Contrast: '+str(self.parent.parent.Camera.contrast))
        # ~ print('Saturation: '+str(self.parent.parent.Camera.saturation))
        
    def on_image_denoise_button(self, button):
        # ~ position = self.parent.mainWindow.get_position()
        # ~ print(position)
        # ~ size = self.parent.mainWindow.get_size()
        # ~ print(size)
        if button.get_active():
            self.parent.printToLog('Image denoising on')
            self.parent.parent.Camera.set_image_denoising(True)
        else:
            self.parent.printToLog('Image denoising off')
            self.parent.parent.Camera.set_image_denoising(False)
            
    def on_brightness_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.parent.Camera.set_brightness(newval)
        self.parent.printToLog('Brightness set to '+str(newval))
    
    def on_brightness_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = int(entry.get_text())
        except ValueError:
            self.parent.printToLog('Brightness must be an integer!')
            return
        if newval >= 0 and newval <= 100:
            self.parent.BrightnessScale.set_value(newval)
        else:
            self.parent.printToLog('Brightness must be between 0 and 100!')

    def on_contrast_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.parent.Camera.set_contrast(newval)
        self.parent.printToLog('Contrast set to '+str(newval))
    
    def on_contrast_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = int(entry.get_text())
        except ValueError:
            self.parent.printToLog('Contrast must be an integer!')
            return
        if newval >= -100 and newval <= 100:
            self.parent.ContrastScale.set_value(newval)
        else:
            self.parent.printToLog('Brightness must be between -100 and +100!')

    def on_saturation_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.parent.Camera.set_saturation(newval)
        self.parent.printToLog('Saturation set to '+str(newval))
            
    def on_saturation_entry_activate(self, entry):
        newval = entry.get_text()
        try:    
            newval = int(entry.get_text())
        except ValueError:
            self.parent.printToLog('Saturation must be an integer!')
            return
        if newval >= -100 and newval <= 100:
            self.parent.SaturationScale.set_value(newval)
        else:
            self.parent.printToLog('Saturation must be between -100 and +100!')

    def on_sharpness_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.parent.Camera.set_sharpness(newval)
        self.parent.printToLog('Sharpness set to '+str(newval))

    def on_sharpness_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = int(entry.get_text())
        except ValueError:
            self.parent.printToLog('Sharpness must be an integer!')
            return
        if newval >= -100 and newval <= 100:
            self.parent.SharpnessScale.set_value(newval)
        else:
            self.parent.printToLog('Sharpness must be between -100 and +100!')

    # LED Control Section
    def on_uv_led_button_toggled(self, switch):
        if switch.get_active():
            try:
                pw = int(self.parent.uvManualEntry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"UV LED on, set to {pw} pulse width")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.UV, pw)
        else:
            self.parent.printToLog("UV LED off")
            self.parent.parent.GPIO.disable_toggle_led(ZionLEDColor.UV)

    def on_uv_led_manual_entry_focus_out_event(self, entry, _):
        self.on_uv_led_manual_entry_activate(entry)

    def on_uv_led_manual_entry_activate(self, entry):
        if self.parent.uvSwitch.get_active():
            # Treat this like we toggled the switch
            try:
                pw = int(entry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"Changing UV LED pulse width to {pw}")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.UV, pw)
            
    def on_blue_led_button_toggled(self, switch):
        if switch.get_active():
            try:
                pw = int(self.parent.blueManualEntry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"BLUE LED on, set to {pw} pulse width")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.BLUE, pw)
        else:
            self.parent.printToLog("BLUE LED off")
            self.parent.parent.GPIO.disable_toggle_led(ZionLEDColor.BLUE)

    def on_blue_led_manual_entry_focus_out_event(self, entry, _):
        self.on_blue_led_manual_entry_activate(entry)

    def on_blue_led_manual_entry_activate(self, entry):
        if self.parent.blueSwitch.get_active():
            # Treat this like we toggled the switch
            try:
                pw = int(entry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"Changing BLUE LED pulse width to {pw}")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.BLUE, pw)
            
    def on_green_led_button_toggled(self, switch):
        if switch.get_active():
            try:
                pw = int(self.parent.greenManualEntry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"GREEN LED on, set to {pw} pulse width")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.GREEN, pw)
        else:
            self.parent.printToLog("GREEN LED off")
            self.parent.parent.GPIO.disable_toggle_led(ZionLEDColor.GREEN)

    def on_green_led_manual_entry_focus_out_event(self, entry, _):
        self.on_green_led_manual_entry_activate(entry)

    def on_green_led_manual_entry_activate(self, entry):
        if self.parent.greenSwitch.get_active():
            # Treat this like we toggled the switch
            try:
                pw = int(entry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"Changing GREEN LED pulse width to {pw}")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.GREEN, pw)
            
    def on_orange_led_button_toggled(self, switch):
        if switch.get_active():
            try:
                pw = int(self.parent.orangeManualEntry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"ORANGE LED on, set to {pw} pulse width")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.ORANGE, pw)
        else:
            self.parent.printToLog("ORANGE LED off")
            self.parent.parent.GPIO.disable_toggle_led(ZionLEDColor.ORANGE)

    def on_orange_led_manual_entry_focus_out_event(self, entry, _):
        self.on_orange_led_manual_entry_activate(entry)

    def on_orange_led_manual_entry_activate(self, entry):
        if self.parent.orangeSwitch.get_active():
            # Treat this like we toggled the switch
            try:
                pw = int(entry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"Changing ORANGE LED pulse width to {pw}")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.ORANGE, pw)
            
    def on_red_led_button_toggled(self, switch):
        if switch.get_active():
            try:
                pw = int(self.parent.redManualEntry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"RED LED on, set to {pw} pulse width")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.RED, pw)
        else:
            self.parent.printToLog("RED LED off")
            self.parent.parent.GPIO.disable_toggle_led(ZionLEDColor.RED)

    def on_red_led_manual_entry_focus_out_event(self, entry, _):
        self.on_red_led_manual_entry_activate(entry)

    def on_red_led_manual_entry_activate(self, entry):
        if self.parent.redSwitch.get_active():
            # Treat this like we toggled the switch
            try:
                pw = int(entry.get_text())
            except ValueError:
                self.parent.printToLog("Pulse width must be an integer!")
                return
            #TODO: condition this following printToLog on the success of the pulse width setting (exception handled in a different thread)
            self.parent.printToLog(f"Changing RED LED pulse width to {pw}")
            self.parent.parent.GPIO.enable_toggle_led(ZionLEDColor.RED, pw)

    # ~ def on_uv_switch_safety_button(self, button):
        # ~ if button.get_active():
            # ~ self.parent.secretUVSwitchButton.set_visible(True)
            # ~ self.parent.secretUVSwitchButton.set_sensitive(True)
        # ~ else:
            # ~ self.parent.secretUVSwitchButton.set_visible(False)
            # ~ self.parent.secretUVSwitchButton.set_sensitive(False)

    def on_uv_led_pulse_button(self, button):
        pass
        # newVal = self.parent.pulseTextInput.get_text()
        # try:
        #     newVal = float(newVal)
        # except ValueError:
        #     self.parent.printToLog('Pulse time should be an floating point number of milliseconds!')
        #     return
        # try:
        #     dc = int(self.parent.uvManualEntry.get_text())
        # except ValueError:
        #     self.parent.printToLog('Duty Cycle must be an integer from 0-100!')
        #     return
        # self.parent.printToLog('Doing UV pulse of '+str(newVal)+' milliseconds at '+str(dc)+' % duty cycle')
        # pulse_thread = threading.Thread(target=self.parent.parent.GPIO.send_uv_pulse, args=(newVal,float(dc/100)))
        # pulse_thread.daemon = True
        # pulse_thread.start()

    def on_led_off_button_clicked(self, button):
        # TODO: this should probably call self.parent.parent.GPIO.disable_all_leds() instead
        self.parent.uvSwitch.set_active(False)
        self.parent.blueSwitch.set_active(False)
        self.parent.greenSwitch.set_active(False)
        self.parent.orangeSwitch.set_active(False)
        self.parent.redSwitch.set_active(False)

    #Exposure Stuff
    def on_iso_auto_button(self, button):
        if button.get_active():
            self.parent.printToLog('ISO set to auto')
            self.parent.parent.Camera.set_iso(0)
    def on_iso_100_button(self, button):
        if button.get_active():
            self.parent.printToLog('ISO set to 100')
            self.parent.parent.Camera.set_iso(100)
    def on_iso_200_button(self, button):
        if button.get_active():
            self.parent.printToLog('ISO set to 200')
            self.parent.parent.Camera.set_iso(200)
    def on_iso_320_button(self, button):
        if button.get_active():
            self.parent.printToLog('ISO set to 320')
            self.parent.parent.Camera.set_iso(320)
    def on_iso_400_button(self, button):
        if button.get_active():
            self.parent.printToLog('ISO set to 400')
            self.parent.parent.Camera.set_iso(400)
    def on_iso_500_button(self, button):
        if button.get_active():
            self.parent.printToLog('ISO set to 500')
            self.parent.parent.Camera.set_iso(500)
    def on_iso_640_button(self, button):
        if button.get_active():
            self.parent.printToLog('ISO set to 640')
            self.parent.parent.Camera.set_iso(640)
    def on_iso_800_button(self, button):
        if button.get_active():
            self.parent.printToLog('ISO set to 800')
            self.parent.parent.Camera.set_iso(800)

    def on_exposure_comp_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.parent.Camera.set_exp_comp(newval)
        self.parent.printToLog('Exposure compensation set to '+str(newval))

    def on_exposure_time_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = float(newval)
        except ValueError: 
            self.parent.printToLog('Requested exposure time must be a number!')
            return
        else:
            self.parent.printToLog(f"Requesting exposure time of {newval:.0f} ms")
            
        if newval==0:
            # self.parent.parent.Camera.shutter_speed = 0
            self.parent.parent.Camera.set_shutter_speed(0)
            self.parent.printToLog('Exposure time set to auto')
        else:
            # self.parent.parent.Camera.shutter_speed = round(1000*newval)
            self.parent.parent.Camera.set_shutter_speed(round(1000*newval))
            self.parent.printToLog('Exposure time set to '+str(newval)+' ms')
        
        self.updateExpParams()

    def on_framerate_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = float(newval)
        except ValueError: 
            self.parent.printToLog('Requested exposure time must be a number!')
            return
        if newval==0:
            self.parent.parent.Camera.framerate_range=(0.05, 10)
        else:
        # ~ if newval<0.05 or newval>42:
            # ~ self.parent.printToLog('Requested Framerate out of range!')
        # ~ else:
            self.parent.parent.Camera.set_framerate(newval)

        
    def on_analog_gain_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = float(newval)
        except ValueError: 
            self.parent.printToLog('Requested analog gain must be a number!')
            return
        self.parent.parent.Camera.set_analog_gain(newval)
        self.parent.printToLog('Analog gain set to '+str(newval))

    def on_digital_gain_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = float(newval)
        except ValueError: 
            self.parent.printToLog('Requested digital gain must be a number!')
            return
        self.parent.parent.Camera.set_digital_gain(newval)
        self.parent.printToLog('Digital gain set to '+str(newval))
        
    def on_exp_mode_changed(self, combo):
        active_idx = combo.get_active()
        if not active_idx==-1:
            newmode = self.parent.expModeComboBox.get_active_text()
            self.parent.parent.Camera.set_exp_mode(newmode)
            self.parent.printToLog('New exposure mode: '+newmode)
            handle_id = get_handler_id(self.parent.expModeLockButton, "toggled")
            self.parent.expModeLockButton.handler_block(handle_id)
            if active_idx==0:
                self.parent.expModeLockButton.set_active(True)
                self.enable_exp_params(False)
            else:
                self.ExpModeLastChoice = active_idx
                self.parent.expModeLockButton.set_active(False)
                self.enable_exp_params(True)
            self.parent.expModeLockButton.handler_unblock(handle_id)

    def on_lock_exp_mode_button(self, button):
        if button.get_active():
            self.parent.printToLog('Exposure settings locked')
            self.parent.expModeComboBox.set_active(0)
        else:
            self.parent.printToLog('Exposure settings unlocked')
            self.parent.expModeComboBox.set_active(self.ExpModeLastChoice)

    def enable_exp_params(self, isOn):
        self.parent.isoButtonBox.set_sensitive(isOn)
        self.parent.expCompScale.set_sensitive(isOn)
        return

    #Auto White Balance/Color Stuff
    def on_awb_enable_button(self, switch, gparam):
        if switch.get_active():
            on_now = self.parent.parent.Camera.toggle_awb()
            if on_now[0]:
                self.parent.printToLog('Auto WB enabled')
                self.parent.redGainEntry.set_sensitive(False)
                self.parent.blueGainEntry.set_sensitive(False)
                self.parent.redGainScale.set_sensitive(False)
                self.parent.blueGainScale.set_sensitive(False)
        else:
            on_now = self.parent.parent.Camera.toggle_awb()
            if not on_now[0]:
                self.parent.printToLog('Auto WB disabled')

                self.parent.redGainScale.set_sensitive(True)
                self.parent.redGainEntry.set_sensitive(True)
                handle_id_red = get_handler_id(self.parent.redGainScale, "value-changed")
                self.parent.redGainScale.handler_block(handle_id_red)
                self.parent.redGainScale.set_value(on_now[1])
                self.parent.redGainScale.handler_unblock(handle_id_red)

                self.parent.blueGainScale.set_sensitive(True)
                self.parent.blueGainEntry.set_sensitive(True)
                handle_id_blue = get_handler_id(self.parent.blueGainScale, "value-changed")
                self.parent.blueGainScale.handler_block(handle_id_blue)
                self.parent.blueGainScale.set_value(on_now[2])
                self.parent.blueGainScale.handler_unblock(handle_id_blue)

    def on_red_gain_scale_value_changed(self, scale):
        newval = scale.get_value()
        self.parent.parent.Camera.set_red_gain(newval)
        self.parent.printToLog('WB Red Gain set to '+str(newval))
        
    def on_red_gain_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = float(newval)
        except ValueError:
            self.parent.printToLog('Red Gain must be a number!')
            return
        if newval<=8.0 and newval>=0:
            self.parent.redGainScale.set_value(newval)
        else:
            self.parent.printToLog('Red Gain must be between 0 and 8.0!')
            return

    def on_blue_gain_scale_value_changed(self, scale):
        newval = scale.get_value()
        self.parent.parent.Camera.set_blue_gain(newval)
        self.parent.printToLog('WB Blue Gain set to '+str(newval))

    def on_blue_gain_entry_activate(self, entry):
        newval = entry.get_text()
        try:
            newval = float(newval)
        except ValueError:
            self.parent.printToLog('Blue Gain must be a number!')
            return
        if newval<=8.0 and newval>=0:
            self.parent.blueGainScale.set_value(newval)
        else:
            self.parent.printToLog('Blue Gain must be between 0 and 8.0!')
            return

    #Capturing, Running, Etc.
    def on_capture_button_clicked(self, button):
        #TODO: get cropping from some self object here
        comment = self.parent.commentBox.get_text()
        suffix = self.parent.suffixBox.get_text()

        if not check_for_valid_filename(suffix):
            print("Invalid character (or whitespace) detected in filename suffix!")
            self.parent.printToLog("Invalid character (or whitespace) detected in filename suffix!")
        else:
            capture_thread = threading.Thread(target=self.parent.parent.CaptureImageThread, kwargs={'comment': comment,'verbose': True, 'protocol': False, 'suffix': suffix})
            capture_thread.daemon = True
            capture_thread.start()

    def on_run_program_button_clicked(self,button):
        button.set_sensitive(False)

        # Turn off and disable the led toggles
        self.parent.uvSwitch.set_active(False)
        self.parent.blueSwitch.set_active(False)
        self.parent.greenSwitch.set_active(False)
        self.parent.orangeSwitch.set_active(False)
        self.parent.redSwitch.set_active(False)
        self.parent.uvSwitch.set_sensitive(False)
        self.parent.blueSwitch.set_sensitive(False)
        self.parent.greenSwitch.set_sensitive(False)
        self.parent.orangeSwitch.set_sensitive(False)
        self.parent.redSwitch.set_sensitive(False)
        self.parent.report_button.set_sensitive(False)

        # ~ self.parent.expModeComboBox.set_active(0)
        comment = self.parent.commentBox.get_text()
        suffix = self.parent.suffixBox.get_text()
        self.parent.parent.SaveParameterFile(comment, True)
        self.parent.parent.SaveProtocolFile(comment=comment, suffix=suffix)

        try:
            median_ks = int(self.parent.median_ks_entry.get_text())
            erode_ks = int(self.parent.erode_ks_entry.get_text())
            dilate_ks = int(self.parent.dilate_ks_entry.get_text())
        except ValueError:
            self.parent.printToLog("ROI Values must be integers!")
            return
        #todo check for non-positive values
        try:
            threshold_scale = float(self.parent.threshold_scale_entry.get_text())
        except ValueError:
            self.parent.printToLog("ROI threshold needs to be numeric!")
        #todo check for negative

        try:
            min_sz = int(self.parent.spot_min_size_entry.get_text())
        except ValueError:
            min_sz = None
        try:
            max_sz = int(self.parent.spot_max_size_entry.get_text())
        except ValueError:
            max_sz = None

        self.parent.parent.ImageProcessor.set_roi_params(median_ks, erode_ks, dilate_ks, threshold_scale, min_sz, max_sz)

        self.stop_run_thread.clear()
        self.parent.parent.Camera.stop_preview()

        # ~ button.set_sensitive(False)
        self.run_thread = threading.Thread(target=self.parent.parent.RunProgram, args=(self.stop_run_thread, ) )
        self.run_thread.daemon=True  # TODO: Should make this non-daemonic so files get save even if program is shutdown
        self.run_thread.start()

        self.parent.stopProgramButton.set_sensitive(True)

    def _stop_running_program(self):
        self.run_thread.join(5.0)
        if self.run_thread.is_alive():
            self.parent.printToLog("WARNING: The thread running the protocol didn't stop!\n You might want to restart the program...")
            d = Gtk.MessageDialog(
                transient_for=self.parent.mainWindow,
                modal=True,
                buttons=Gtk.ButtonsType.OK
            )
            d.props.text = "ERROR: The program thread did not shut down in a timely manner! Suggest you restart..."
            d.run()
            d.destroy()

        self.run_thread = None
        self.parent.parent.GPIO.disable_event_leds()
        self.parent.runProgramButton.set_sensitive(True)
        self.parent.uvSwitch.set_sensitive(True)
        self.parent.blueSwitch.set_sensitive(True)
        self.parent.greenSwitch.set_sensitive(True)
        self.parent.orangeSwitch.set_sensitive(True)
        self.parent.redSwitch.set_sensitive(True)

    def on_stop_program_button_clicked(self, button):
        if self.is_program_running():
            d = Gtk.MessageDialog(
                transient_for=self.parent.mainWindow,
                modal=True,
                buttons=Gtk.ButtonsType.OK_CANCEL
            )
            d.props.text = 'Are you sure you stop the protocol?'
            response = d.run()
            d.destroy()

            # We only terminate when the user presses the OK button
            if response == Gtk.ResponseType.OK:
                self.stop_run_thread.set()
                self.parent.printToLog('Requesting script to stop')
                print('Requesting thread to stop')
                GLib.idle_add(self._stop_running_program)

    #File chooser:
    def on_param_file_chooser_dialog_realize(self, widget):
        Gtk.Window.maximize(self.parent.paramFileChooser)

    def on_load_params_button(self,button):
        self.parent.paramFileChooser.set_action(Gtk.FileChooserAction.OPEN)

        self.parent.set_file_chooser_for_parameter_files()
        if self.recent_params_file:
            self.parent.paramFileChooser.set_current_folder(os.path.dirname(self.recent_params_file))
        else:
            self.parent.paramFileChooser.set_current_folder(mod_path)

        response = self.parent.paramFileChooser.run()

        if response == Gtk.ResponseType.OK:
            filename = self.parent.paramFileChooser.get_filename()
            self.parent.paramFileChooser.hide()
            self.recent_params_file = filename
            params = self.parent.parent.LoadParameterFile(filename)
            self.parent.BrightnessEntry.set_text('')
            self.parent.ContrastEntry.set_text('')
            self.parent.SaturationEntry.set_text('')
            self.parent.SharpnessEntry.set_text('')
            self.parent.redGainEntry.set_text('')
            self.parent.blueGainEntry.set_text('')
            self.parent.analogGainEntry.set_text('')
            self.parent.digitalGainEntry.set_text('')
            self.parent.expTimeBox.set_text('')

            handler_id = get_handler_id(self.parent.BrightnessScale, "value-changed")
            self.parent.BrightnessScale.handler_block(handler_id)
            self.parent.BrightnessScale.set_value(params.brightness)
            self.parent.BrightnessScale.handler_unblock(handler_id)

            handler_id = get_handler_id(self.parent.ContrastScale, "value-changed")
            self.parent.ContrastScale.handler_block(handler_id)
            self.parent.ContrastScale.set_value(params.contrast)
            self.parent.ContrastScale.handler_unblock(handler_id)

            handler_id = get_handler_id(self.parent.SaturationScale, "value-changed")
            self.parent.SaturationScale.handler_block(handler_id)
            self.parent.SaturationScale.set_value(params.saturation)
            self.parent.SaturationScale.handler_unblock(handler_id)

            handler_id = get_handler_id(self.parent.SharpnessScale, "value-changed")
            self.parent.SharpnessScale.handler_block(handler_id)
            self.parent.SharpnessScale.set_value(params.sharpness)
            self.parent.SharpnessScale.handler_unblock(handler_id)

            # ~ handler_id = get_handler_id(self.parent.expCompScale, "value-changed")
            # ~ self.parent.expCompScale.handler_block(handler_id)
            # ~ self.parent.expCompScale.set_value(params.exposure_compensation)
            # ~ self.parent.expCompScale.handler_unblock(handler_id)

            handler_id = get_handler_id(self.parent.imageDenoiseButton, "toggled")
            self.parent.imageDenoiseButton.handler_block(handler_id)
            self.parent.imageDenoiseButton.set_active(params.image_denoise)
            self.parent.imageDenoiseButton.handler_unblock(handler_id)

            # ~ handler_id_1 = get_handler_id(self.parent.isoButtonAuto, "toggled")
            # ~ self.parent.isoButtonAuto.handler_block(handler_id_1)
            # ~ handler_id_2 = get_handler_id(self.parent.isoButton100, "toggled")
            # ~ self.parent.isoButton100.handler_block(handler_id_2)
            # ~ handler_id_3 = get_handler_id(self.parent.isoButton200, "toggled")
            # ~ self.parent.isoButton200.handler_block(handler_id_3)
            # ~ handler_id_4 = get_handler_id(self.parent.isoButton320, "toggled")
            # ~ self.parent.isoButton320.handler_block(handler_id_4)
            # ~ handler_id_5 = get_handler_id(self.parent.isoButton400, "toggled")
            # ~ self.parent.isoButton400.handler_block(handler_id_5)
            # ~ handler_id_6 = get_handler_id(self.parent.isoButton500, "toggled")
            # ~ self.parent.isoButton500.handler_block(handler_id_6)
            # ~ handler_id_7 = get_handler_id(self.parent.isoButton640, "toggled")
            # ~ self.parent.isoButton640.handler_block(handler_id_7)
            # ~ handler_id_8 = get_handler_id(self.parent.isoButton800, "toggled")
            # ~ self.parent.isoButton800.handler_block(handler_id_8)
            # ~ handler_id_9 = get_handler_id(self.parent.expModeComboBox, "changed")
            # ~ handler_id_10 = get_handler_id(self.parent.expModeLockButton, "toggled")
            # ~ handler_id_11 = get_handler_id(self.parent.expCompScale, "value-changed")
            # ~ self.parent.expModeComboBox.handler_block(handler_id_9)
            # ~ self.parent.expModeLockButton.handler_block(handler_id_10)
            # ~ self.parent.expCompScale.handler_block(handler_id_11)

            # ~ if params.iso == 0:
                # ~ button_name = "isoButtonAuto"
            # ~ else:
                # ~ button_name = f"isoButton{params.iso}"

            # ~ iso_button = getattr(self.parent, button_name, None)
            # ~ if iso_button:
                # ~ iso_button.set_active(True)
            # ~ else:
                # ~ self.parent.printToLog(f"WARNING: Unrecogonized ISO value ({params.iso})")

            # ~ self.parent.expCompScale.set_value(params.exposure_compensation)

            # ~ listStore = self.parent.expModeComboBox.get_model()
            # ~ rowList = [row[0] for row in listStore]
            # ~ row_idx = rowList.index(params.exposure_mode)
            # ~ self.parent.expModeComboBox.set_active(row_idx)
            # ~ if not row_idx:
                # ~ self.parent.expModeLockButton.set_active(True)
                # ~ self.parent.expCompScale.set_sensitive(False)
                # ~ self.parent.isoButtonBox.set_sensitive(False)
            # ~ else:
                # ~ self.parent.expModeLockButton.set_active(False)
                # ~ self.parent.expCompScale.set_sensitive(True)
                # ~ self.parent.isoButtonBox.set_sensitive(True)

            # ~ self.parent.expModeComboBox.handler_unblock(handler_id_9)
            # ~ self.parent.expModeLockButton.handler_unblock(handler_id_10)
            # ~ self.parent.expCompScale.handler_unblock(handler_id_11)
            # ~ self.parent.isoButtonAuto.handler_unblock(handler_id_1)
            # ~ self.parent.isoButton100.handler_unblock(handler_id_2)
            # ~ self.parent.isoButton200.handler_unblock(handler_id_3)
            # ~ self.parent.isoButton320.handler_unblock(handler_id_4)
            # ~ self.parent.isoButton400.handler_unblock(handler_id_5)
            # ~ self.parent.isoButton500.handler_unblock(handler_id_6)
            # ~ self.parent.isoButton640.handler_unblock(handler_id_7)
            # ~ self.parent.isoButton800.handler_unblock(handler_id_8)

            handler_id_1 = get_handler_id(self.parent.AutoAwbButton, "notify::active")
            # ~ handler_id_2 = get_handler_id(self.parent.redGainScale, "value-changed")
            # ~ handler_id_3 = get_handler_id(self.parent.blueGainScale, "value-changed")
            # ~ self.parent.AutoAwbButton.handler_block(handler_id_1)
            self.parent.redGainScale.handler_block(handler_id_2)
            self.parent.blueGainScale.handler_block(handler_id_3)

            self.parent.redGainScale.set_value(params.red_gain)
            self.parent.blueGainScale.set_value(params.blue_gain)
            if params.awb_mode == 'off':
                self.parent.AutoAwbButton.set_active(False)
                self.parent.redGainScale.set_sensitive(True)
                self.parent.blueGainScale.set_sensitive(True)
            elif params.awb_mode == 'auto':
                self.parent.AutoAwbButton.set_active(True)
                self.parent.redGainScale.set_sensitive(False)
                self.parent.blueGainScale.set_sensitive(True)

            # ~ self.parent.AutoAwbButton.handler_unblock(handler_id_1)
            self.parent.redGainScale.handler_unblock(handler_id_2)
            self.parent.blueGainScale.handler_unblock(handler_id_3)

        elif response == Gtk.ResponseType.CANCEL:
            # ~ print('cancel')
            self.parent.paramFileChooser.hide()

    def on_param_file_chooser_close(self, *args):
        self.parent.paramFileChooser.hide()

    def on_camera_preview_draw(self, *args):
        # print(f"on_camera_preview_draw")
        self.parent.cameraPreviewWrapper.on_draw(*args)
        # print("on_camera_preview_draw: done!")
        return False

    def on_camera_preview_button_press_event(self, *args):
        print("on_camera_preview_button_press_event")
        print("on_camera_preview_button_press_event: done!")

    def on_camera_preview_configure_event(self, *args):
        # This will fire if the area is resized
        # print("on_camera_preview_configure_event")
        self.parent.cameraPreviewWrapper.on_configure(*args)
        self._update_camera_preview()
        # print("on_camera_preview_configure_event: done!")
        return False

    def on_image_processing_display_draw(self, *args):
        if not self.is_program_running():
            self.parent.parent.Camera.stop_preview()
        self.parent.IpViewWrapper.on_draw(*args)
        return False

    def on_image_processing_display_configure_event(self, *args):
        self.parent.IpViewWrapper.on_configure(*args)
        # ~ self._update_camera_preview()
        return False

    def on_ip_enable_checkbox_toggled(self, switch):
        #TODO: lock/unlock rest of ip control section
        if switch.get_active():
            self.parent.parent.ImageProcessor.mp_namespace.IP_Enable = True
        else:
            self.parent.parent.ImageProcessor.mp_namespace.IP_Enable = False
        return

    def on_redo_roi_detection_button_clicked(self, button):
        try:
            median_ks = int(self.parent.median_ks_entry.get_text())
            erode_ks = int(self.parent.erode_ks_entry.get_text())
            dilate_ks = int(self.parent.dilate_ks_entry.get_text())
        except ValueError:
            self.parent.printToLog("ROI Values must be integers!")
            return
        #todo check for non-positive values
        try:
            threshold_scale = float(self.parent.threshold_scale_entry.get_text())
        except ValueError:
            self.parent.printToLog("ROI threshold needs to be numeric!")
        #todo check for negative value

        try:
            min_sz = int(self.parent.spot_min_size_entry.get_text())
        except ValueError:
            min_sz = None
        try:
            max_sz = int(self.parent.spot_max_size_entry.get_text())
        except ValueError:
            max_sz = None

        self.parent.parent.ImageProcessor.set_roi_params(median_ks, erode_ks, dilate_ks, threshold_scale, min_sz, max_sz)
        self.parent.parent.ImageProcessor.basis_spots_chosen_queue.put( 'redo_roi' )

    def on_select_spots_button_clicked(self, button):
        # TODO make user able to provide list of spots for each base
        try:
            a = [int(self.parent.Spot_A_Entry.get_text())]
            c = [int(self.parent.Spot_C_Entry.get_text())]
            g = [int(self.parent.Spot_G_Entry.get_text())]
            t = [int(self.parent.Spot_T_Entry.get_text())]
        except ValueError:
            print("Invalid Spot Choices")
            return
        #TODO check for ranges
        basis = (a,c,g,t)
        self.parent.parent.ImageProcessor.basis_spots_chosen_queue.put( basis )

    def on_report_button_clicked(self, button):
        try:
            p = float(self.parent.basecall_p_entry.get_text())
            q = float(self.parent.basecall_q_entry.get_text())
            # ~ r = float(self.parent.basecall_r_entry.get_text())
        except ValueError:
            self.parent.printToLog("p and q must be numeric!")
            return
        self.parent.parent.ImageProcessor.set_basecall_params(p,q)
        self.parent.parent.ImageProcessor.generate_report()

    def on_cloud_push_button_clicked(self, button):
        self.parent.parent.push_to_cloud()

    def on_spot_A_entry_activate(self, entry):
        #TODO
        return

    def on_spot_C_entry_activate(self, entry):
        #TODO
        return

    def on_spot_G_entry_activate(self, entry):
        #TODO
        return

    def on_spot_T_entry_activate(self, entry):
        #TODO
        return

    def on_subtract_dark_checkbutton_activate(self, button):
        #TODO
        return

    def on_subtract_temporal_checkbutton_activate(self, button):
        #TODO
        return

    def on_subtract_bg_checkbutton_activate(self, button):
        #TODO
        return

    def on_ip_back_button_clicked(self, button):
        self.parent.IpViewWrapper.channel_decrement()

    def on_ip_fwd_button_clicked(self, button):
        self.parent.IpViewWrapper.channel_increment()

    def on_ip_seek_back_button_clicked(self, button):
        return

    def on_ip_seek_fwd_button_clicked(self, button):
        return

    def on_ip_view_spots_checkbox_toggled(self, button):
        self.parent.parent.ImageProcessor.do_test()
        return

    def on_ip_view_bases_checkbox_toggled(self, button):
        return

    def on_ip_use_diff_imgs_checkbox_toggled(self, button):
        return

    def on_test1_button_clicked(self, button):
        print("Test 1 Button clicked")
        self.parent.parent.ImageProcessor.do_test()
        return

    def check_fixed_settings(self):
        is_fixed_capture, bad_params = self.parent.parent.Camera.is_fixed_capture()
        if not is_fixed_capture:
            d = Gtk.MessageDialog(
                transient_for=self.parent.mainWindow,
                modal=True,
                buttons=Gtk.ButtonsType.OK
            )
            bad_params_strs = "\n".join([f"{k}: {v}" for k,v in bad_params.items()])
            d.props.text = "CAMERA SETTINGS WARNING!"
            d.props.secondary_text = "\n\n".join([
                "The camera is not set for fixed exposure & white-balance.",
                "Inconsistent images may result due to following parameters:",
                bad_params_strs]
            )
            d.run()
            d.destroy()

    def on_event_tree_selection_changed(self, selection):
        # print(f"selection: {selection}")
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            print(f"\non_event_tree_selection_changed -- you selected: \'{getattr(model[treeiter][0], 'name', None)}\' ({model.get_path(treeiter)})")
            self.parent.DeleteEntryButton.set_sensitive(True)
        #     parent_iter = model.iter_parent(treeiter)
        #     has_child = model.iter_has_child(treeiter)
        #     if parent_iter is None:
        #         print(f"Parent: 'Root'")
        #     else:
        #         print(f"Parent: '{model[parent_iter][0].name}'")

        #     print(f"has_child: {has_child}\n")
        #     if model[treeiter][0].is_event or not has_child:
        #         print(f"\t-->event: ")
        #     else:
        #         print(f"\t-->event_group: ")
        else:
            # print("on_event_tree_selection_changed -- Nothing is selected")
            self.parent.DeleteEntryButton.set_sensitive(False)

        sel = self.parent.parent.Protocol.gtk_get_current_selection()
        print(f"name: {getattr(sel.entry, 'name', None)}  parent: {getattr(sel.parent, 'name', None)}  num_children: {sel.num_children}  num_siblings: {sel.num_siblings}")

    #Event List stuff
    def on_new_event_button_clicked(self, button):
        # Need to get selected event/group if there is one
        self.parent.parent.Protocol.gtk_new_event()
        # self.parent.parent.Protocol.load_from_treestore()

    def on_new_group_button_clicked(self, button):
        # Need to get selected event/group if there is one
        self.parent.parent.Protocol.gtk_new_group()
        # self.parent.parent.Protocol.load_from_treestore()

    def on_delete_entry_button_clicked(self, _):

        # Prompt the user to make sure they want to delete the event or eventgroup
        selection = self.parent.parent.Protocol.gtk_get_current_selection()
        d = Gtk.MessageDialog(
            transient_for=self.parent.mainWindow,
            modal=True,
            buttons=Gtk.ButtonsType.OK_CANCEL
        )
        entry_name = selection.entry.name
        if selection.entry.is_event:
            d.props.text = f"Are you sure you want to delete the event '{entry_name}'?"
        else:
            d.props.text = f"Are you sure you want to delete the event group '{entry_name}' (contains X sub-events)?"

        response = d.run()
        d.destroy()

        # We only terminate when the user presses the OK button
        if response == Gtk.ResponseType.OK:
            self.parent.parent.Protocol.gtk_delete_selection(selection)
        else:
            print(f"Not deleting {entry_name}")

    def on_event_tree_row_activated(self, *args):
        print(f"\non_event_tree_row_activated -- args: {args}")

    def on_event_tree_selection_notify_event(self, *args):
        print(f"\non_event_tree_selection_notify_event -- args: {args}")

    def on_event_tree_selection_request_event(self, *args):
        print(f"\non_event_tree_selection_request_event -- args: {args}")

# ~ builder.connect_signals(Handlers())

illegal_chars = [
'/',
'\\',
'<',
'>',
':',
'"',
'|',
'?',
'*',
' ',
]

def check_for_valid_filename(filename):
    ret = True
    for c in illegal_chars:
        if c in filename:
            ret = False
            break
    return ret
