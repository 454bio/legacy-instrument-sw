from collections import UserDict
from operator import attrgetter
import time
from dataclasses import dataclass, field, asdict, is_dataclass
from enum import IntEnum
import json
from types import SimpleNamespace
import traceback
from typing import List, Tuple, Optional, Union, TypeVar, Dict
from fractions import Fraction

from ZionLED import (
    ZionLEDColor, 
    ZionLEDs, 
    ZionLEDsKT,
    ZionLEDsVT,
)

from ZionErrors import (
    ZionProtocolVersionError,
    ZionProtocolFileError,
)

from ZionCamera import ZionCameraParameters

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


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


# Maybe I can just ultimately make this a Gtk.TreeView subclass??
class ZionProtocolTreestore():
    """
    Helper class for converting the above dataclasses into
    treestore entries
    """

    FIELDS : Tuple[str] = (
        'is_event',
        'name',
        'cycles',
        'capture',
        'group',
        'postdelay',
        'leds',  # Special field that gets expanded to the number of LEDs
    )

    _names : Tuple[str] = (
        "Is Event?",
        "Name",
        "Cycles",
        "Capture?",
        "Group",
        "Post Delay\n(ms)",
        *list(f"{l.name} Pulse\n(ms)" for l in ZionLEDColor),
    )

    _visible : Tuple[bool] = (
        False,
        True,
        True,
        True,
        True,
        True,
        *list([True] * len(ZionLEDColor)),
    )

    _led_field = "pulsetime"        # This is the field to use for the LED

    def __init__(self, default_event : ZionEvent = ZionEvent()):
        # Right now the ZionEvent has all of the types that are used in the treestore
        default_entry = []

        default_event = ZionEvent()
        for f in self.FIELDS:
            if f == "leds":
                for led in getattr(default_event, f):
                    val = getattr(led, self._led_field)
                    default_entry.append(val)
            else:
                val = getattr(default_event, f)
                default_entry.append(val)

        self._types = tuple(map(type, default_entry))
        self._default_entry = tuple(default_entry)
        self._led_start_ind = self.FIELDS.index("leds")

    @property
    def names(self):
        return self._names

    @property
    def visible(self):
        return self._visible

    @property
    def types(self):
        return self._types

    def get_event(self, entry: Tuple) -> Union[ZionEvent, ZionEventGroup]:
        """
        Convert a treemodel entry (tuple) into ZionEvent or ZionEventGroup
        """

        # Make a dict out of the fields, _except_ the leds entries which are a special case
        # zip handles this gracefully for us since we can still pass in the full entry tuple
        entry_dict = {f: v for f,v in zip(self.FIELDS[:-1], entry)}

        print(entry_dict)

        if entry_dict["is_event"]:
            event = ZionEvent(**entry_dict)
            # Now load the led params
            led_pulsetimes = entry[self._led_start_ind:]
            if len(led_pulsetimes) != len(event.leds):
                raise RuntimeWarning("Problem converting treestore entry to ZionEvent... " \
                                     "Entry has {len(led_pulsetimes)} led parameters, we were expecting {len(event.leds)}")
            for ptime, led in zip(led_pulsetimes, event.leds):
                led.pulsetime = ptime
        else:
            # Name & cycles are the only thing we care about right now
            event = ZionEventGroup(name=entry_dict["name"], cycles=entry_dict["cycles"])

        print(event)
        return event

    def get_entry(self, obj : Union[ZionEvent, ZionEventGroup]):
        """
        Convert a ZionEvent or ZionEventGroup into a treemodel entry (tuple)
        """
        entry = []

        # FIELDS is shorter than _default_entry, but since leds is the last entry that's expanded
        # it all works out
        for ind, (f, default_val) in enumerate(zip(self.FIELDS, self._default_entry)):
            if hasattr(obj, f):
                if f == "leds":
                    for led in getattr(obj, f):
                        entry.append(getattr(led, self._led_field))
                else:
                    entry.append(getattr(obj, f))
            elif f == "leds":
                entry.extend(self._default_entry[ind:])
            else:
                entry.append(default_val)

        return tuple(entry)

    def gtk_initialize_treeview(self, treeview : Gtk.TreeView):
        """ Helper function to intiailize a treeview to support this model """

        for col_ind, (name, typ, vis) in enumerate(zip(self.names, self.types, self.visible)):
            if typ is bool:
                renderer = Gtk.CellRendererToggle()
                column = Gtk.TreeViewColumn(name, renderer, active=col_ind)
            else:
                renderer = Gtk.CellRendererText()

                # renderer.set_property("editable", True)
                # Center Align text (not the name though)
                column = Gtk.TreeViewColumn(name, renderer, text=col_ind)

                if col_ind > 0:
                    renderer.set_property("xalign", 0.5)

            column.set_visible(vis)

            # After the "capture" columns ZionEvents should display a value.
            # We can use the value of the first column (is_event) to control the visibility
            if col_ind > 2:
                column.add_attribute(renderer, 'visible', 0)

            treeview.append_column(column)

            # column = Gtk.TreeViewColumn(column_title, renderer, text=i)
            # # Not sure what the text argument is used for....
            # # FOUND IT: Also, with Gtk.TreeViewColumn,
            # # you can bind a property to a value in a Gtk.TreeModel.
            # # For example, you can bind the “text” property on the cell renderer
            # # to a string value in the model,
            # # thus rendering a different string in each row of the Gtk.TreeView

            # renderer.connect("edited", partial(self.text_edited, i))

        select = treeview.get_selection()
        select.connect("changed", self.on_tree_selection_changed)

    def on_tree_selection_changed(self, selection):
        print(f"selection: {selection}")
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            print(f"You selected {model[treeiter][1]}")
            parent_iter = model.iter_parent(treeiter)
            has_child = model.iter_has_child(treeiter)
            if parent_iter is None:
                print(f"Parent: Root")
            else:
                print(f"Parent: {model[parent_iter][1]}")

            print(f"has_child: {has_child}\n")
            if model[treeiter][0] or not has_child:
                print(f"\t-->event: {self.get_event(model[treeiter])}")
            else:
                print(f"\t-->event_group: NEED TO IMPLEMENT")



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

        self._treestore_helper = ZionProtocolTreestore(default_event=self.Entries[0])
        self._treestore = Gtk.TreeStore(*self._treestore_helper.types)

        if filename:
            self.load_from_file(filename, flatten=False)

    def clear(self):
        self.Entries = []
        self._treestore.clear()

    def _load_v1(self, json_ns: dict):
        print(f"ERROR: Loading a Version 1 protocol not supported!")
        # self.Entries = []

        # events = []
        # for e in json_ns.Events:
        #     leds = []
        #     if e[0]:
        #         for color, intensity in e[0].items():
        #             leds.append(ZionLED(ZionLEDColor[color.upper()], intensity, e[1]))
        #     events.append(
        #         ZionEvent(capture=e[2], group=e[4], postdelay=e[3], leds=leds)
        #     )

        # event_group = ZionEventGroup(cycles=json_ns.N + 1, events=events)
        # self.Entries.append(event_group)

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

    def _load_eventgroup_from_treestore(self, event_group : ZionEventGroup, iter):
        entries = []
        cur_iter = root_iter = self._treestore.get_iter_first()
        print(f"root_iter: {self._treestore[root_iter][1]}")

    def load_from_treestore(self):
        all_entries = []
        cur_entries = all_entries
        cur_iter = self._treestore.get_iter_first()
        print(f"root_iter: {self._treestore[cur_iter][1]}")
        while cur_iter is not None:
            event_or_group = self._treestore_helper.get_event(self._treestore[cur_iter])
            cur_entries.append(event_or_group)
            if isinstance(event_or_group, ZionEventGroup) and self._treestore.iter_has_child(cur_iter):
                # Recurse
                pass
            else:
                cur_iter = self._treestore.iter_next(cur_iter)

    def save_to_file(self, filename: str):
        if not filename.endswith(".txt"):
            filename += ".txt"

        with open(filename, "w") as f:
            json.dump(self, f, indent=1, cls=ZionProtocolEncoder)

    def init_treestore(self) -> Gtk.TreeStore:
        self._treestore.clear()
        self._init_treestore(None, self.Entries)
        return self._treestore

    def _init_treestore(
        self,
        row_iter : Optional[Gtk.TreeIter],
        entries : List[Union[ZionEventGroup, ZionEvent]],
    ):
        for entry in entries:
            new_row_iter = self._treestore.append(row_iter, self._entry_to_treestore(entry))
            if isinstance(entry, ZionEventGroup):
                # Recurse into the events
                self._init_treestore(new_row_iter, entry.events)

    def _entry_to_treestore(self, entry):
        return self._treestore_helper.get_entry(entry)

    def gtk_initialize_treeview(self, treeview : Gtk.TreeView):
        self._treestore_helper.gtk_initialize_treeview(treeview)

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
        leds : List[ZionLED] : Led settings for the new event (default: [])
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

