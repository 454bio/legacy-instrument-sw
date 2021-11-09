#!/usr/bin/python3

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, GObject, Gst
import threading
from ZionEvents import print_eventList

def get_handler_id(obj, signal_name):
    signal_id, detail = GObject.signal_parse_name(signal_name, obj, True)
    return GObject.signal_handler_find(obj, GObject.SignalMatchType.ID, signal_id, detail, None, None, None)

class Placeholder(Gtk.Entry):
    def __init__(self, *args):
        super(Placeholder,self).__init__(*args)
        self.set_sensitive(False)
        
class TrashButton(Gtk.Button):
    def __init__(self, *args):
        super(TrashButton,self).__init__(*args)
        img = Gtk.Image.new_from_icon_name("edit-delete-symbolic", 4)
        self.add(img)
        
class LEDColorComboBox(Gtk.ComboBoxText):
    def __init__(self, *args):
        super(LEDColorComboBox,self).__init__(*args)
        self.append(None, 'Bl')
        self.append(None, 'Or')
        self.append(None, 'UV')

class EventTypeComboBox(Gtk.ComboBoxText):
    def __init__(self, *args):
        super(EventTypeComboBox,self).__init__(*args)
        self.append(None, 'None')
        self.append(None, 'LED')
        self.append(None, 'Capture')
        self.set_active(0)

class EventEntry(Gtk.HBox): 
    def __init__(self, parent, safe, *args):
        super(EventEntry,self).__init__(*args)
        self.parent = parent
        self.Safe = safe
        self.TimeEntry = Gtk.Entry()
        self.TimeEntry.set_width_chars(14)
        self.TypeComboBox = EventTypeComboBox()
        self.Parameter1 = Placeholder()
        self.Parameter2 = Placeholder()
        self.DeleteButton = TrashButton()
        if self.Safe:
            self.DeleteButton.set_sensitive(False)
        self.pack_start( self.DeleteButton, False, False, 0)
        self.pack_start( self.TimeEntry, False, False, 0)
        self.pack_start( self.TypeComboBox, False, False, 0)
        self.TypeComboBox.connect("changed", self.on_event_type_changed)
        self.DeleteButton.connect("clicked", self.on_event_delete_button)

    def on_event_delete_button(self, button):
        if not self.Safe:
            idx = self.parent.EventEntries.index(self)
            self.destroy()
            print('idx to remove = '+str(idx))
            del(self.parent.EventEntries[idx])

    def load_parameter_widgets(self):
        self.pack_start( self.Parameter1, False, False, 0 )
        self.pack_start( self.Parameter2, False, False, 0 )

    def on_event_type_changed(self, combo):
        active_idx = combo.get_active()
        if active_idx==1: #LED:
            self.Parameter1.destroy()
            self.Parameter2.destroy()
            self.Parameter1 = LEDColorComboBox()
            self.Parameter2 = Gtk.Entry()
            self.Parameter2.set_width_chars(14)
            self.load_parameter_widgets()
            self.show_all()
        elif active_idx==2: #Capture:
            self.Parameter1.destroy()
            self.Parameter2.destroy()
            self.Parameter1 = Gtk.Entry()
            self.Parameter1.set_width_chars(4)
            self.Parameter1.set_margin_right(1)
            self.Parameter2 = Gtk.Entry()
            self.Parameter2.set_width_chars(14)
            self.load_parameter_widgets()
            self.show_all()
        else:
            self.Parameter1.destroy()
            self.Parameter2.destroy()

# ~ class LED_EventEntry(EventEntry):
    # ~ def __init__(self, parent, safe, *args):
        # ~ super(LED_EventEntry, self).__init__(parent, safe, *args)
        # ~ self.Parameter1 = Gtk.ComboBoxText()
        # ~ self.Parameter1.append(None, 'Blue')
        # ~ self.Parameter1.append(None, 'Orange')
        # ~ self.Parameter1.append(None, 'UV')
        # ~ self.Parameter2 = Gtk.Entry() #This is numerical (duty cycle)
        # ~ super(LED_EventEntry,self).load_parameter_widgets()

