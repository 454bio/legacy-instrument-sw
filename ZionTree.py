from typing import (
    Union,
    NamedTuple
)

from ZionEvents import (
    ZionEvent,
    ZionEventGroup
)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import (
    Gtk,
    GObject,
)


class ZionTreeSelection(NamedTuple):
    entry:          Union[ZionEvent, ZionEventGroup, None]
    entry_iter:     Union[Gtk.TreeIter, None]
    parent:         Union[ZionEventGroup, None]
    parent_iter:    Union[Gtk.TreeIter, None]
    num_siblings:   int
    num_children:   int


class ZionTreeStore(Gtk.TreeStore):

    def __init__(self, *args, **kwargs):
        super().__init__(GObject.TYPE_PYOBJECT, *args, **kwargs)

    def do_row_draggable(self, path: Gtk.TreePath) -> bool:
        """ Don't allow empty rows to be dragged """
        return self[path][0] is not None

    # def do_drag_data_received(self, *args):
    #     print(f"do_drag_data_received -- args: {args}")

    def do_row_drop_possible(self, dest_path: Gtk.TreePath, selection_data: Gtk.SelectionData):
        # print(f"row_drop_possible -- dest_path: {dest_path}")

        try:
            # If dest_path doesn't exist, then this throw ValueError
            dest_iter = self.get_iter(dest_path)

            # Get the source data
            (success, source_model, source_path) = Gtk.tree_get_row_drag_data(selection_data)
            if not success:
                print(f"row_drop_possible -- selection_data.get_data_type(): {selection_data.get_data_type()}")
                return False

            # The python overloading allows this
            source_row = source_model[source_path]

            # Don't move an empty row
            if source_row[0] is None:
                return False

            # Check to make sure we're not trying to recursively move us
            if self.is_ancestor(source_row.iter, dest_iter):
                return False

        except ValueError:
            # Destination path doesn't exist (i.e. we're trying to make a group)
            return False
        else:
            return True

