import time

from dataclasses import fields
from functools import partial
from typing import (
    Union,
    NamedTuple,
    Dict,
    List,
    Optional,
    Tuple,
)

from ZionEvents import (
    ZionEvent,
    ZionEventGroup
)

from ZionLED import (
    ZionLEDs,
    ZionLEDColor,
)

from ZionGPIO import LED_GPIOS

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import (
    Gtk,
    GObject,
    GLib,
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


class ZionProtocolTree():
    """
    Helper class for converting a ZionProtocol into
    a treeview with an associated treestore model
    """

    # Mapping of visible fields to display names.
    FIELDS : Dict[str, str] = {
        'name': "Name",
        'cycles': "Repeats",
        'cycle_time': "Cycle Time\n(ms)",
        'total_time_sec': "Total Time\n(sec)",
        'capture': "Capture?",
        'group': "Label",
        'leds': "$LED_NAME$ Pulse\n(ms)",  # Special field that gets formatted
    }

    # Displayed fields that shouldn't be edited
    NOT_EDITABLE_FIELDS = ('total_time_sec',)

    assert set(FIELDS.keys()) <= set([f.name.lstrip('_') for f in fields(ZionEvent)]), \
            f"'{set(FIELDS.keys())}' not a subset of '{set([f.name.lstrip('_') for f in fields(ZionEvent)])}'"

    def __init__(self, gtktreeview : Gtk.TreeView, entries : List[Union[ZionEventGroup, ZionEvent]] = []):
        # self._protocol = protocol
        self._treeview = gtktreeview
        self._dirty = False
        self._glib_mutex = GLib.Mutex()
        self._glib_mutex.init()
        self._glib_cb_id = None

        # The treestore is just a single python object, either a ZionEvent or ZionEventGroup
        # self._treestore = Gtk.TreeStore(GObject.TYPE_PYOBJECT)
        self._treestore = ZionTreeStore()

        self._treestore_handlers = [
            ("row-inserted", self.on_tree_row_inserted),
            ("row-deleted", self.on_tree_row_deleted),
            ("row-changed", self.on_tree_row_changed),
            ("row-has-child-toggled", self.on_tree_row_has_child_toggled),
        ]

        self._treestore_handlers_ids = None

        self.init_treestore(entries)

        self._treeview.set_model(self._treestore)

        _field_to_type = {f.name.lstrip('_'): f.type for f in fields(ZionEvent)}
        _type_to_func = {str: self.get_event_entry_str, int: self.get_event_entry_str, float: self.get_event_entry_str, bool: self.get_event_entry_bool}
        _type_to_edit_func = {str: self._text_edited, int: self._int_edited, bool: self._toggle_edited}
        _type_to_edit_signal = {str: "edited", int: "edited", bool: "toggled"}

        for field, column_title in self.FIELDS.items():
            print(f"field={field}, title={column_title}")
            ftype = _field_to_type[field]
            if ftype in (str, int, float, bool):
                cell_data_func = _type_to_func[ftype]

                if ftype is bool:
                    renderer = Gtk.CellRendererToggle()
                else:
                    renderer = Gtk.CellRendererText()
                    # If you want to center align text
                    # renderer.set_property("xalign", 0.5)

                column = Gtk.TreeViewColumn(column_title, renderer)

                column.set_cell_data_func(renderer, cell_data_func, field)
                self._treeview.append_column(column)
                if field not in self.NOT_EDITABLE_FIELDS:
                    if ftype is not bool:
                        renderer.set_property("editable", True)
                    renderer.connect(_type_to_edit_signal[ftype], partial(_type_to_edit_func[ftype], field))

            elif ftype is ZionLEDs:
                for led_color in ZionLEDColor:  # Actually a dict of led name to title of strings
                    if LED_GPIOS[led_color]:
                        renderer = Gtk.CellRendererText()
                        column = Gtk.TreeViewColumn(column_title.replace("$LED_NAME$", led_color.name), renderer)
                        column.set_cell_data_func(renderer, self.get_event_entry_led, led_color)
                        self._treeview.append_column(column)
                        renderer.set_property("editable", True)
                        renderer.connect("edited", partial(self._led_cell_edited, field, led_color))

            elif ftype is list: #TODO: make this capturelist? only dealing with capture lists right now
                renderer = Gtk.CellRendererText()
                column = Gtk.TreeViewColumn(column_title, renderer)
                column.set_cell_data_func(renderer, self.get_event_entry_captures, field)
                self._treeview.append_column(column)
                renderer.set_property("editable", True)
                renderer.connect("edited", partial(self._captures_edited, field))

            else:
                raise RuntimeError(f"Unrecognized field type for field {field}: {ftype}")

            # # Not sure what the text argument is used for....
            # # FOUND IT: Also, with Gtk.TreeViewColumn,
            # # you can bind a property to a value in a Gtk.TreeModel.
            # # For example, you can bind the “text” property on the cell renderer
            # # to a string value in the model,
            # # thus rendering a different string in each row of the Gtk.TreeView

            # renderer.connect("edited", partial(self.text_edited, i))
        self._selection = self._treeview.get_selection()
        # self._selection.connect("changed", self.on_tree_selection_changed)

        # # This signal doesn't fire when reordering the rows through the GUI
        # self._treestore.connect("rows-reordered", self.on_tree_rows_reordered)

        # Instead, it appears as a row-insert, followed by a delete
        self._enable_treestore_handlers()
        # self._treestore.connect("row-inserted", self.on_tree_row_inserted)
        # self._treestore.connect("row-deleted", self.on_tree_row_deleted)
        # self._treestore.connect("row-changed", self.on_tree_row_changed)
        # self._treestore.connect("row-has-child-toggled", self.on_tree_row_has_child_toggled)
        # self._treeview.connect("drag-motion", self.on_treeview_drag_motion)
        # self._treeview.connect("drag-data-received", self.on_treeview_drag_data_received)

    def init_treestore(self, entries : List[Union[ZionEventGroup, ZionEvent]] = []) -> Gtk.TreeStore:
        self._treestore.clear()
        self._init_treestore(None, entries)
        self._dirty = False
        return self._treestore

    def reload_treestore(self, entries : List[Union[ZionEventGroup, ZionEvent]] = []) -> Gtk.TreeStore:
        self._disable_treestore_handlers()
        self._treestore.clear()
        self._init_treestore(None, entries)
        self._dirty = False
        self._enable_treestore_handlers()
        return self._treestore

    def _init_treestore(
        self,
        row_iter : Optional[Gtk.TreeIter],
        entries : List[Union[ZionEventGroup, ZionEvent]],
    ):
        for entry in entries:
            new_row_iter = self._treestore.append(row_iter, [entry,])
            if isinstance(entry, ZionEventGroup):
                # Recurse into the entries
                self._init_treestore(new_row_iter, entry.entries)

    def _enable_treestore_handlers(self):
        if self._treestore_handlers_ids is not None:
            print("WARNING: The treestore handlers are already enabled!")
            return

        handler_ids = []
        for signal_name, handler_func in self._treestore_handlers:
            handler_ids.append(self._treestore.connect(signal_name, handler_func))

        # Save the IDs for when we need to disable the handlers
        self._treestore_handlers_ids = tuple(handler_ids)

    def _disable_treestore_handlers(self):
        if self._treestore_handlers_ids is  None:
            print("WARNING: The treestore handlers are already disabled!")
            return

        for handler_id in self._treestore_handlers_ids:
            self._treestore.disconnect(handler_id)

        self._treestore_handlers_ids = None

    def _set_cell_value_visibility(self, cell, property, value):
        # Only update a field if it's present, otherwise don't show it
        visible = (value is not None)

        if visible:
            if property == 'text':
                value = str(value)
            cell.set_property(property, value)

        cell.set_property('visible', visible)

    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def dirty(self) -> bool:
        return self._dirty

    @dirty.setter
    def dirty(self, value : bool):
        if bool(value):
            GLib.idle_add(self._refresh_tree)

        self._dirty = bool(value)

    def _refresh_tree(self):
        """
        Helper function to set a callback timeout.
        Add functionality to have the timeout reset if called repeatedly.
        """
        if not self._glib_mutex.trylock():
            print("_refresh_tree -- can't lock mutex... trying again...")
            return True

        if self._glib_cb_id is not None:
            GLib.Source.remove(self._glib_cb_id)

        self._glib_cb_id = GLib.timeout_add(100, self._refresh_tree_cb)
        self._glib_mutex.unlock()

        return False

    def _refresh_tree_cb(self):
        """ Refresh the ZionProtocolEntry objects in the tree """
        self._glib_mutex.lock()
        print(f"_refresh_tree_cb has the lock!")

        for row in self._treestore:
            if row[0] is not None and not row[0].is_event:
                del row[0].entries[:]
                # This will update the entries recursively
                self._row_to_entry(row)
                row[0].refresh_minimum_cycle_time()
                # self._treestore.row_changed(row.path, row.iter)

        print(f"_refresh_tree_cb unlocking....")
        self._glib_cb_id = None
        self._treeview.queue_draw()
        self._glib_mutex.unlock()
        return False

    def _refresh_cycle_times(self, child_row : Gtk.TreeModelRow):
        parent_row = child_row.get_parent()
        while parent_row is not None:
            parent_row[0].refresh_minimum_cycle_time()
            parent_row = parent_row.get_parent()

    def _text_edited(self, field, widget, path, value):
        print(f"_text_edited -- field: {field}  widget: {widget}  path: {path}  value: {value}")
        setattr(self._treestore[path][0], field, value)

    def _int_edited(self, field, widget, path, value):
        print(f"_int_edited -- field: {field}  widget: {widget}  path: {path}  value: {value}")
        setattr(self._treestore[path][0], field, int(value))
        if field in ("cycles", "cycle_time"):
            self._refresh_cycle_times(self._treestore[path])

    def _toggle_edited(self, field, widget, path):
        print(f"_toggle_edited -- field: {field}  widget: {widget}  path: {path}")
        setattr(self._treestore[path][0], field, not getattr(self._treestore[path][0], field))

    def _led_cell_edited(self, field, led_color, widget, path, value):
        print(f"field: {field}  led_color: {led_color}  widget: {widget}  path: {path}  value: {value}")
        getattr(self._treestore[path][0], field)[led_color] = int(value)

    def _captures_edited(self, field, widget, path, value):
        # Value should be comma-separated integers. Assumed to not include brackets. Parse:
        caps_str = value.split(',')
        if len(caps_str)==1:
            try:
                captures = [int(caps_str[0].strip())]
            except ValueError:
                captures = []
        else:
            captures = []
            for cap in caps_str:
                try:
                    captures.append(int(cap.strip()))
                except ValueError:
                    print("Capture values must be integers!")
                    return
        print(f"field: {field}  widget: {widget}  path: {path}  value: {captures}")
        setattr(self._treestore[path][0], field, captures)

    def get_event_entry_str(self, treeviewcolumn, cell, model, iter_, event_field):
        event = model[iter_][0]
        cell_value = getattr(event, event_field, None)

        self._set_cell_value_visibility(cell, 'text', cell_value)

    def get_event_entry_bool(self, treeviewcolumn, cell, model, iter_, event_field):
        event = model[iter_][0]
        cell_value = getattr(event, event_field, None)

        self._set_cell_value_visibility(cell, 'active', cell_value)

    def get_event_entry_led(self, treeviewcolumn, cell, model, iter_, led_key):
        event = model[iter_][0]
        cell_value = getattr(event, 'leds', {}).get(led_key, None)

        self._set_cell_value_visibility(cell, 'text', cell_value)

    def get_event_entry_captures(self, treeviewcolumn, cell, model, iter_, event_field):
        event = model[iter_][0]
        cell_value = getattr(event, event_field, None)
        self._set_cell_value_visibility(cell, 'text', cell_value)

    def on_tree_row_inserted(self, model, path, iter_):
        """ A new event as been inserted into the treestore. Check if we need to remove any placeholder row. """

        # We'll get a None entry when adding a new group and we add a None placeholder child
        # OR we've moved a row by drag-and-drop (which first adds an empty row before changing it)
        entry = model[iter_][0]
        if entry is None:
            print(f"on_tree_row_inserted (entry is None) -- iter_: {iter_} path: {path}")
            return

        # Need the parent object
        parent_iter = model.iter_parent(iter_)

        # Check if we need to remove the empty row in a new group. Doesn't apply if parent is the root
        if parent_iter is not None:
            print(f"on_tree_row_inserted -- iter_: {iter_}  entry.name: {entry.name}  path: {path}  parent: {getattr(model[parent_iter][0], 'name', 'None')}")
            for child_row in model[parent_iter].iterchildren():
                if child_row[0] is None:
                    # We found the empty row
                    self._treestore.remove(child_row.iter)
                    break
        else:
            print(f"on_tree_row_inserted -- iter_: {iter_}  entry.name: {entry.name}  path: {path}  parent: 'None'")

        # Mark the tree as dirty which will force a refresh
        self.dirty = True

        # Update parent cycle times
        # self._refresh_cycle_times(model[iter_])

    def on_tree_row_deleted(self, model, path):
        print(f"\non_tree_row_deleted --  path: {path}")
        # Mark the tree as dirty
        self.dirty = True

        # Update parent cycle times
        # self._refresh_cycle_times(model[path])

    def on_tree_row_changed(self, model, path, iter_):
        # Treat this just like a insertion since we'll delete the original event in on_tree_row_deleted

        # Need the parent object
        parent_iter = model.iter_parent(iter_)

        print(f"\non_tree_row_changed --  path: {path}  entry.name: {getattr(model[iter_][0], 'name', None)}")

        # Check if we need to remove the empty row in a new group. Doesn't apply if parent is the root
        if parent_iter is not None:
            for child_row in model[parent_iter].iterchildren():
                if child_row[0] is None:
                    # We found the empty row
                    self._treestore.remove(child_row.iter)
                    break

        # Mark the tree as dirty
        self.dirty = True

        # # Update parent cycle times
        # self._refresh_cycle_times(model[path])

    def on_tree_row_has_child_toggled(self, model, path, iter_):
        entry_row = model[iter_]
        entry = entry_row[0]
        num_children = model.iter_n_children(entry_row.iter)
        print(f"\non_tree_row_has_child_toggled --  path: {path}  entry: {entry.name}  num_children: {num_children}")
        if not entry.is_event and num_children == 0:
            # We're removed the last event from this group. Add a placeholder event
            model.append(entry_row.iter, [None,])

    def get_current_selection(self) -> ZionTreeSelection:
        entry = None
        parent = None
        parent_iter = None
        num_children = 0
        num_siblings = 0

        model, entry_iter = self._selection.get_selected()
        if entry_iter is not None:
            entry_row = model[entry_iter]
            entry = entry_row[0]
            num_children = len(list(entry_row.iterchildren()))
            num_siblings = model.iter_n_children(getattr(entry_row.parent, 'iter', None)) - 1
            if entry_row.parent is not None:
                parent = entry_row.parent[0]

        return ZionTreeSelection(
            entry=entry,
            entry_iter=entry_iter,
            parent=parent,
            parent_iter=parent_iter,
            num_children=num_children,
            num_siblings=num_siblings
        )

    def tree_delete_selection(self, selection : ZionTreeSelection):
        """ Delete the selected event from the tree, mark it as dirty """
        print(f"Deleting {selection.entry.name}...")
        self._treestore.remove(selection.entry_iter)

    def get_entries(self) -> List[Union[ZionEventGroup, ZionEvent]]:
        """
        Convert the treestore to a list of ZionEventGroups and ZionEvents.
        The objects themselves are already created, just need to fill in the 'entries' field.
        """
        entries = []
        for row in self._treestore:
            if row[0] is not None:
                entries.append(self._row_to_entry(row))
        return entries

    def _row_to_entry(self, row : Gtk.TreeModelRow) -> Optional[Union[ZionEventGroup, ZionEvent]]:
        """
        Recursive call to fill in entries.
        Don't add empty rows that are used as placeholders in ZionEventGroups
        """
        if row[0] is None:
            # Empty row... probably a place holder
            return

        if not row[0].is_event:
            # We're a Group. Clear out the old entries
            row[0].entries = []
            for child_row in row.iterchildren():
                child = self._row_to_entry(child_row)
                if child is not None:
                    row[0].entries.append(child)
            row[0].refresh_minimum_cycle_time()

        return row[0]

    def tree_add_entry(self, is_event : bool):
        """
        Adds an event depending on the currently selected row. There are 3 possibilites:

        (1) Nothing is selected: Append the new event to the root of the tree
        (2) An Event Group is selected: Append the new event to it's children
        (3) An Event is selected: Add the new event after the currently selected event
        """

        selection = self.get_current_selection()
        entry_parent = None
        entry_parent_iter = None
        entry_sibling_iter = None

        # Scenario (2) or (3)
        if selection.entry is not None:
            print(f"You selected: '{selection.entry.name}'")
            if not selection.entry.is_event:
                # Scenario (2). Add the new event to this group
                entry_parent = selection.entry
                entry_parent_iter = selection.entry_iter
            else:
                # Scenario (3)
                entry_parent = selection.parent
                entry_parent_iter = selection.parent_iter
                entry_sibling_iter = selection.entry_iter

        if is_event:
            if entry_parent is None:
                #  If entry_sibling is also None, then this is scenario (1)
                event_name = "New Event"
            else:
                print(f"   parent: '{entry_parent.name}'")
                event_name = f"New {entry_parent.name} event"

            # We'll leverage the 'on_tree_row_inserted' callback to insert the event into our Protocol object
            new_entry = ZionEvent(name=event_name)
        else:
            new_entry = ZionEventGroup(name="New Group")

        if entry_sibling_iter is not None:
            new_iter = self._treestore.insert_after(entry_parent_iter, entry_sibling_iter, [new_entry,])
        else:
            new_iter = self._treestore.append(entry_parent_iter, [new_entry,])

        # Need this so we get the expander icon to make it clear it's a group
        if not is_event:
            self._treestore.append(new_iter, [None,])

        # Mark the tree as dirty
        self._dirty = True

    # The following methods are unused but will be useful when I get around to fixing drag & drop
    @staticmethod
    def get_treeview_dest_row_at_pos(treeview : Gtk.TreeView, drag_x : int, drag_y : int) -> Optional[Tuple[Optional[Gtk.TreePath], Gtk.TreeViewDropPosition]]:
        cell_y = 0 # gint
        offset_into_row = 0.0 # gdouble
        fourth = 0.0 # gdouble
        cell = None

        if drag_x < 0 or drag_y < 0:
            return None

        if treeview.get_bin_window() is None:
            return None

        if treeview.get_model() is None:
            return None

        # Note: this function is can't touch TreeViewDragInfo

        # If in the top fourth of a row, we drop before that row; if
        # in the bottom fourth, drop after that row; if in the middle,
        # and the row has children, drop into the row.
        bin_x, bin_y = treeview.convert_widget_to_bin_window_coords(drag_x, drag_y)
        ret = treeview.get_path_at_pos(bin_x, bin_y)
        if ret is None:
            vis_range = treeview.get_visible_range()
            if vis_range is None:
                print("Could not get a visible range!")
                print(f"Could not get destination row @ position ({bin_x}, {bin_y}) (drag_coord: {drag_x}, {drag_y})")
                return None

            print(f"treeview.get_visible_range(): {vis_range[0]} -> {vis_range[1]}")
            vis_min = treeview.get_background_area(vis_range[0], None).y
            vis_max_rect = treeview.get_background_area(vis_range[1], None)
            vis_max = vis_max_rect.y + vis_max_rect.height

            print(f"visible_rect.y.min: {vis_min}  visible_rect.y.max: {vis_max}")
            if bin_y <= vis_min:
                path = vis_range[0]
                pos = Gtk.TreeViewDropPosition.BEFORE
            else:
                last_visible_root = vis_range[1].get_indices()[0]
                path = Gtk.TreePath.new_from_indices([last_visible_root,])
                pos = Gtk.TreeViewDropPosition.AFTER
        else:
            path, column, _, cell_y = ret
            row = treeview.get_model()[path]
            is_expanded = treeview.row_expanded(path)
            is_group = not row[0].is_event
            print(f"row '{row[0].name}'  path: {path}  is_group: {is_group}  is_expanded: {is_expanded}")
            # print(f"treeview.get_path_at_pos({bin_x}, {bin_y}): {path}")

            cell = treeview.get_background_area(path, column)
            offset_into_row = cell_y

            fourth = cell.height / 4.0

            if offset_into_row < fourth:
                pos = Gtk.TreeViewDropPosition.BEFORE
            elif offset_into_row < (cell.height / 2.0):
                pos = Gtk.TreeViewDropPosition.INTO_OR_BEFORE
            elif offset_into_row < cell.height - fourth or is_expanded:
                pos = Gtk.TreeViewDropPosition.INTO_OR_AFTER
            else:
                pos = Gtk.TreeViewDropPosition.AFTER

        return (path, pos)

    def on_treeview_drag_data_received(self, treeview, drag_context, x, y, selection_data, info, time):
        """
        To get the drag and drop to work properly. I'll probably have to re-implement
        do_drag_data_received(...). It ultimately sets the path that gets used by
        TreeStore in the do_drag_data_received (dest, selection_data) and
        do_row_drop_possible (dest_path, selection_data) calls.
        """

        selected_action = drag_context.get_selected_action()
        suggested_action = drag_context.get_suggested_action()
        print(f"\non_treeview_drag_data_received -- x: {x}  y: {y}  info: {info}  selected_action: {selected_action.first_value_name}  suggested_action: {suggested_action.first_value_name}")
        treeview.do_drag_data_received(treeview, drag_context, x, y, selection_data, info, time)
        selected_action = drag_context.get_selected_action()
        suggested_action = drag_context.get_suggested_action()
        print(f"on_treeview_drag_data_received -- x: {x}  y: {y}  info: {info}  selected_action: {selected_action.first_value_name}  suggested_action: {suggested_action.first_value_name}")
