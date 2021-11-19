import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, GObject, Gst

colors = ['None', 'UV', 'Blue', 'Orange']
        
class TrashButton(Gtk.Button):
    def __init__(self, *args):
        super(TrashButton,self).__init__(*args)
        img = Gtk.Image.new_from_icon_name("edit-delete-symbolic", 4)
        self.add(img)
        
class LEDColorComboBox(Gtk.ComboBoxText):
    def __init__(self, *args):
        super(LEDColorComboBox,self).__init__(*args)
        for color in colors:
            self.append(None, color)
        super(LEDColorComboBox,self).set_active(0)

class EventEntry(Gtk.HBox): 
    def __init__(self, parent, *args):
        super(EventEntry,self).__init__(*args)
        self.parent = parent
        self.ColorComboBox = LEDColorComboBox()
        self.TimeEntry = Gtk.Entry()
        self.TimeEntry.set_width_chars(14)
        self.DutyCycleEntry = Gtk.Entry()
        self.DutyCycleEntry.set_width_chars(3)
        self.CaptureToggleButton = Gtk.CheckButton()
        self.DeleteButton = TrashButton()
        self.pack_start( self.DeleteButton, False, False, 0)
        self.pack_start( self.ColorComboBox, False, False, 0)
        self.pack_start( self.TimeEntry, False, False, 0)
        self.pack_start( self.DutyCycleEntry, False, False, 0)
        self.pack_start( self.CaptureToggleButton, False, False, 0)
        self.DeleteButton.connect("clicked", self.on_event_delete_button)
        self.ColorComboBox.connect("changed", self.on_color_changed)
        self.CaptureToggleButton.set_active(False)
        self.CaptureToggleButton.set_sensitive(False)
        self.DutyCycleEntry.set_sensitive(False)

    def on_event_delete_button(self, button):
        idx = self.parent.EventEntries.index(self)
        self.destroy()
        # ~ print('idx to remove = '+str(idx))
        del(self.parent.EventEntries[idx])
    
    def on_color_changed(self, combo):
        active_idx = combo.get_active()
        if not active_idx:
            self.DutyCycleEntry.set_sensitive(False)
            self.CaptureToggleButton.set_active(False)
            self.CaptureToggleButton.set_sensitive(False)
        else:
            self.DutyCycleEntry.set_sensitive(True)
            self.CaptureToggleButton.set_active(True)
            self.CaptureToggleButton.set_sensitive(True)
            
    def exportEvent(self):
        color_idx = self.ColorComboBox.get_active()
        time = self.TimeEntry.get_text()
        dc = self.DutyCycleEntry.get_text()
        bCapture = self.CaptureToggleButton.get_active()
        try:
            time = float(time)
        except ValueError:
            raise ValueError('Invalid Time Entry!')
        if not color_idx:
            return (None, time, None, None)
        else:
            color = self.ColorComboBox.get_active_text()
            try:
                dc = int(dc)
            except ValueError:
                raise ValueError('Duty Cycle must be integer percent!')
            return (color, time, dc, bCapture)
