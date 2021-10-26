#!/usr/bin/python3

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, GObject, Gst

def get_handler_id(obj, signal_name):
    signal_id, detail = GObject.signal_parse_name(signal_name, obj, True)
    return GObject.signal_handler_find(obj, GObject.SignalMatchType.ID, signal_id, detail, None, None, None)


class Handlers:

    def __init__(self, gui):
        self.parent = gui
        self.ExpModeLastChoice = self.parent.Def_row_idx if self.parent.Def_row_idx else 1
        self.updateExpParams()
        self.source_id = GObject.timeout_add(2000, self.updateExpParams)
        #TODO: do temperature routine
        # ~ self.updateTemp()
        self.lastShutterTime = self.parent.parent.Camera.exposure_speed
        
    def on_window1_delete_event(self, *args):
        GObject.source_remove(self.source_id)
        Gtk.main_quit(*args)

    def updateExpParams(self):
        a_gain = float(self.parent.parent.Camera.analog_gain)
        d_gain = float(self.parent.parent.Camera.digital_gain)
        e_time = float(self.parent.parent.Camera.exposure_speed/1000.)
        self.parent.analogGainBuffer.set_text("{:04.3f}".format(a_gain))
        self.parent.digitalGainBuffer.set_text("{:04.3f}".format(d_gain))
        self.parent.expTimeBuffer.set_text("{:07.1f}".format(e_time))
        return True
        
    def reset_button_click(self, *args):
        self.parent.printToLog('Setting Video Params to Defaults')
        self.parent.BrightnessScale.set_value(self.parent.Default_Brightness)
        self.parent.ContrastScale.set_value(self.parent.Default_Contrast)
        self.parent.SaturationScale.set_value(self.parent.Default_Saturation)
        self.parent.SharpnessScale.set_value(self.parent.Default_Sharpness)
        
    def on_image_denoise_button(self, button):
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
        
    def on_contrast_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.parent.Camera.set_contrast(newval)
        self.parent.printToLog('Contrast set to '+str(newval))
    
    def on_saturation_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.parent.Camera.set_saturation(newval)
        self.parent.printToLog('Saturation set to '+str(newval))
            
    def on_sharpness_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.parent.Camera.set_sharpness(newval)
        self.parent.printToLog('Sharpness set to '+str(newval))

    # LED Control Section
    def on_blue_led_switch_activate(self, switch, gparam):
        if switch.get_active():
            self.parent.printToLog('Blue LED on')
            self.parent.parent.GPIO.turn_on_led('Blue')
        else:
            self.parent.printToLog('Blue LED off')
            self.parent.parent.GPIO.turn_off_led('Blue')
            
    def on_orange_led_switch_activate(self, switch, gparam):
        if switch.get_active():
            self.parent.printToLog('Orange LED on')
            self.parent.parent.GPIO.turn_on_led('Orange')
        else:
            self.parent.printToLog('Orange LED off')
            self.parent.parent.GPIO.turn_off_led('Orange')
            
    def on_uv_led_switch(self, switch, gparam):
        if switch.get_active():
            self.parent.printToLog('UV LED on')
            self.parent.parent.GPIO.turn_on_led('UV')
        else:
            self.parent.printToLog('UV LED off')
            self.parent.parent.GPIO.turn_off_led('UV')
            
    def on_uv_switch_safety_button(self, button):
        if button.get_active():
            self.parent.secretUVSwitchButton.set_visible(True)
            # ~ self.parent.secretUVSwitchButton.set_sensitive(True)
        else:
            self.parent.secretUVSwitchButton.set_visible(False)
            # ~ self.parent.secretUVSwitchButton.set_sensitive(False)
            
    def on_uv_led_pulse_button(self, button):
        newVal = self.parent.pulseTextInput.get_text()
        if newVal.isdecimal():
            self.parent.printToLog('Doing UV pulse of '+newVal+' milliseconds')
            newVal = int(newVal)
            #TODO: use different timer (from gtk?)
            self.parent.parent.GPIO.send_uv_pulse(newVal)
        else:
            self.parent.printToLog('Pulse time should be an integer number of milliseconds!')
    
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
        
    def on_set_exposure_time_button(self, button):
        newval = self.parent.expTimeBox.get_text()
        try:
            newval = float(newval)
        except ValueError: 
            self.parent.printToLog('Requested exposure time must be a number!')
            return
        if newval==0:
            self.parent.parent.Camera.shutter_speed = 0
            self.parent.parent.Camera.set_shutter_speed(0)
            self.parent.printToLog('Exposure time set to auto')
        else:
            self.parent.parent.Camera.shutter_speed = round(1000*newval)
            self.parent.parent.Camera.set_shutter_speed(round(1000*newval))
            self.parent.printToLog('Exposure time set to '+str(newval)+' ms')
        
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

    def on_awb_enable_button(self, switch, gparam):
        if switch.get_active():
            on_now = self.parent.parent.Camera.toggle_awb()
            if on_now[0]:
                self.parent.printToLog('Auto WB enabled')
                self.parent.redGainScale.set_sensitive(False)
                self.parent.blueGainScale.set_sensitive(False)
        else:
            on_now = self.parent.parent.Camera.toggle_awb()
            if not on_now[0]:
                self.parent.printToLog('Auto WB disabled')
                
                self.parent.redGainScale.set_sensitive(True)
                handle_id_red = get_handler_id(self.parent.redGainScale, "value-changed")
                self.parent.redGainScale.handler_block(handle_id_red)
                self.parent.redGainScale.set_value(on_now[1])
                self.parent.redGainScale.handler_unblock(handle_id_red)
                
                self.parent.blueGainScale.set_sensitive(True)
                handle_id_blue = get_handler_id(self.parent.blueGainScale, "value-changed")
                self.parent.blueGainScale.handler_block(handle_id_blue)
                self.parent.blueGainScale.set_value(on_now[2])
                self.parent.blueGainScale.handler_unblock(handle_id_blue)

    def on_red_gain_scale_value_changed(self, scale):
        newval = scale.get_value()
        self.parent.parent.Camera.set_red_gain(newval)
        self.parent.printToLog('WB Red Gain set to '+str(newval))

    def on_blue_gain_scale_value_changed(self, scale):
        newval = scale.get_value()
        self.parent.parent.Camera.set_red_gain(newval)
        self.parent.printToLog('WB Blue Gain set to '+str(newval))

    def on_capture_button_clicked(self, button):
        #TODO: get cropping from some self object here
        comment = self.parent.commentBox.get_text()
        self.parent.parent.SaveParameterFile(comment, False)
        self.parent.parent.CaptureImage(group='P')

    def on_run_program_button_clicked(self,button):
        self.parent.expModeComboBox.set_active(0)
        comment = self.parent.commentBox.get_text()
        self.parent.parent.SaveParameterFile(comment, True)
        # ~ self.parent.parent.RunProgram()

    def on_drawingarea1_draw(self,widget,cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        size = min(w,h)

        # ~ cr.set_source_rgb(0.0,0.2,0.0)
        # ~ cr.paint()

        # ~ if self.LightOn == True:
            # ~ cr.set_source_rgb(1.0,0.0,0.0)
        # ~ else:
            # ~ cr.set_source_rgb(0.2,0.0,0.0)
        # ~ cr.arc(0.5*w,0.5*h,0.5*size,0.0,6.3)
        # ~ cr.fill()
       
    def on_drawingarea1_button_press_event(self, *args):
        return
        
    # ~ def on_offButton_clicked(self, widget):
        # ~ self.LightOn = False
        # ~ da.queue_draw() 
    
    # ~ # drawingarea1 is set as the userdata in glade
    # ~ def on_onButton_clicked(self, widget):
        # ~ self.LightOn = True
        # ~ widget.queue_draw()

class ZionGUI():
    def __init__(self, initial_values, parent, glade_file='zion_layout.glade'):
        #Create Window and Maximize:
        self.builder = Gtk.Builder.new_from_file(glade_file)
        self.mainWindow = self.builder.get_object("window1")
        Gtk.Window.maximize(self.mainWindow)
        self.parent = parent

        #define default values
        self.Default_Brightness = initial_values['brightness']
        self.Default_Contrast = initial_values['contrast']
        self.Default_Saturation = initial_values['saturation']
        self.Default_Sharpness = initial_values['sharpness']

        self.BrightnessScale = self.builder.get_object("brightness_scale")
        self.BrightnessScale.set_value(initial_values['brightness'])
        self.ContrastScale = self.builder.get_object("contrast_scale")
        self.ContrastScale.set_value(initial_values['contrast'])
        self.SaturationScale = self.builder.get_object("saturation_scale")
        self.SaturationScale.set_value(initial_values['saturation'])
        self.SharpnessScale = self.builder.get_object("sharpness_scale")
        self.SharpnessScale.set_value(initial_values['sharpness'])

        self.AutoAwbButton = self.builder.get_object("auto_wb_switch")
        self.redGainScale = self.builder.get_object("red_gain_scale")
        self.redGainScale.set_value(initial_values['red_gain'])
        self.blueGainScale = self.builder.get_object("blue_gain_scale")
        self.blueGainScale.set_value(initial_values['blue_gain'])
        if initial_values['awb']=='off':
            self.AutoAwbButton.set_active(False)
            self.redGainScale.set_sensitive(True)
            self.blueGainScale.set_sensitive(True)
        else:
            self.AutoAwbButton.set_active(True)
            self.redGainScale.set_sensitive(False)
            self.blueGainScale.set_sensitive(False)

        self.expModeLockButton = self.builder.get_object("exp_mode_lock_button")
        self.expModeComboBox = self.builder.get_object("exposure_mode_combobox")
        self.isoButtonBox = self.builder.get_object("iso_button_box")
        self.expCompScale = self.builder.get_object("exposure_comp_scale")
        self.expTimeBuffer = self.builder.get_object("exposure_time_buffer")
        self.expTimeBox = self.builder.get_object("exposure_time_entry")
        self.analogGainBuffer = self.builder.get_object("analog_gain_buffer")
        self.digitalGainBuffer = self.builder.get_object("digital_gain_buffer")
        self.pulseTextInput = self.builder.get_object("uv_led_entry")
        self.secretUVSwitchButton = self.builder.get_object("uv_led_switch")
        self.logBuffer = self.builder.get_object("textbuffer_log")
        self.logView = self.builder.get_object("textview_log")
        self.temperatureBuffer = self.builder.get_object("temperature_buffer")
        
        self.commentBox = self.builder.get_object("comment_entry")
        
        if initial_values['exposure_mode']=='off':
            self.expModeLockButton.set_active(True)
            self.isoButtonBox.set_sensitive(False)
            self.expCompScale.set_sensitive(False)
            self.expModeComboBox.set_active(0)
            self.Def_row_idx = 0
        else:
            self.expModeLockButton.set_active(False)
            self.isoButtonBox.set_sensitive(True)
            self.expCompScale.set_sensitive(True)
            listStore = self.expModeComboBox.get_model()
            rowList = [row[0] for row in listStore]
            self.Def_row_idx = rowList.index(initial_values['exposure_mode'])
            self.expModeComboBox.set_active(self.Def_row_idx)
        
        self.builder.connect_signals(Handlers(self))
        
        # ~ self.printToLog('Center Pixel Value = '+str(self.parent.Camera.center_pixel_value))
        
    def printToLog(self, text):
        self.logBuffer.insert_at_cursor(text+'\n')
        mark = self.logBuffer.create_mark(None, self.logBuffer.get_end_iter(), False)
        self.logView.scroll_to_mark(mark, 0, False, 0,0)

# ~ da    = builder.get_object("drawingarea1")

# ~ builder.connect_signals(Handlers())

# ~ Gtk.main()
