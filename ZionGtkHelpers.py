
import numpy as np
from gi.repository import GObject, GdkPixbuf, Gdk, GLib

NUM_CHANNELS = 5

class PictureViewFromFile(GObject.Object):
    
    def __init__(self, drawing_area_widget, default_image_path):
        GObject.Object.__init__(self)
        self._area = drawing_area_widget
        self._img_path = self._default_img_path = default_image_path
        self._pixbuf = GdkPixbuf.Pixbuf.new_from_file(self._img_path)
        self._img_surface = None
        self._img_offset = (0.0, 0.0)
        self._img_scale_factor = (1.0, 1.0)

    @GObject.Property
    def area(self):
        return self._area

    @GObject.Property(type=str)
    def image_path(self):
        return self._img_path

    @image_path.setter
    def image_path(self, new_path):
        # self._pixbuf = GdkPixbuf.Pixbuf.new_from_file(new_path)
        # self._img_surface = Gdk.cairo_surface_create_from_pixbuf(
        #     self._pixbuf, 1, None
        # )
        self._img_path = new_path
        self._pixbuf = GdkPixbuf.Pixbuf.new_from_file(self._img_path)
        self.init_surface()
        self._area.queue_draw()

    @GObject.Property
    def allocated_width(self):
        if self._area:
            return self._area.get_allocated_width()
        else:
            return 0

    @GObject.Property
    def allocated_height(self):
        if self._area:
            return self._area.get_allocated_height()
        else:
            return 0

    @GObject.Property
    def parent_gdk_window(self):
        return self._area.get_toplevel().get_window()

    def clear_image(self):
        self.image_path = self._default_img_path
        
    def get_bbox(self):
        """ Returns the x,y and width,height of the bounding box for the drawing area
            in absolute pixel coordinates """
            
        parent_window = self._area.get_toplevel()

        # Use the GDK window instead of the GTK window
        # since get_position will take into consideration the
        # title bar in the case of the GDK method
        gdk_window = parent_window.get_window()
        window_x, window_y = gdk_window.get_position()
        # w = self.allocated_width
        # h = self.allocated_height
        w = self._area.get_allocated_width()
        h = self._area.get_allocated_height()
        # print(f"window (x,y): ({window_x}, {window_y})  area (w,h): ({w, h})")

        rel_x, rel_y = self._area.translate_coordinates(parent_window, 0, 0)
        # print(f"rel_x, rel_y: ({rel_x}, {rel_y})")

        return window_x + rel_x, window_y + rel_y, w, h

    def get_scale_factor(self):
        width_sf =  self._area.get_allocated_width() / self._pixbuf.get_width()
        height_sf =  self._area.get_allocated_height() / self._pixbuf.get_height()
        
        # print(f"sf (width,height): {width_sf:0.6f},{height_sf:0.6f}")
        if width_sf < height_sf:
            sf = width_sf
            excess_height = self._area.get_allocated_height() - sf * self._pixbuf.get_height()
            # print(f"Excess height: {excess_height:0.1f}")
            surface_offset = (0, excess_height / 2 / sf)
        else:
            sf = height_sf
            excess_width = self._area.get_allocated_width() - sf * self._pixbuf.get_width()
            # print(f"Excess width: {excess_width:0.1f}")
            surface_offset = (excess_width / 2 / sf, 0)
        return (sf, sf), surface_offset

    def init_surface(self):
        # Destroy previous buffer
        if self._img_surface is not None:
            self._img_surface.finish()
            self._img_surface = None

        # Create a new buffer
        self._img_surface = Gdk.cairo_surface_create_from_pixbuf(
            self._pixbuf, 1, None
        )
        self._img_scale_factor, self._img_offset = self.get_scale_factor()
        # print(f"sf: {self._img_scale_factor}  offset: {self._img_offset}")

    def on_configure(self, area, event, data=None):
        # doesn't appear to need a "redraw", just init the surface
        self.init_surface()

        # "redraw" -- Keeping this around as an example of a context 
        # context = cairo.Context(self._img_surface)
        # print(f"sf, surface_offset: {self._img_scale_factor}, {self._img_offset}")
        # context.scale(*self._img_scale_factor)
        # context.set_source_surface(self._img_surface, *self._img_offset)
        # context.paint()
        return False

    def on_draw(self, area, context):
        if self._img_surface is not None:
            context.scale(*self._img_scale_factor)
            context.set_source_surface(self._img_surface, *self._img_offset)
            context.paint()
        else:
            print('Invalid surface')

        return False

