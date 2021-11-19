import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, GObject, Gst

colors = ['None', 'UV', 'Blue', 'Orange', 'Red', 'Yellow', 'Green', 'Indigo', 'Violet']
        
class TrashButton(Gtk.Button):
    def __init__(self, *args):
        super(TrashButton,self).__init__(*args)
        img = Gtk.Image.new_from_icon_name("edit-delete-symbolic", 4)
        self.add(img)
        
# ~ class LEDColorComboBox(Gtk.ComboBoxText):
    # ~ def __init__(self, *args):
        # ~ super(LEDColorComboBox,self).__init__(*args)
        # ~ for color in colors:
            # ~ self.append(None, color)
        # ~ super(LEDColorComboBox,self).set_active(0)
        
class ColorCheckButton(Gtk.HBox):
    def __init__(self, label, *args):
        super(ColorCheckButton,self).__init__(*args)
        self.label = label
        self.pack_start( Gtk.CheckButton(), False, False, 0 )
        self.pack_start( Gtk.Label(label), False, False, 0 )

class LEDColorComboBox(Gtk.Grid):
    def __init__(self, *args):
        super(LEDColorComboBox,self).__init__(*args)
        self.ColorButtons = []
        color = 0
        for i in range(2):
            for j in range(4):
                color += 1
                self.ColorButtons.append( ColorCheckButton(colors[color]) )
                self.attach(self.ColorButtons[-1], i, j, 1, 1)
                
        # ~ self.attach(ColorCheckButton(),0,0,1,1)
        # ~ self.attach(ColorCheckButton('Blue'),0,1,1,1)
        # ~ self.attach(ColorCheckButton('Orange'),0,2,1,1)
        # ~ self.attach(ColorCheckButton('Red'),0,3,1,1)
        # ~ self.attach(ColorCheckButton('Green'),1,0,1,1)
        # ~ self.attach(ColorCheckButton('Yellow'),1,1,1,1)
        # ~ self.attach(ColorCheckButton('Indigo'),1,2,1,1)
        # ~ self.attach(ColorCheckButton('Violet'),1,3,1,1)
            
    def get_active_colors(self):
        colors_selected = []
        for color_button in self.ColorButtons:
            if color_button.get_active():
                colors_selected.append( color_button.label )

class EventEntry(Gtk.HBox): 
    def __init__(self, parent, *args):
        super(EventEntry,self).__init__(*args)
        self.parent = parent
        self.ColorComboBox = LEDColorComboBox()
        self.TimeEntry = Gtk.Entry()
        self.TimeEntry.set_width_chars(14)
        self.TimeEntry.set_valign(3)
        self.DutyCycleEntry = Gtk.Entry()
        self.DutyCycleEntry.set_width_chars(3)
        self.DutyCycleEntry.set_valign(3)
        self.CaptureToggleButton = Gtk.CheckButton()
        self.DeleteButton = TrashButton()
        self.pack_start( self.DeleteButton, False, False, 0)
        self.pack_start( self.ColorComboBox, False, False, 0)
        self.pack_start( self.TimeEntry, False, False, 0)
        self.pack_start( self.DutyCycleEntry, False, False, 0)
        self.pack_start( self.CaptureToggleButton, False, False, 0)
        self.DeleteButton.connect("clicked", self.on_event_delete_button)
        # ~ self.ColorComboBox.connect("changed", self.on_color_changed)
        # ~ self.CaptureToggleButton.set_active(False)
        # ~ self.CaptureToggleButton.set_sensitive(False)
        # ~ self.DutyCycleEntry.set_sensitive(False)

    def on_event_delete_button(self, button):
        idx = self.parent.EventEntries.index(self)
        self.destroy()
        # ~ print('idx to remove = '+str(idx))
        del(self.parent.EventEntries[idx])

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
