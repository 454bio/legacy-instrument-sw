import time
from dataclasses import dataclass, field, asdict, is_dataclass, fields
import json
from types import SimpleNamespace
import traceback
from typing import List, Optional, Union, Dict, NamedTuple, Tuple
from fractions import Fraction

from ZionLED import (
    ZionLEDColor,
    ZionLEDs,
)

from ZionErrors import (
    ZionProtocolVersionError,
    ZionProtocolFileError,
)

from ZionCamera import ZionCameraParameters

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject


@dataclass
class ZionProtocolEntry:
    is_event: bool
    name: str = ""
    cycles: int = 1
    parent: Optional['ZionEventGroup'] = None
    # tree_iter: Optional[Gtk.TreeIter] = None

@dataclass
class ZionEvent(ZionProtocolEntry):
    is_event: bool = True
    capture: bool = True
    group: str = ""
    postdelay: int = 0
    leds: ZionLEDs = field(default_factory=ZionLEDs)

    def __post_init__(self):
        if isinstance(self.leds, dict):
            self.leds = ZionLEDs(**self.leds)

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEvent":
        # Convert "leds" from a dictionary to ZionLEDs
        json_dict.update({"leds": ZionLEDs(**json_dict.get("leds", {}))})
        return cls(**json_dict)


@dataclass
class ZionEventGroup(ZionProtocolEntry):
    is_event: bool = False
    entries: List[Union[ZionEvent, "ZionEventGroup"]] = field(default_factory=list)

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEventGroup":
        # Remove "event" from the dictionary
        entries_list = json_dict.pop("entries", [])
        entries : Union[List[ZionEvent], List["ZionEventGroup"], List] = []
        for event_or_group in entries_list:
            # This is not a robust way to go from json <-> python...
            # But for now it allows people to edit the JSON directly without crazy class names
            if "entries" in event_or_group:
                # Hurray recursion!
                entries.append(cls.from_json(event_or_group))
            else:
                entries.append(ZionEvent.from_json(event_or_group))

        return cls(**json_dict, entries=entries)

    def flatten(self) -> List[ZionEvent]:
        """
        Convert a ZionEventGroup to an equivalent list of ZionEvents
        """

        flat_events = []
        for _ in range(self.cycles):
            for event in self.entries:
                if isinstance(event, ZionEvent):
                    flat_events.append(event)
                elif isinstance(event, ZionEventGroup):
                    flat_events.extend(event.flatten())
                else:
                    raise RuntimeError(
                        f"Unrecognized type in the event list: {type(event)}"
                    )

        return flat_events


class ZionProtocolEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, ZionProtocol):
            return obj.__dict__
        if isinstance(obj, ZionLEDColor):
            return obj.name
        if isinstance(obj, Fraction):
            return float(obj)
        if isinstance(obj, ZionLEDs):
            return {k.name: v for k,v in obj.data.items()}
        return json.JSONEncoder.default(self, obj)


class TreeSelection(NamedTuple):
    entry:          Union[ZionEvent, ZionEventGroup, None]
    entry_iter:     Union[Gtk.TreeIter, None]
    parent:         Union[ZionEventGroup, None]
    parent_iter:    Union[Gtk.TreeIter, None]
    num_siblings:   int
    num_children:   int