class ProcessingResultLoader(GdkPixbuf.PixbufLoader):
    pass

# ~ class MultiChannelPixbuf(GdkPixbuf.Pixbuf):
    # ~ def __init__(self, *args, **kwargs):
        # ~ super().__init__(GObject.TYPE_PYOBJECT, *args, **kwargs)

    # ~ @classmethod
    # ~ def new(cls, numChannels):
        # ~ super().new(0, False, 8, 2028, numChannels*1520)

    # ~ @classmethod
    # ~ def new_from_data(cls, image_data):
        # ~ height, width = image_data.shape[1:3]
        # ~ numChannels = image_data.shape[0]
        # ~ super().new_from_data(image_data.flatten(), 0, False, 8, width, numChannels*height, 3*width, None, None)

    # ~ def get_height(self):
        # ~ return int(super().get_height() / self.numChannels)

    # ~ def get_pixbuf(self, channel):
        # ~ return self.new_subpixbuf(0, channel*1520, 2028, 1520)

class PictureViewFromMem(GObject.Object):

    def __init__(self, drawing_area_widget, image_data=None):#, default_image_path):
        GObject.Object.__init__(self)
        self._area = drawing_area_widget

        # ~ self._image_data = image_data
        self._curr_channel = 0
        self._pixbufs = []

        if image_data is not None:
            height,width = image_data.shape[1:3]
            self.numChannels = image_data.shape[0]
            # ~ self._pixbuf = GdkPixbuf.Pixbuf.new_from_data(image_data.flatten(), 0, False, 8, width, self.numChannels*height, 3*width, None, None)
            for ch in range(self.numChannels):
                self._pixbufs.append( GdkPixbuf.Pixbuf.new_from_data(image_data[ch,:,:,:].flatten(), 0, False, 8, width, height, 3*width, None, None) )
            # ~ self.pixbuf = MultiChannelPixbuf.new_from_data(image_data)
        else:
            # TODO: remove hard-coding here
            self.numChannels = NUM_CHANNELS
            # ~ self.pixbuf = MultiChannelPixbuf.new(NUM_CHANNELS)
            # ~ self.pixbuf = None
            for ch in range(self.numChannels):
                self._pixbufs.append(  GdkPixbuf.Pixbuf.new(0, False, 8, 2028, 1520) )
            # ~ self._pixbuf = GdkPixbuf.Pixbuf.new(0, False, 8, 2028, self.numChannels*1520)

        self._img_surface = None
        self._img_offset = (0.0, 0.0)
        self._img_scale_factor = (1.0, 1.0)

    @GObject.Property
    def images(self):
        return self._image_data

    @images.setter
    def images(self, image_data):
        height,width = image_data.shape[1:3]
        self.numChannels = image_data.shape[0]
        # ~ self._image_data = image_data
        for ch in range(self.numChannels):
                self._pixbufs[ch] = GdkPixbuf.Pixbuf.new_from_data(image_data[ch,:,:,:].flatten(), 0, False, 8, width, height, 3*width, None, None)
        # ~ self.pixbuf = MultiChannelPixbuf.new_from_data(image_data)
        # ~ self._pixbuf = GdkPixbuf.Pixbuf.new_from_data(image_data.flatten(), 0, False, 8, width, self.numChannels*height, 3*width, None, None)

    @GObject.Property
    def channel(self):
        return self._curr_channel

    @channel.setter
    def channel(self, newChannel):
        if newChannel in range(self.numChannels):
            if newChannel != self._curr_channel:
                self._curr_channel = newChannel
                print(f"Viewing channel {newChannel}")
                # ~ height,width = self._image_data.shape[:2]
                # ~ self._pixbuf = GdkPixbuf.Pixbuf.new_from_data(self._image_data[:,:,:,newChannel].flatten(), 0, False, 8, width, height, 3*width, None, None)
                self.init_surface(self._curr_channel)
                self._area.queue_draw()

    def channel_increment(self):
        if self.channel < self.numChannels-1:
            self.channel = self.channel + 1

    def channel_decrement(self):
        if self.channel > 0:
            self.channel = self.channel - 1

    @GObject.Property
    def area(self):
        return self._area

    # ~ @GObject.Property
    # ~ def pixbuf(self):
        # ~ return self._pixbuf

    # ~ @pixbuf.setter
    # ~ def pixbuf(self, image_data, wl):
        # ~ image_buff = image_data[wl].flatten(order='C')
        # ~ height, width = image_data.shape[:2]
        # ~ #print(f"Width = {width}, Height = {height}")
        # ~ #gbytes = GLib.Bytes(
        # ~ self._pixbuf = GdkPixbuf.Pixbuf.new_from_data(image_buff, 0, False, 8, width, height, 3*width, None, None)
        # ~ print(f"nchannels = {self._pixbuf.get_n_channels()}")
        # ~ self.init_surface()
        # ~ self._area.queue_draw()

    @GObject.Property
    def allocated_width(self):
        if self._area:
            return self._area.get_allocated_width()
        else:
            return 0

    @GObject.Property
    def allocated_height(self):
        if self._area:
            return self._area.get_allocated_height()
        else:
            return 0

    @GObject.Property
    def parent_gdk_window(self):
        return self._area.get_toplevel().get_window()

    def clear_image(self):
        self.image_path = self._default_img_path

    def get_bbox(self):
        """ Returns the x,y and width,height of the bounding box for the drawing area
            in absolute pixel coordinates """

        parent_window = self._area.get_toplevel()

        # Use the GDK window instead of the GTK window
        # since get_position will take into consideration the
        # title bar in the case of the GDK method
        gdk_window = parent_window.get_window()
        window_x, window_y = gdk_window.get_position()
        # w = self.allocated_width
        # h = self.allocated_height
        w = self._area.get_allocated_width()
        h = self._area.get_allocated_height()
        # print(f"window (x,y): ({window_x}, {window_y})  area (w,h): ({w, h})")

        rel_x, rel_y = self._area.translate_coordinates(parent_window, 0, 0)
        # print(f"rel_x, rel_y: ({rel_x}, {rel_y})")

        return window_x + rel_x, window_y + rel_y, w, h

    def get_scale_factor(self):
        width_sf =  self._area.get_allocated_width() / self._pixbufs[0].get_width()
        height_sf =  self._area.get_allocated_height() / self._pixbufs[0].get_height()

        # print(f"sf (width,height): {width_sf:0.6f},{height_sf:0.6f}")
        if width_sf < height_sf:
            sf = width_sf
            excess_height = self._area.get_allocated_height() - sf * self._pixbufs[0].get_height()
            # print(f"Excess height: {excess_height:0.1f}")
            surface_offset = (0, excess_height / 2 / sf)
        else:
            sf = height_sf
            excess_width = self._area.get_allocated_width() - sf * self._pixbufs[0].get_width()
            # print(f"Excess width: {excess_width:0.1f}")
            surface_offset = (excess_width / 2 / sf, 0)
        return (sf, sf), surface_offset

    def init_surface(self, channel=0):
        # Destroy previous buffer
        if self._img_surface is not None:
            self._img_surface.finish()
            self._img_surface = None

        # Create a new buffer
        self._img_surface = Gdk.cairo_surface_create_from_pixbuf(
            self._pixbufs[channel], 1, None
        )
        self._img_scale_factor, self._img_offset = self.get_scale_factor()
        # print(f"sf: {self._img_scale_factor}  offset: {self._img_offset}")

    def on_configure(self, area, event, data=None):
        # doesn't appear to need a "redraw", just init the surface
        self.init_surface()

        # "redraw" -- Keeping this around as an example of a context 
        # context = cairo.Context(self._img_surface)
        # print(f"sf, surface_offset: {self._img_scale_factor}, {self._img_offset}")
        # context.scale(*self._img_scale_factor)
        # context.set_source_surface(self._img_surface, *self._img_offset)
        # context.paint()
        return False

    def on_draw(self, area, context):
        if self._img_surface is not None:
            context.scale(*self._img_scale_factor)
            context.set_source_surface(self._img_surface, *self._img_offset)
            context.paint()
        else:
            print('Invalid surface')

        return False
