import os
from enum import Enum

from gi.repository import Gtk, GdkPixbuf, Gdk

class PictureView(Gtk.DrawingArea):
    __gtype_name__ = 'PictureView'

    def __init__(self, *args, **kwargs):
        super(Gtk.DrawingArea, self).__init__(*args, **kwargs)
        # self._path = None
        mod_path = os.path.dirname(os.path.abspath(__file__))
        self.pixbuf = GdkPixbuf.Pixbuf.new_from_file(os.path.join(mod_path, "Detect_Logo.png"))
        # self.pixbuf =  GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, width, height)
        self.img_surface = Gdk.cairo_surface_create_from_pixbuf(
            self.pixbuf, 1, None
        )

    def get_useful_height(self):
        aw = self.get_allocated_width()
        pw = self.pixbuf.get_width()
        ph = self.pixbuf.get_height()
        return aw/pw * ph

    def get_useful_width(self):
        ah = self.get_allocated_height()
        pw = self.pixbuf.get_width()
        ph = self.pixbuf.get_height()
        return ah/ph * pw

    def get_scale_factor(self):
        width_sf =  self.get_allocated_width() / self.pixbuf.get_width()
        height_sf =  self.get_allocated_height() / self.pixbuf.get_height()
        
        print(f"sf (width,height): {width_sf:0.6f},{height_sf:0.6f}")
        if width_sf < height_sf:
            sf = width_sf
            excess_height = self.get_allocated_height() - sf * self.pixbuf.get_height()
            print(f"Excess height: {excess_height:0.1f}")
            surface_offset = (0, excess_height / 2 / sf)            
            # surface_offset = (0, ( self.get_allocated_height() - sf * self.pixbuf.get_height() ) / 2)
            # surface_offset = (0, 20)
        else:
            sf = height_sf
            excess_width = self.get_allocated_width() - sf * self.pixbuf.get_width()
            print(f"Excess width: {excess_width:0.1f}")
            surface_offset = (excess_width / 2 / sf, 0)            
            # surface_offset = (20, 0)
        return sf, surface_offset

    def do_draw(self, context):
        print(f"context: {context}")
        print(f"context.get_source(): {context.get_source()}")
        print(f"alloc_w,h: {self.get_allocated_width()}, {self.get_allocated_height()}")
        print(f"pxbuf_w,h: {self.pixbuf.get_width()}, {self.pixbuf.get_height()}")
        sf, surface_offset = self.get_scale_factor()
        print(f"sf, surface_offset: {sf:0.6f}, {surface_offset}")
        # if context.get_source()
        context.scale(sf, sf)
        context.set_source_surface(self.img_surface, *surface_offset)
        # context.set_source_surface(self.img_surface, 0,0)
        context.paint()
        print(f"context.get_source(): {context.get_source()}")

        # # height = self.get_useful_height()
        # if driving_dim == ResizeDrivingDimEnum.HEIGHT:
        #     height = self.get_useful_height()
        #     self.set_size_request(-1, height)
        # else:
        #     width = self.get_useful_width()
        #     self.set_size_request(width, -1)

        print(f"alloc_w,h: {self.get_allocated_width()}, {self.get_allocated_height()}")