# TODO: Have ZionProtocol generate the TreeStroe
#       When it's time to run a protocol. Convert the TreeStore
#       back into an list of eventgroups/events
class ZionProtocol:

    def __init__(self, filename: str = None):
        self.Version: int = 2
        self.Parameters: ZionCameraParameters = ZionCameraParameters()
        self.Entries: List[Union[ZionEvent, ZionEventGroup]] = [ZionEvent()]
        self._protocoltree = None

        if filename:
            self.load_from_file(filename, flatten=False)

    # def __str__(self):
    #     print("str called...")
    #     out = ""
    #     try:
    #         rprint(self)
    #         # out = json.dumps(self, indent=1, cls=ZionProtocolEncoder)
    #     except Exception as e:
    #         tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
    #         print(f"ERROR:\n{tb}")
    #     finally:
    #         print("done")
    #     return out

    def clear(self):
        self.Entries = []
        if self._protocoltree:
            self._protocoltree.clear()

    def _load_v1(self, json_ns: dict):
        print(f"ERROR: Loading a Version 1 protocol not supported!")

    def _load_v2(self, json_ns: dict):
        print(f"Loading a Version 2 protocol...")

        # TODO: Use a serialization library that's still human editable
        self.Entries = []
        # Ensure each element of Entries looks like an EventGroup
        for eg in json_ns.Entries:
            if "entries" not in eg:
                raise ZionProtocolFileError(
                    "Each top-level element in 'Entries' must be an EventGroup!"
                )

            self.Entries.append(ZionEventGroup.from_json(eg))

        parameters_dict = getattr(json_ns, 'Parameters', {})
        self.Parameters = ZionCameraParameters(**parameters_dict)

    def load_from_file(self, filename: str, flatten: bool = True):
        try:
            with open(filename) as f:
                json_ns = SimpleNamespace(**json.load(f))

            # Previous version of the protocol won't have a verison number
            file_version = getattr(json_ns, "Version", 1)

            # Convert the old protocol version to the new one
            if file_version == 1:
                self._load_v1(json_ns)
            elif file_version == 2:
                self._load_v2(json_ns)
            else:
                raise ZionProtocolVersionError(
                    f"Version {file_version} is not supported... "
                    "Check if there's an newer version of the GUI available"
                )

            print(self.Entries)
        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            print(f"ERROR Loading Protocol File: {filename}\n{tb}")

    def save_to_file(self, filename: str):
        if not filename.endswith(".txt"):
            filename += ".txt"

        with open(filename, "w") as f:
            json.dump(self, f, indent=1, cls=ZionProtocolEncoder)

    def gtk_initialize_treeview(self, treeview : Gtk.TreeView):
        self._protocoltree = ZionProtocolTree(treeview, self)

    def get_entries(self):
        return self.Entries

    # I wonder if I can put a hook into the treemodel that will get called
    # anytime it's updated. So I can keep Entries up-to-date in real time...

    def performEvent(self, event: ZionEvent, gpio_ctrl: "ZionGPIO"):
        gpio_ctrl.enable_vsync_callback(event)
        if event.postdelay > 0:
            time.sleep(event.postdelay / 1000.0)

    def add_event_group(
        self,
        event_group : ZionEventGroup = None,
        parent : Optional[ZionEventGroup] = None,
        name : Optional[str] = None,
        cycles : Optional[int] = None,
    ) -> ZionEventGroup:
        """
        Add a new event group to the protocol.
        event_group:    If None, then create a new event group.
        parent:         Parent for the event group. If None then the event group is added to the root Entries.
        name:           Name of new event group. Ignored if event_group is not None.
        cycles:         Number of cycles for the event group. Ignored if event_group is not None.
        """

        if event_group is None:
            event_group = ZionEventGroup()
            if parent is not None: event_group.parent = parent
            if name is not None : event_group.name = name
            if cycles is not None : event_group.cycles = cycles

        if parent:
            parent.entries.append(event_group)
        else:
            self.Entries.append(event_group)

        return event_group

    def add_event(
        self,
        event : Optional[ZionEvent] = None,
        parent: Optional[ZionEventGroup] = None,
        index: Optional[int] = None,
        **kwargs
    ) -> ZionEvent:
        """
        Add a new event to the protocol.
        event:      If None, then create a new event.
        parent:     Parent the event. If None then the event is added to the root Entries.
        index:      The index to insert the event at

        The `event` is None then the following optional keyword arguments are available initalize the new event.

        name : str      : Descriptive name for the event (default: "")
        cycles : int    : Number of cycles for the event (default: 1)
        capture : bool  : Wheter to capture an image for the event (default: True)
        group : str     : Group string that's added to the image filename (default: "")
        postdelay : int : Number of milliseconds to wait after the event completers (default: 0)
        leds : ZionLEDs : Led settings for the new event (default: ZionLEDs())
        """

        # Create the event if it doesn't exist
        if event is None:
            if parent is not None:
                kwargs["parent"] = parent
            event = ZionEvent(**kwargs)

        # Grab the list we'll be inserting into
        if parent is None:
            entries = self.Entries
        else:
            # If an event is passed in that already has a parent define AND we passed in parent as a kwarg, then they should be the same
            assert event.parent is None or event.parent is parent
            if event.parent is None:
                # If we haven't defined the parent for a passed in event
                event.parent = parent

            entries = parent.entries

        # Equivalent to entries.append(..) if index is None
        if index is None:
            index = len(entries)

        # Add the event
        entries.insert(index, event)

        return event

    def gtk_new_event(self):
        self._protocoltree.tree_add_entry(is_event=True)

    def gtk_new_group(self):
        self._protocoltree.tree_add_entry(is_event=False)

    def gtk_delete_selection(self, selection: TreeSelection) -> bool:
        return self._protocoltree.tree_delete_selection(selection)

    def gtk_get_current_selection(self) -> TreeSelection:
        return self._protocoltree.get_current_selection()


