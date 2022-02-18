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

class ColorEntry(Gtk.HBox):
    def __init__(self, label, *args):
        super(ColorEntry,self).__init__(*args)
        self.Label = label
        self.DutyCycleEntry = Gtk.Entry()
        self.DutyCycleEntry.set_width_chars(3)
        self.pack_start( Gtk.Label(label), True, False, 0 )
        self.pack_start( self.DutyCycleEntry, False, False, 0 )
        
    def get_duty_cycle(self):
        dc = self.DutyCycleEntry.get_text()
        if not dc =='':
            try:
                dc = int(dc)
            except ValueError:
                print('Duty Cycle must be integer percent!')
                return
            if dc >0 and dc<=100:
                return dc
            elif dc <0 or dc>100:
                print('Duty Cycle must be positve and no more than 100!')
                return
            else: #equals 0
                return
        else:
            return

# ~ class LEDColorComboBox(Gtk.ComboBoxText):
    # ~ def __init__(self, *args):
        # ~ super(LEDColorComboBox,self).__init__(*args)
        # ~ for color in colors:
            # ~ self.append(None, color)
        # ~ super(LEDColorComboBox,self).set_active(0)

class LEDColorComboBox(Gtk.Grid):
    def __init__(self, *args):
        super(LEDColorComboBox,self).__init__(*args)
        self.ColorEntries = []
        color = 0
        for i in range(len(colors)-1):
            color +=1 
            self.ColorEntries.append( ColorEntry(colors[color]) )
            # ~ self.ColorButtons[-1].button.connect("toggled", self.get_active_colors)
            self.attach(self.ColorEntries[-1], 0, i, 1, 1)
        #TODO: bring back for rainbow board
        # ~ for i in range(2):
            # ~ for j in range(4):
                # ~ color += 1
                # ~ self.ColorButtons.append( ColorCheckButton(colors[color]) )
                # ~ self.attach(self.ColorButtons[-1], i, j, 1, 1)
            
    def get_active(self):
        colors_selected = dict()
        for color_entry in self.ColorEntries:
            color_dc = color_entry.get_duty_cycle()
            if not color_dc is None:
                colors_selected[color_entry.Label]=color_dc
        if bool(colors_selected):
            return colors_selected
        else:
            return
            
    def set_active(self, dDutyCycles):
        if dDutyCycles:
            for key in dDutyCycles.keys():
                self.ColorEntries[colors.index(key)-1].DutyCycleEntry.set_text(str(dDutyCycles[key]))
                
class EventEntry(Gtk.HBox): 
    def __init__(self, parent, *args):
        super(EventEntry,self).__init__(*args)
        self.parent = parent
        self.DeleteButton = TrashButton()
        self.ColorComboBox = LEDColorComboBox()
        self.PulseTimeEntry = Gtk.Entry()
        self.PulseTimeEntry.set_width_chars(14)
        self.PulseTimeEntry.set_valign(3)
        self.CaptureToggleButton = Gtk.CheckButton()
        self.CaptureToggleButton.set_margin_left(40)
        self.CaptureToggleButton.set_margin_right(40)
        self.CaptureGroupEntry = Gtk.Entry()
        self.CaptureGroupEntry.set_width_chars(2)
        self.CaptureBox = Gtk.VBox()
        self.CaptureBox.pack_start(self.CaptureToggleButton, False, False, 8)
        self.CaptureBox.pack_start(self.CaptureGroupEntry, False, False, 1)
        self.CaptureBox.set_valign(1)
        self.CaptureGroupEntry.set_sensitive(False)
        self.PostDelayEntry = Gtk.Entry()
        self.PostDelayEntry.set_width_chars(9)
        self.PostDelayEntry.set_valign(3)
        self.pack_start( self.DeleteButton, False, False, 0)
        self.pack_start( self.ColorComboBox, False, False, 0)
        self.pack_start( self.PulseTimeEntry, False, False, 0)
        self.pack_start( self.CaptureBox, False, False, 0)
        self.pack_start( self.PostDelayEntry, False, False, 0)
        self.DeleteButton.connect("clicked", self.on_event_delete_button)
        self.CaptureToggleButton.connect("toggled", self.on_capture_toggle_toggled)

    def on_event_delete_button(self, button):
        idx = self.parent.EventEntries.index(self)
        self.destroy()
        # ~ print('idx to remove = '+str(idx))
        del(self.parent.EventEntries[idx])
        
    def on_capture_toggle_toggled(self, switch):
            self.CaptureGroupEntry.set_sensitive(switch.get_active())

    def exportEvent(self):
        colorList = self.ColorComboBox.get_active()
        pulsetime = self.PulseTimeEntry.get_text()
        postdelay = self.PostDelayEntry.get_text()
        bCapture = self.CaptureToggleButton.get_active()

        if postdelay == '':
            postdelay = 0
        else:
            try:
                postdelay=float(postdelay)
            except ValueError:
                print('Post-Delay must be empty or a floating point number of seconds!')
                return

        if colorList is None:
            colorList = {}
            if not pulsetime:
                pulsetime = 0
            # pulsetime = 0
            # ~ bCapture = False

        try:
            pulsetime = float(pulsetime)
        except ValueError:
            print('Invalid Time Entry!')
            return False
        capture_grp = self.CaptureGroupEntry.get_text() if bCapture else None
        return (colorList, pulsetime, bCapture, postdelay, capture_grp)
