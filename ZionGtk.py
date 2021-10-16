#!/usr/bin/python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject

def get_handler_id(obj, signal_name):
    signal_id, detail = GObject.signal_parse_name(signal_name, obj, True)
    return GObject.signal_handler_find(obj, GObject.SignalMatchType.ID, signal_id, detail, None, None, None)


class Handlers:

    def __init__(self, gui):
#        self.LightOn = False
        self.parent = gui
        self.parent.redGainScale.set_sensitive(True)
        self.parent.blueGainScale.set_sensitive(True)
        
        #TODO: fix inital exp mode based on input
        self.ExpModeLastChoice = 2
        
        self.updateExpParams()
        self.source_id = GObject.timeout_add(2000, self.updateExpParams)
        # ~ self.updateTemp()
        
    def on_window1_delete_event(self, *args):
        GObject.source_remove(self.source_id)
        Gtk.main_quit(*args)
        
    def printToLog(self, text):
        self.parent.logBuffer.insert_at_cursor(text+'\n')
        mark = self.parent.logBuffer.create_mark(None, self.parent.logBuffer.get_end_iter(), False)
        self.parent.logView.scroll_to_mark(mark, 0, False, 0,0)

    def updateExpParams(self):
        a_gain = float(self.parent.Camera.analog_gain)
        d_gain = float(self.parent.Camera.digital_gain)
        e_time = float(self.parent.Camera.exposure_speed/1000.)
        self.parent.analogGainBuffer.set_text("{:.3f}".format(a_gain))
        self.parent.digitalGainBuffer.set_text("{:.3f}".format(d_gain))
        self.parent.expTimeBuffer.set_text("{:.3f}".format(e_time))
        return True
        
    def reset_button_click(self, *args):
        self.printToLog('Setting Video Params to Defaults')
        self.parent.BrightnessScale.set_value(50)
        self.parent.ContrastScale.set_value(50)
        self.parent.SaturationScale.set_value(100)
        self.parent.SharpnessScale.set_value(0)
        self.updateExpParams()
        
    def on_image_denoise_button(self, button):
        if button.get_active():
            self.printToLog('Image denoising on')
            self.parent.Camera.image_denoising=True
        else:
            self.printToLog('Image denoising off')
            self.parent.Camera.image_denoising=False
            
    def on_brightness_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.Camera.brightness=newval
        self.printToLog('Brightness set to '+str(newval))
        
    def on_contrast_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.Camera.contrast=newval
        self.printToLog('Contrast set to '+str(newval))
    
    def on_saturation_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.Camera.saturation=newval
        self.printToLog('Saturation set to '+str(newval))
            
    def on_sharpness_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.Camera.sharpness=newval
        self.printToLog('Sharpness set to '+str(newval))

    # LED Control Section
    def on_blue_led_switch_activate(self, switch, gparam):
        if switch.get_active():
            self.printToLog('Blue LED on')
            self.parent.Camera.GPIO.turn_on_led('Blue')
        else:
            self.printToLog('Blue LED off')
            self.parent.Camera.GPIO.turn_off_led('Blue')
            
    def on_orange_led_switch_activate(self, switch, gparam):
        if switch.get_active():
            self.printToLog('Orange LED on')
            self.parent.Camera.GPIO.turn_off_led('Orange')
        else:
            self.printToLog('Orange LED off')
            self.parent.Camera.GPIO.turn_off_led('Orange')
            
    def on_uv_led_switch(self, switch, gparam):
        if switch.get_active():
            self.printToLog('UV LED on')
            self.parent.Camera.GPIO.turn_off_led('UV')
        else:
            self.printToLog('UV LED off')
            self.parent.Camera.GPIO.turn_off_led('UV')
            
    def on_uv_switch_safety_button(self, button):
        if button.get_active():
            self.parent.secretUVSwitchButton.set_visible(True)
        else:
            self.parent.secretUVSwitchButton.set_visible(False)
            
    def on_uv_led_pulse_button(self, button):
        newVal = self.parent.pulseTextInput.get_text()
        if newVal.isdecimal():
            self.printToLog('Doing UV pulse of '+newVal+' milliseconds')
            newVal = int(newVal)
            #TODO: fill in hook for sending pulse
        else:
            print('Pulse time should be an integer number of milliseconds.')
            
    def on_iso_auto_button(self, button):
        if button.get_active():
            self.printToLog('ISO set to auto')
            self.parent.Camera.iso = 0
    def on_iso_100_button(self, button):
        if button.get_active():
            self.printToLog('ISO set to 100')
            self.parent.Camera.iso = 100
    def on_iso_200_button(self, button):
        if button.get_active():
            self.printToLog('ISO set to 200')
            self.parent.Camera.iso = 200
    def on_iso_320_button(self, button):
        if button.get_active():
            self.printToLog('ISO set to 320')
            self.parent.Camera.iso = 320
    def on_iso_400_button(self, button):
        if button.get_active():
            self.printToLog('ISO set to 400')
            self.parent.Camera.iso = 400
    def on_iso_500_button(self, button):
        if button.get_active():
            self.printToLog('ISO set to 500')
            self.parent.Camera.iso = 500
    def on_iso_640_button(self, button):
        if button.get_active():
            self.printToLog('ISO set to 640')
            self.parent.Camera.iso = 640
    def on_iso_800_button(self, button):
        if button.get_active():
            self.printToLog('ISO set to 800')
            self.parent.Camera.iso = 800
            
    def on_exposure_comp_scale_value_changed(self, scale):
        newval = int(scale.get_value())
        self.parent.Camera.exposure_compensation = newval
        self.printToLog('Exposure compensation set to '+str(newval))

    def on_exp_mode_changed(self, combo):
        active_idx = combo.get_active()
        if not active_idx==-1:
            newmode = self.parent.expModeComboBox.get_active_text()
            self.parent.Camera.exposure_mode = newmode
            self.printToLog('New exposure mode: '+newmode)
            handle_id = get_handler_id(self.parent.expModeLockButton, "toggled")
            if active_idx==0:
                self.parent.expModeLockButton.handler_block(handle_id)
                self.parent.expModeLockButton.set_active(True)
                self.parent.expModeLockButton.handler_unblock(handle_id)
                self.enable_exp_params(False)
            else:
                self.ExpModeLastChoice = active_idx
                self.parent.expModeLockButton.handler_block(handle_id)
                self.parent.expModeLockButton.set_active(False)
                self.parent.expModeLockButton.handler_unblock(handle_id)
                self.enable_exp_params(True)
    def on_lock_exp_mode_button(self, button):
        if button.get_active():
            self.parent.expModeComboBox.set_active(0)
        else:
            self.parent.expModeComboBox.set_active(self.ExpModeLastChoice)
    def enable_exp_params(self, isOn):
        #TODO: put this back in once we get the hang of it
        self.parent.isoButtonBox.set_sensitive(isOn)
        # ~ expCompScale.set_sensitive(isOn)
        return

    def on_awb_enable_button(self, switch, gparam):
        if switch.get_active():
            on_now = self.parent.Camera.toggle_awb()
            if on_now[0]:
                self.printToLog('Auto WB enabled')
                self.parent.redGainScale.set_sensitive(False)
                self.parent.blueGainScale.set_sensitive(False)
        else:
            on_now = self.parent.Camera.toggle_awb()
            if not on_now[0]:
                self.printToLog('Auto WB disabled')
                
                self.parent.redGainScale.set_sensitive(True)
                handle_id_red = get_handler_id(self.parent.redGainScale, "value-changed")
                self.parent.redGainScale.handler_block(handle_id_red)
                self.parent.redGainScale.set_value(on_now[1])
                self.parent.redGainScale.handler_unblock(handle_id_red)
                
                self.parent.blueGainScale.set_sensitive(True)
                handle_id_blue = get_handler_id(self.parent.blueGainScale, "value-changed")
                self.parent.blueGainScale.handler_block(handle_id_blue)
                self.parent.blueGainScale.set_value(on_now[2])
                self.parent.redGainScale.handler_unblock(handle_id_blue)

    def on_red_gain_scale_value_changed(self, scale):
        newval = scale.get_value()
        gains = self.parent.Camera.awb_gains
        self.parent.Camera.awb_gains = (newval, gains[1])
        self.printToLog('WB Red Gain set to '+str(newval))
            
    def on_blue_gain_scale_value_changed(self, scale):
        newval = scale.get_value()
        gains = self.parent.Camera.awb_gains
        self.parent.Camera.awb_gains = (gains[0], newval)
        self.printToLog('WB Blue Gain set to '+str(newval))
        
    def on_capture_button_clicked(self, button):
        #TODO:fix capture file naming here
        self.parent.Camera.capture(('','test_pic'), cropping=(0,0,1,1), baseTime=0, group='P')              


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
    def __init__(self, camera, initExpMode):#, gladefile, paramDefs=None):
        #Create Window and Maximize:
        self.builder = Gtk.Builder.new_from_file("zion_layout.glade")
        self.mainWindow = self.builder.get_object("window1")
        Gtk.Window.maximize(self.mainWindow)
        self.Camera = camera

    #Objects needed for handlers:
        self.redGainScale = self.builder.get_object("red_gain_scale")
        self.blueGainScale = self.builder.get_object("blue_gain_scale")
        self.expModeLockButton = self.builder.get_object("exp_mode_lock_button")
        self.expModeComboBox = self.builder.get_object("exposure_mode_combobox")
        self.isoButtonBox = self.builder.get_object("iso_button_box")
        self.expCompScale = self.builder.get_object("exposure_comp_scale")
        self.pulseTextInput = self.builder.get_object("uv_led_entry")
        self.secretUVSwitchButton = self.builder.get_object("uv_led_switch")
        self.logBuffer = self.builder.get_object("textbuffer_log")
        self.logView = self.builder.get_object("textview_log")
        self.temperatureBuffer = self.builder.get_object("temperature_buffer")
        self.analogGainBuffer = self.builder.get_object("analog_gain_buffer")
        self.digitalGainBuffer = self.builder.get_object("digital_gain_buffer")
        self.expTimeBuffer = self.builder.get_object("exposure_time_buffer")
        self.expTimeBox = self.builder.get_object("exposure_time_entry")
        self.BrightnessScale = self.builder.get_object("brightness_scale")
        self.ContrastScale = self.builder.get_object("contrast_scale")
        self.SaturationScale = self.builder.get_object("saturation_scale")
        self.SharpnessScale = self.builder.get_object("sharpness_scale")
        
        self.builder.connect_signals(Handlers(self))

# ~ da    = builder.get_object("drawingarea1")

# ~ builder.connect_signals(Handlers())

# ~ Gtk.main()