# ~ class Capture_EventEntry(EventEntry):
    # ~ def __init__(self, parent, safe, *args):
        # ~ super(Capture_EventEntry, self).__init__(parent, safe, *args)
        # ~ self.Parameter1 = Gtk.Entry() # This is group (ie filename prefix), a string
        # ~ self.Parameter2 = Gtk.Entry() # This is a tuple representing cropping, or None
        # ~ super(Capture_EventEntry,self).load_parameter_widgets()

class Handlers:

    def __init__(self, gui):
        self.parent = gui
        self.ExpModeLastChoice = self.parent.Def_row_idx if self.parent.Def_row_idx else 1
        self.updateExpParams()
        self.source_id = GObject.timeout_add(2000, self.updateExpParams)
        # ~ self.updateTemp()
        # ~ self.source_id2 = GObject.timeout_add(2000, self.updateTemp)
        self.lastShutterTime = self.parent.parent.Camera.exposure_speed
        self.run_thread = None
        self.stop_run_thread = False
        self.load_eventList(self.parent.parent.EventList)
        
    def on_script_save_button_clicked(self, button):
        eventList = []
        for eventEntry in self.parent.EventEntries:
            eventType = eventEntry.TypeComboBox.get_active()
            eventTime = eventEntry.TimeEntry.get_text()
            # ~ self.parent.printToLog('event time: '+eventTime+' ms')
            if not eventTime.isdecimal():
                self.parent.printToLog('Event Time '+eventTime+' must be an integer in milliseconds!')
                return
            eventTime = int(eventTime)
            if eventType == 1: #LED Event
                if eventEntry.Parameter2.get_text().isdecimal():
                    dc = int(eventEntry.Parameter2.get_text())
                else:
                    self.parent.printToLog('Duty Cycle must be an integer percent!')
                    return
                event = (eventTime, 'LED')
                if eventEntry.Parameter1.get_active_text() == 'UV':
                    event += ('UV',)
                elif eventEntry.Parameter1.get_active_text() == 'Bl':
                    event += ('Blue',)
                elif eventEntry.Parameter1.get_active_text() == 'Or':
                    event += ('Orange',)
                event += (dc,)
                eventList.append(event)
            elif eventType == 2: #Capture event
                event = (eventTime, 'Capture', eventEntry.Parameter1.get_text())
                #TODO: check cropping is a valid tuple!
                cropping = eventEntry.Parameter2.get_text().strip(' ')
                cropping = None #if cropping=='' else cropping
                event += (cropping,)
                eventList.append(event)
            else: #TODO: should we add None "wait" events?
                pass
                # ~ print('this is an unknown event')
        # ~ print_eventList(eventList)
        N = self.parent.RepeatNEntry.get_value_as_int()
        # ~ with open('ZionDefaultProtocol.txt','w') as f:
            # ~ f.write('N='+str(N)+'\n')
            # ~ for e in eventList:
                # ~ f.write(str(e)+'\n')

    def on_script_load_button_clicked(self, button):
        response = self.parent.paramFileChooser.run()
        if response == Gtk.ResponseType.OK:
            filename = self.parent.paramFileChooser.get_filename()
            self.parent.paramFileChooser.hide()
            eventList = self.parent.parent.LoadProtocolFile(filename)
            self.load_eventList(eventList)
        elif response == Gtk.ResponseType.CANCEL:
            self.parent.paramFileChooser.hide()
            
    def load_eventList(self, eventList):
            self.parent.RepeatNEntry.set_value(eventList.N)
            self.parent.EventEntries[0].TimeEntry.set_text(str(eventList.Events[0][0]))
            if eventList.Events[0][1]=='LED':
                self.parent.EventEntries[0].TypeComboBox.set_active(1)
                if eventList.Events[0][2]=='Blue':
                    self.parent.EventEntries[0].Parameter1.set_active(0)
                elif eventList.Events[0][2]=='Orange':
                    self.parent.EventEntries[0].Parameter1.set_active(1)
                elif eventList.Events[0][2]=='UV':
                    self.parent.EventEntries[0].Parameter1.set_active(2)
                self.parent.EventEntries[0].Parameter2.set_text(str(eventList.Events[0][3]))
            elif eventList.Events[0][1]=='Capture':
                self.parent.EventEntries[0].TypeComboBox.set_active(2)
                self.parent.EventEntries[1].Parameter1.set_text(eventList.Events[0][2])
            else:
                self.parent.EventEntries[0].TypeComboBox.set_active(0)
                
            for event in eventList.Events[1:]:
                eventEntry = EventEntry(self.parent, False)
                eventEntry.TimeEntry.set_text(str(event[0]))
                if event[1]=='LED':
                    eventEntry.TypeComboBox.set_active(1)
                    if event[2]=='Blue':
                        eventEntry.Parameter1.set_active(0)
                    elif event[2]=='Orange':
                        eventEntry.Parameter1.set_active(1)
                    elif event[2]=='UV':
                        eventEntry.Parameter1.set_active(2)
                    eventEntry.Parameter2.set_text(str(event[3]))
                elif event[1]=='Capture':
                    eventEntry.TypeComboBox.set_active(2)
                    eventEntry.Parameter1.set_text(event[2])
                else:
                    eventEntry.TypeComboBox.set_active(0)
                self.parent.EventEntries.append( eventEntry )
                self.parent.EventList.pack_start( self.parent.EventEntries[-1], False, False, 0 )
            self.parent.EventList.show_all()

    def on_window1_delete_event(self, *args):
        self.parent.parent.GPIO.cancel_PWM()
        GObject.source_remove(self.source_id)
        # ~ GObject.source_remove(self.source_id2)
        Gtk.main_quit(*args)

    def updateExpParams(self):
        a_gain = float(self.parent.parent.Camera.analog_gain)
        d_gain = float(self.parent.parent.Camera.digital_gain)
        e_time = float(self.parent.parent.Camera.exposure_speed/1000.)
        self.parent.analogGainBuffer.set_text("{:04.3f}".format(a_gain))
        self.parent.digitalGainBuffer.set_text("{:04.3f}".format(d_gain))
        self.parent.expTimeBuffer.set_text("{:07.1f}".format(e_time))
        return True
        
    def updateTemp(self):
        temp = self.parent.parent.GPIO.read_temperature()
        if temp:
            self.parent.temperatureBuffer.set_text("{:02.1f}".format(temp))
        else:
            self.parent.temperatureBuffer.set_text("-")
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
    def on_blue_led_button_toggled(self, switch):
        if switch.get_active():
            try:
                dc = int(self.parent.blueDCEntry.get_text())
            except ValueError:
                self.parent.printToLog('Duty Cycle must be an integer from 0-100!')
                return
            self.parent.printToLog('Blue LED on, set to '+str(dc)+'% duty cycle')
            self.parent.parent.GPIO.enable_led('Blue',float(dc/100.))
        else:
            self.parent.printToLog('Blue LED off')
            self.parent.parent.GPIO.enable_led('Blue',0)
            
    def on_orange_led_button_toggled(self, switch):
        if switch.get_active():
            try:
                dc = int(self.parent.orangeDCEntry.get_text())
            except ValueError:
                self.parent.printToLog('Duty Cycle must be an integer from 0-100!')
                return
            self.parent.printToLog('Orange LED on, set to '+str(dc)+'% duty cycle')
            self.parent.parent.GPIO.enable_led('Orange',float(dc/100.))
        else:
            self.parent.printToLog('Orange LED off')
            self.parent.parent.GPIO.enable_led('Orange',0)
            
    def on_uv_led_button_toggled(self, switch):
        if switch.get_active():
            try:
                dc = int(self.parent.uvDCEntry.get_text())
            except ValueError:
                self.parent.printToLog('Duty Cycle must be an integer from 0-100!')
                return
            self.parent.printToLog('UV LED on, set to '+str(dc)+'% duty cycle')
            self.parent.parent.GPIO.enable_led('UV',float(dc/100.))
        else:
            self.parent.printToLog('UV LED off')
            self.parent.parent.GPIO.enable_led('UV',0)
            
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
            
    def on_led__off_button_clicked(self, button):
        self.parent.parent.GPIO.cancel_PWM()
        self.parent.blueSwitch.set_active(False)
        self.parent.orangeSwitch.set_active(False)
        self.parent.uvSwitch.set_active(False)
    
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
        capture_thread = threading.Thread(target=self.parent.parent.CaptureImage, kwargs={'group': 'P', 'comment': comment,'verbose': True})
        capture_thread.daemon = True
        capture_thread.start()

    def on_run_program_button_clicked(self,button):
        if button.get_active():
            self.parent.expModeComboBox.set_active(0)
            comment = self.parent.commentBox.get_text()
            self.parent.parent.SaveParameterFile(comment, True)
            self.parent.parent.SaveProtocolFile()
            self.stop_run_thread = False
            # ~ button.set_sensitive(False)
            self.run_thread = threading.Thread(target=self.parent.parent.RunProgram, args=(lambda:self.stop_run_thread,) )
            self.run_thread.daemon=True
            self.run_thread.start()
        
    def on_stop_program_button_clicked(self, button):
        if self.run_thread:
            self.stop_run_thread = True
            self.parent.printToLog('Requesting script to stop')
            print('Requesting thread to stop')
            self.run_thread.join()
            self.run_thread = None
            self.parent.parent.GPIO.enable_led('UV',0)
            self.parent.parent.GPIO.enable_led('Blue',0)
            self.parent.parent.GPIO.enable_led('Orange',0)
            self.parent.runProgramButton.set_active(False)
            self.parent.runProgramButton.set_sensitive(True)
        
    def on_new_event_button_clicked(self, button):
        self.parent.EventEntries.append( EventEntry(self.parent, False) )
        self.parent.EventList.pack_start( self.parent.EventEntries[-1], False, False, 0 )
        self.parent.EventList.show_all()
        
    def on_event_scroll_size_allocate(self, scroll, rectangle):
        #TODO scroll to bottom
        # ~ adjustment = scroll.get_vadjustment()
        # ~ adjustment.set_value(adjustment.get_upper())
        adjustment = scroll.get_vadjustment()
        adjustment.set_value(adjustment.get_upper())
        # ~ Gtk.Widget.show(self.parent.EventListScroll)
        # ~ mark = self.logBuffer.create_mark(None, self.logBuffer.get_end_iter(), False)
        # ~ self.logView.scroll_to_mark(mark, 0, False, 0,0)
        
    def on_param_file_chooser_dialog_realize(self, widget):
        Gtk.Window.maximize(self.parent.paramFileChooser)
        
    def on_load_params_button(self,button):
        response = self.parent.paramFileChooser.run()
        if response == Gtk.ResponseType.OK:
            filename = self.parent.paramFileChooser.get_filename()
            self.parent.paramFileChooser.hide()
            params = self.parent.parent.LoadParameterFile(filename)
                
            handler_id = get_handler_id(self.parent.BrightnessScale, "value-changed")
            self.parent.BrightnessScale.handler_block(handler_id)
            self.parent.BrightnessScale.set_value(params['brightness'])
            self.parent.BrightnessScale.handler_unblock(handler_id)
                
            handler_id = get_handler_id(self.parent.ContrastScale, "value-changed")
            self.parent.ContrastScale.handler_block(handler_id)
            self.parent.ContrastScale.set_value(params['contrast'])
            self.parent.ContrastScale.handler_unblock(handler_id)

            handler_id = get_handler_id(self.parent.SaturationScale, "value-changed")
            self.parent.SaturationScale.handler_block(handler_id)
            self.parent.SaturationScale.set_value(params['saturation'])
            self.parent.SaturationScale.handler_unblock(handler_id)

            handler_id = get_handler_id(self.parent.SharpnessScale, "value-changed")
            self.parent.SharpnessScale.handler_block(handler_id)
            self.parent.SharpnessScale.set_value(params['sharpness'])
            self.parent.SharpnessScale.handler_unblock(handler_id)

            handler_id = get_handler_id(self.parent.expCompScale, "value-changed")                
            self.parent.expCompScale.handler_block(handler_id)
            self.parent.expCompScale.set_value(params['exposure_comp'])
            self.parent.expCompScale.handler_unblock(handler_id)

            handler_id = get_handler_id(self.parent.imageDenoiseButton, "toggled")
            self.parent.imageDenoiseButton.handler_block(handler_id)
            self.parent.imageDenoiseButton.set_active(params['denoise'])
            self.parent.imageDenoiseButton.handler_unblock(handler_id)

            handler_id_1 = get_handler_id(self.parent.isoButtonAuto, "toggled")
            self.parent.isoButtonAuto.handler_block(handler_id_1)
            handler_id_2 = get_handler_id(self.parent.isoButton100, "toggled")
            self.parent.isoButton100.handler_block(handler_id_2)
            handler_id_3 = get_handler_id(self.parent.isoButton200, "toggled")
            self.parent.isoButton200.handler_block(handler_id_3)
            handler_id_4 = get_handler_id(self.parent.isoButton320, "toggled")
            self.parent.isoButton320.handler_block(handler_id_4)
            handler_id_5 = get_handler_id(self.parent.isoButton400, "toggled")
            self.parent.isoButton400.handler_block(handler_id_5)
            handler_id_6 = get_handler_id(self.parent.isoButton500, "toggled")
            self.parent.isoButton500.handler_block(handler_id_6)
            handler_id_7 = get_handler_id(self.parent.isoButton640, "toggled")
            self.parent.isoButton640.handler_block(handler_id_7)
            handler_id_8 = get_handler_id(self.parent.isoButton800, "toggled")
            self.parent.isoButton800.handler_block(handler_id_8)
            handler_id_9 = get_handler_id(self.parent.expModeComboBox, "changed")
            handler_id_10 = get_handler_id(self.parent.expModeLockButton, "toggled")
            handler_id_11 = get_handler_id(self.parent.expCompScale, "value-changed")
            self.parent.expModeComboBox.handler_block(handler_id_9)
            self.parent.expModeLockButton.handler_block(handler_id_10)
            self.parent.expCompScale.handler_block(handler_id_11)
                
            if params['ISO']==0:
                self.parent.isoButtonAuto.set_active(True)
            elif params['ISO']==100:
                self.parent.isoButton100.set_active(True)
            elif params['ISO']==200:
                self.parent.isoButton200.set_active(True)
            elif params['ISO']==320:
                self.parent.isoButton320.set_active(True)
            elif params['ISO']==400:
                self.parent.isoButton400.set_active(True)
            elif params['ISO']==500:
                self.parent.isoButton500.set_active(True)
            elif params['ISO']==640:
                self.parent.isoButton640.set_active(True)
            elif params['ISO']==800:
                self.parent.isoButton800.set_active(True)
                  
            self.parent.expCompScale.set_value(params['exposure_comp'])
                
            listStore = self.parent.expModeComboBox.get_model()
            rowList = [row[0] for row in listStore]
            row_idx = rowList.index(params['exposure_mode'])
            self.parent.expModeComboBox.set_active(row_idx)
            if not row_idx:
                self.parent.expModeLockButton.set_active(True)
                self.parent.expCompScale.set_sensitive(False)
                self.parent.isoButtonBox.set_sensitive(False)
            else:
                self.parent.expModeLockButton.set_active(False)
                self.parent.expCompScale.set_sensitive(True)
                self.parent.isoButtonBox.set_sensitive(True)
                    
            self.parent.expModeComboBox.handler_unblock(handler_id_9)
            self.parent.expModeLockButton.handler_unblock(handler_id_10)
            self.parent.expCompScale.handler_unblock(handler_id_11)
            self.parent.isoButtonAuto.handler_unblock(handler_id_1)
            self.parent.isoButton100.handler_unblock(handler_id_2)
            self.parent.isoButton200.handler_unblock(handler_id_3)
            self.parent.isoButton320.handler_unblock(handler_id_4)
            self.parent.isoButton400.handler_unblock(handler_id_5)
            self.parent.isoButton500.handler_unblock(handler_id_6)
            self.parent.isoButton640.handler_unblock(handler_id_7)
            self.parent.isoButton800.handler_unblock(handler_id_8)
                
                
            handler_id_1 = get_handler_id(self.parent.AutoAwbButton, "notify::active")
            handler_id_2 = get_handler_id(self.parent.redGainScale, "value-changed")                
            handler_id_3 = get_handler_id(self.parent.blueGainScale, "value-changed")
            self.parent.AutoAwbButton.handler_block(handler_id_1)
            self.parent.redGainScale.handler_block(handler_id_2)
            self.parent.blueGainScale.handler_block(handler_id_3)
               
            self.parent.redGainScale.set_value(params['red_gain'])
            self.parent.blueGainScale.set_value(params['blue_gain'])
            if params['awb']=='off':
                self.parent.AutoAwbButton.set_active(False)
                self.parent.redGainScale.set_sensitive(True)
                self.parent.blueGainScale.set_sensitive(True)
            elif params['awb']=='auto':
                self.parent.AutoAwbButton.set_active(True)
                self.parent.redGainScale.set_sensitive(False)
                self.parent.blueGainScale.set_sensitive(True)
                    
            self.parent.AutoAwbButton.handler_unblock(handler_id_1)
            self.parent.redGainScale.handler_unblock(handler_id_2)
            self.parent.blueGainScale.handler_unblock(handler_id_3)
                
        elif response == Gtk.ResponseType.CANCEL:
            # ~ print('cancel')
            self.parent.paramFileChooser.hide()
            
    def on_param_file_chooser_close(self, *args):
        self.parent.paramFileChooser.hide()

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
        
        # ~ self.pulseTextInput = self.builder.get_object("uv_led_entry")
        # ~ self.secretUVSwitchButton = self.builder.get_object("uv_led_switch")
        self.blueDCEntry = self.builder.get_object("blue_led_dc_entry")
        self.orangeDCEntry = self.builder.get_object("orange_led_dc_entry")
        self.uvDCEntry = self.builder.get_object("uv_led_dc_entry")
        self.blueSwitch = self.builder.get_object("blue_led_switch")
        self.orangeSwitch = self.builder.get_object("orange_led_switch")
        self.uvSwitch = self.builder.get_object("uv_led_switch")
        
        self.logBuffer = self.builder.get_object("textbuffer_log")
        self.logView = self.builder.get_object("textview_log")
        self.temperatureBuffer = self.builder.get_object("temperature_buffer")
        
        self.imageDenoiseButton = self.builder.get_object("denoise_button")
        
        self.isoButtonAuto = self.builder.get_object("radiobutton0")
        self.isoButton100 = self.builder.get_object("radiobutton1")
        self.isoButton200 = self.builder.get_object("radiobutton2")
        self.isoButton320 = self.builder.get_object("radiobutton3")
        self.isoButton400 = self.builder.get_object("radiobutton4")
        self.isoButton500 = self.builder.get_object("radiobutton5")
        self.isoButton640 = self.builder.get_object("radiobutton6")
        self.isoButton800 = self.builder.get_object("radiobutton7")

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
            
        self.paramFileChooser = self.builder.get_object('param_file_chooser_dialog')
        
        self.EventList = self.builder.get_object("event_list")
        self.EventEntries = [EventEntry(self, True)]
        self.EventList.pack_start(self.EventEntries[0], False, True, 0)
        self.EventList.show_all()
        self.EventListScroll = self.builder.get_object("eventlist_scroll")
        
        self.runProgramButton = self.builder.get_object("run_program_button")
        
        self.RepeatNEntry = self.builder.get_object("repeat_n_spin_button")
        
        self.builder.connect_signals(Handlers(self))
        
        # ~ self.printToLog('Center Pixel Value = '+str(self.parent.Camera.center_pixel_value))
        
    def printToLog(self, text):
        self.logBuffer.insert_at_cursor(text+'\n')
        mark = self.logBuffer.create_mark(None, self.logBuffer.get_end_iter(), False)
        self.logView.scroll_to_mark(mark, 0, False, 0,0)

# ~ da    = builder.get_object("drawingarea1")

# ~ builder.connect_signals(Handlers())

# ~ Gtk.main()