class ZionTreeStore(Gtk.TreeStore):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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
    Helper class for converting the above class into
    treeview with an associated treestore model
    """

    # Mapping of visible fields to display names.
    FIELDS : Dict[str, str] = {
        'name': "Name",
        'cycles': "Cycles",
        'capture': "Capture?",
        'group': "Group",
        'postdelay': "Post Delay\n(ms)",
        'leds': "$LED_NAME$ Pulse\n(ms)",  # Special field that gets formatted
    }

    def __init__(self, gtktreeview : Gtk.TreeView, protocol : ZionProtocol):
        self._protocol = protocol
        self._treeview = gtktreeview

        # The treestore is just a single python object, either a ZionEvent or ZionEventGroup
        self._treestore = Gtk.TreeStore(GObject.TYPE_PYOBJECT)

        self.init_treestore()

        self._treeview.set_model(self._treestore)

        _field_to_type = {f.name: f.type for f in fields(ZionEvent)}
        _type_to_func = {str: self.get_event_entry_str, int: self.get_event_entry_str, bool: self.get_event_entry_bool}

        for field, column_title in self.FIELDS.items():
            ftype = _field_to_type[field]
            if ftype in (str, int, bool):
                cell_data_func = _type_to_func[ftype]

                if ftype is bool:
                    renderer = Gtk.CellRendererToggle()
                else:
                    renderer = Gtk.CellRendererText()
                    # Center Align text (not the name though)
                    renderer.set_property("xalign", 0.5)

                column = Gtk.TreeViewColumn(column_title, renderer)

                column.set_cell_data_func(renderer, cell_data_func, field)
                self._treeview.append_column(column)
                # renderer.set_property("editable", True)

            elif ftype is ZionLEDs:
                for led_color in ZionLEDColor:  # Actually a dict of led name to title of strings
                    renderer = Gtk.CellRendererText()
                    column = Gtk.TreeViewColumn(column_title.replace("$LED_NAME$", led_color.name), renderer)
                    column.set_cell_data_func(renderer, self.get_event_entry_led, led_color)
                    self._treeview.append_column(column)
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
        self._treestore.connect("row-inserted", self.on_tree_row_inserted)
        self._treestore.connect("row-deleted", self.on_tree_row_deleted)
        self._treestore.connect("row-changed", self.on_tree_row_changed)
        self._treestore.connect("row-has-child-toggled", self.on_tree_row_has_child_toggled)
        # self._treeview.connect("drag-motion", self.on_treeview_drag_motion)
        # self._treeview.connect("drag-data-received", self.on_treeview_drag_data_received)


    def init_treestore(self) -> Gtk.TreeStore:
        self._treestore.clear()
        self._init_treestore(None, self._protocol.get_entries())
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

    def _set_cell_value_visibility(self, cell, property, value):
        # Only update a field if it's present, otherwise don't show it
        visible = (value is not None)

        if visible:
            if property == 'text':
                value = str(value)
            cell.set_property(property, value)

        cell.set_property('visible', visible)

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

    def on_tree_row_inserted(self, model, path, iter_):
        """ Update the internal representation of the protocol """

        # Need the parent object
        parent_iter = model.iter_parent(iter_)
        parent_row = None
        parent = None
        if parent_iter is not None:
            parent_row = model[parent_iter]
            parent = parent_row[0]

        # We'll get a None entry when adding a new group and we add a None placeholder child
        # OR we've moved a row by drag-and-drop (which first adds an empty row before changing it)
        entry = model[iter_][0]
        if entry is None:
            return

        # print(f"on_tree_row_inserted -- name: {model[iter_][0].name}  path: {path}  parent: {getattr(parent, 'name', 'None')}")
        print(f"on_tree_row_inserted -- iter_: {iter_}  entry.name: {entry.name}  path: {path}  parent: {getattr(parent, 'name', 'None')}")

        # num_children = len(list(parent_row.iterchildren()))
        # print(f"\tparent has {num_children} children")

        # Check if we need to remove the empty row in a new group. Doesn't apply if parent is the root
        if parent_row:
            for child_row in parent_row.iterchildren():
                if child_row[0] is None:
                    # We found the empty row
                    self._treestore.remove(child_row.iter)
                    break

        # And where this object will be inserted
        new_row_ind = path.get_indices()[-1]
        # print(f"new_row_inds: {new_row_ind}")

        self._protocol.add_event(event=model[iter_][0], parent=parent, index=new_row_ind)

    def on_tree_row_deleted(self, model, path):
        print(f"\non_tree_row_deleted --  path: {path}")

    def on_tree_row_changed(self, model, path, iter_):
        entry_row = model[iter_]
        entry = entry_row[0]
        print(f"\non_tree_row_changed --  path: {path}  entry.name: {getattr(entry, 'name', None)}")

        # Check if we need to remove the empty row in a new group
        if entry_row.parent is None:
            return

        for child_row in entry_row.parent.iterchildren():
            if child_row[0] is None:
                # We found the empty row
                self._treestore.remove(child_row.iter)
                break

    def on_tree_row_has_child_toggled(self, model, path, iter_):
        entry_row = model[iter_]
        entry = entry_row[0]
        num_children = model.iter_n_children(entry_row.iter)
        print(f"\non_tree_row_has_child_toggled --  path: {path}  entry: {entry.name}  num_children: {num_children}")
        if not entry.is_event and num_children == 0:
            # We're removed the last event from this group. Add a placeholder event
            model.append(entry_row.iter, [None,])

    def get_current_selection(self) -> TreeSelection:
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

        return TreeSelection(
            entry=entry,
            entry_iter=entry_iter,
            parent=parent,
            parent_iter=parent_iter,
            num_children=num_children,
            num_siblings=num_siblings
        )

    def tree_delete_selection(self, selection : TreeSelection) -> bool:
        # Since the callback doesn't contain the iterator, we need to update the Protocol ourselves
        entry_iter = selection.entry_iter
        if selection.parent is None:
            # The selection is in the root
            entry_ind = self._protocol.Entries.index(selection.entry)
            del self._protocol.Entries[entry_ind]
        else:
            # The selection is a child of an EventGroup
            entry_ind = selection.parent.entries.index(selection.entry)
            del selection.parent.entries[entry_ind]

        return self._treestore.remove(entry_iter)

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
