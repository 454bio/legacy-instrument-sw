#!/usr/bin/python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class Handlers:

    def __init__(self):
        self.LightOn = False
        self.awbGainsOn = True
        redGainScale.set_sensitive(self.awbGainsOn)
        blueGainScale.set_sensitive(self.awbGainsOn)
        self.isoButtonsOn = True
        self.ExpModeLastChoice = 1
        
    def on_image_denoise_button(self, button):
        if button.get_active():
            print('Image denoising on')
        else:
            print('Image denoising off')
        
    def on_blue_led_switch_activate(self, switch, gparam):
        if switch.get_active():
            print('Blue LED on')
        else:
            print('Blue LED off')
            
    def on_orange_led_switch_activate(self, switch, gparam):
        if switch.get_active():
            print('Orange LED on')
        else:
            print('Orange LED off')
            
    def reset_button_click(self, *args):
        # ~ print('test resetting')
        Gtk.main_quit(*args)
        
    def on_iso_auto_button(self, button):
        if button.get_active():
            print('auto iso button clicked')
    def on_iso_100_button(self, button):
        if button.get_active():
            print('100 iso button clicked')
    def on_iso_200_button(self, button):
        if button.get_active():
            print('200 iso button clicked')
    def on_iso_320_button(self, button):
        if button.get_active():
            print('320 iso button clicked')
    def on_iso_400_button(self, button):
        if button.get_active():
            print('400 iso button clicked')
    def on_iso_500_button(self, button):
        if button.get_active():
            print('500 iso button clicked')
    def on_iso_640_button(self, button):
        if button.get_active():
            print('640 iso button clicked')
    def on_iso_800_button(self, button):
        if button.get_active():
            print('800 iso button clicked')
            
            
    def on_awb_enable_button(self, switch, gparam):
        if switch.get_active():
            print('Enable AWB and disable gain sliders')
            self.awbGainsOn = False
            redGainScale.set_sensitive(self.awbGainsOn)
            blueGainScale.set_sensitive(self.awbGainsOn)

        else:
            print('Disable AWB and enable gain sliders')
            self.awbGainsOn = True
            redGainScale.set_sensitive(self.awbGainsOn)
            blueGainScale.set_sensitive(self.awbGainsOn)
            
    def on_exp_mode_changed(self, combo):
        active_idx = combo.get_active()
        if not active_idx==-1:
            print('New exposure mode: '+expModeComboBox.get_active_text())
            handle_id = expModeLockButton.connect("toggled", self.on_lock_exp_mode_button)
            if active_idx==0:
                expModeLockButton.handler_block(handle_id)
                expModeLockButton.set_active(True)
                expModeLockButton.handler_unblock(handle_id)
                self.enable_iso_buttons(False)
            else:
                self.ExpModeLastChoice = active_idx
                expModeLockButton.handler_block(handle_id)
                expModeLockButton.set_active(False)
                expModeLockButton.handler_unblock(handle_id)
                self.enable_iso_buttons(True)
                
    def on_lock_exp_mode_button(self, button):
        if button.get_active():
            expModeComboBox.set_active(0)
        else:
            expModeComboBox.set_active(self.ExpModeLastChoice)
            
    def enable_iso_buttons(self, isOn):
        isoButtonBox.set_sensitive(isOn)
        
        
        
    # ~ def on_offButton_clicked(self, widget):
        # ~ self.LightOn = False
        # ~ da.queue_draw() 
    
    # ~ # drawingarea1 is set as the userdata in glade
    # ~ def on_onButton_clicked(self, widget):
        # ~ self.LightOn = True
        # ~ widget.queue_draw()
 
    def on_window1_delete_event(self, *args):
        return True

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

builder = Gtk.Builder.new_from_file("zion_layout.glade")
mainWindow = builder.get_object("window1")
Gtk.Window.maximize(mainWindow)

redGainScale = builder.get_object("red_gain_scale")
blueGainScale = builder.get_object("blue_gain_scale")
expModeLockButton = builder.get_object("exp_mode_lock_button")
expModeComboBox = builder.get_object("exposure_mode_combobox")
isoButtonBox = builder.get_object("iso_button_box")

# ~ da    = builder.get_object("drawingarea1")

builder.connect_signals(Handlers())

Gtk.main()
