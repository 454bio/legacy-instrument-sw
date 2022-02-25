import time
from dataclasses import dataclass, field, asdict, is_dataclass, fields
import json
from types import SimpleNamespace
import traceback
from typing import List, Optional, Union, Dict
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
    events: List[Union[ZionEvent, "ZionEventGroup"]] = field(default_factory=list)

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEventGroup":
        # Remove "event" from the dictionary
        events_list = json_dict.pop("events", [])
        events : Union[List[ZionEvent], List["ZionEventGroup"], List] = []
        for event_or_group in events_list:
            # This is not a robust way to go from json <-> python...
            # But for now it allows people to edit the JSON directly without crazy class names
            if "events" in event_or_group:
                # Hurray recursion!
                events.append(cls.from_json(event_or_group))
            else:
                events.append(ZionEvent.from_json(event_or_group))

        return cls(**json_dict, events=events)

    def flatten(self) -> List[ZionEvent]:
        """
        Convert a ZionEventGroup to an equivalent list of ZionEvents
        """

        flat_events = []
        for _ in range(self.cycles):
            for event in self.events:
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
            if "events" not in eg:
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
            parent.events.append(event_group)
        else:
            self.Entries.append(event_group)

        return event_group

    def add_event(
        self,
        event : Optional[ZionEvent] = None,
        parent: Optional[ZionEventGroup] = None,
        **kwargs
    ) -> ZionEvent:
        """
        Add a new event to the protocol.
        event:      If None, then create a new event.
        parent:     Parent the event. If None then the event is added to the root Entries.

        The `event` is None then the following optional keyword arguments are available initalize the new event.

        name : str      : Descriptive name for the event (default: "")
        cycles : int    : Number of cycles for the event (default: 1)
        capture : bool  : Wheter to capture an image for the event (default: True)
        group : str     : Group string that's added to the image filename (default: "")
        postdelay : int : Number of milliseconds to wait after the event completers (default: 0)
        leds : ZionLEDs : Led settings for the new event (default: ZionLEDs())
        """

        if event is None:
            if parent is not None:
                kwargs["parent"] = parent
            event = ZionEvent(**kwargs)

        if parent:
            parent.events.append(event)
        else:
            self.Entries.append(event)

        return event

    def gtk_new_event(self):
        print("gtk_new_event")


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
        select = self._treeview.get_selection()
        select.connect("changed", self.on_tree_selection_changed)

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
                # Recurse into the events
                self._init_treestore(new_row_iter, entry.events)

    def get_event_entry_str(self, treeviewcolumn, cell, model, iter_, event_field):
        event = model.get_value(iter_, 0)

        # Only update a field if it's present, otherwise don't show it
        cell_value = getattr(event, event_field, None)

        if cell_value is not None:
            cell.set_property('text', str(cell_value))

        cell.set_property('visible', (cell_value is not None))

    def get_event_entry_bool(self, treeviewcolumn, cell, model, iter_, event_field):
        event = model.get_value(iter_, 0)

        # Only update a field if it's present, otherwise don't show it
        cell_value = getattr(event, event_field, None)

        if cell_value is not None:
            cell.set_property('active', cell_value)

        cell.set_property('visible', (cell_value is not None))

    def get_event_entry_led(self, treeviewcolumn, cell, model, iter_, led_key):
        event = model.get_value(iter_, 0)

        # Only update a field if it's present, otherwise don't show it
        cell_value = getattr(event, 'leds', {}).get(led_key, None)

        if cell_value is not None:
            cell.set_property('text', str(cell_value))

        cell.set_property('visible', (cell_value is not None))

    def on_tree_selection_changed(self, selection):
        print(f"selection: {selection}")
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            print(f"You selected: '{model[treeiter][0].name}'")
            parent_iter = model.iter_parent(treeiter)
            has_child = model.iter_has_child(treeiter)
            if parent_iter is None:
                print(f"Parent: 'Root'")
            else:
                print(f"Parent: '{model[parent_iter][0].name}'")

            print(f"has_child: {has_child}\n")
            if model[treeiter][0].is_event or not has_child:
                print(f"\t-->event: ")
            else:
                print(f"\t-->event_group: ")
