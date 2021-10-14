#!/usr/bin/python3

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class Handlers:

    def __init__(self):
        self.LightOn = False

    def on_quitButton_clicked(self, *args):
        Gtk.main_quit(*args)
    
    def on_offButton_clicked(self, widget):
        self.LightOn = False
        da.queue_draw() 
    
    # drawingarea1 is set as the userdata in glade
    def on_onButton_clicked(self, widget):
        self.LightOn = True
        widget.queue_draw()
 
    def on_window1_delete_event(self, *args):
        return True

    def on_drawingarea1_draw(self,widget,cr):
        w = widget.get_allocated_width()
        h = widget.get_allocated_height()
        size = min(w,h)

        cr.set_source_rgb(0.0,0.2,0.0)
        cr.paint()

        if self.LightOn == True:
            cr.set_source_rgb(1.0,0.0,0.0)
        else:
            cr.set_source_rgb(0.2,0.0,0.0)
        cr.arc(0.5*w,0.5*h,0.5*size,0.0,6.3)
        cr.fill()
       
    def on_drawingarea1_button_press_event(self, *args):
        return

builder = Gtk.Builder.new_from_file("zion_layout.glade")

da    = builder.get_object("drawingarea1")

# ~ builder.connect_signals(Handlers())

Gtk.main()
