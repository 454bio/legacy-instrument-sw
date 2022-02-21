from collections import namedtuple
import time
from dataclasses import dataclass, field, asdict, is_dataclass
from enum import IntEnum
import json
from types import SimpleNamespace
import traceback
from typing import List, Tuple, Optional, Union
from fractions import Fraction

from ZionErrors import (
    ZionProtocolVersionError,
    ZionProtocolFileError,
)

from ZionCamera import ZionCameraParameters

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class ZionLEDColor(IntEnum):
    UV = 0
    BLUE = 1
    ORANGE = 2


@dataclass
class ZionLED:
    color: ZionLEDColor
    pulsetime: int

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionLED":
        return cls(ZionLEDColor[json_dict["color"]], json_dict["pulsetime"])


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
    leds: Tuple[ZionLED] = field(default_factory=lambda: tuple(ZionLED(color=color, pulsetime=0) for color in ZionLEDColor))

    def __post_init__(self):
        # Create a private mapping to more easily access the leds
        self._leds_dict = {led.color: led for led in self.leds}

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEvent":
        # Remove "leds" from the dictionary
        leds_list = json_dict.pop("leds", [])
        leds = tuple(ZionLED.from_json(led) for led in leds_list)
        return cls(**json_dict, leds=leds)

    def set_led_pulsetime(self, led : ZionLEDColor, pulsetime : int):
        self._leds_dict[led] = pulsetime

    def update_leds(self, leds: Union[List[ZionLED], ZionLED]):
        """ Update the instance's LED settings """
        if not isinstance(leds, (list, tuple)):
            leds = [leds,]

        for l in leds:
            self._leds_dict[l.color].pulsetime = l.pulsetime


@dataclass
class ZionEventGroup(ZionProtocolEntry):
    is_event: bool = False
    events: List[Union[ZionEvent, "ZionEventGroup"]] = field(default_factory=list)

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEventGroup":
        # Remove "event" from the dictionary
        events_list = json_dict.pop("events", [])
        events = []
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

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEvent":
        # Remove "leds" from the dictionary
        leds_list = json_dict.pop("leds", [])
        leds = [ZionLED.from_json(led) for led in leds_list]
        return cls(**json_dict, leds=leds)


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

    @property
    def names(self):
        return self._names

    @property
    def visible(self):
        return self._visible

    @property
    def types(self):
        return self._types

    def get_entry(self, obj):
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

    def save_to_file(self, filename: str):
        if not filename.endswith(".txt"):
            filename += ".txt"

        with open(filename, "w") as f:
            json.dump(self, f, indent=1, cls=ZionProtocolEncoder)

    def load_treestore(self) -> Gtk.TreeStore:
        self._load_treestore(None, self.Entries)
        return self._treestore

    def _load_treestore(
        self,
        row_iter : Optional[Gtk.TreeIter],
        entries : List[Union[ZionEventGroup, ZionEvent]],
    ):
        for entry in entries:
            new_row_iter = self._treestore.append(row_iter, self._entry_to_treestore(entry))
            if isinstance(entry, ZionEventGroup):
                # Recurse into the events
                self._load_treestore(new_row_iter, entry.events)

    def _entry_to_treestore(self, entry):
        return self._treestore_helper.get_entry(entry)

    def gtk_initialize_treeview(self, treeview : Gtk.TreeView):
        self._treestore_helper.gtk_initialize_treeview(treeview)

    def get_entries(self):
        return self.Entries

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
        event : ZionEvent = None,
        parent : Optional[ZionEventGroup] = None,
        name : Optional[str] = None,
        cycles : Optional[int] = None,
        capture : Optional[bool] = None,
        group : Optional[str] = None,
        postdelay : Optional[int] = None,
        leds : Optional[Union[List[ZionLED], ZionLED]] = None,
    ) -> ZionEvent:
        """
        Add a new event to the protocol.
        event:      If None, then create a new event.
        parent:     Parent the event. If None then the event is added to the root Entries.

        The `event` is None then the following optional keyword arguments are used to initalize the new event.

        name : str      : Descriptive name for the event (default: "")
        cycles : int    : Number of cycles for the event (default: 1)
        capture : bool  : Wheter to capture an image for the event (default: True)
        group : str     : Group string that's added to the image filename (default: "")
        postdelay : int : Number of milliseconds to wait after the event completers (default: 0)
        leds : List[ZionLED] : Led settings for the new event (default: [])
        """

        if event is None:
            event = ZionEvent()
            if parent is not None: event.parent = parent
            if name is not None : event.name = name
            if cycles is not None : event.cycles = cycles
            if capture is not None : event.capture = capture
            if group is not None : event.group = group
            if postdelay is not None : event.postdelay = postdelay
            if leds is not None: event.update_leds(leds)

        if parent:
            parent.events.append(event)
        else:
            self.Entries.append(event)

        return event

# Check for well-formed timing arrays:
def check_led_timings(LED_Blu_Timing, LED_Or_Timing, LED_UV_Timing, UV_duty_cycle=3.0):
    for led_array in [LED_Blu_Timing, LED_Or_Timing, LED_UV_Timing]:
        for onOffPair in led_array:
            if len(onOffPair) != 2:
                raise ValueError(
                    "On-Off Pair " + str(onOffPair) + " must have length 2!"
                )
            elif onOffPair[1] <= onOffPair[0]:
                raise ValueError("On-Off Pair must be in increasing order (ie time)!")
    if not UV_duty_cycle is None:
        for i in range(len(LED_UV_Timing) - 1):
            t_on1 = LED_UV_Timing[i][0]
            t_off1 = LED_UV_Timing[i][1]
            t_dc_on = t_off1 - t_on1
            t_on2 = LED_UV_Timing[i + 1][0]
            t_dc_off = t_on2 - t_off1
            if t_dc_off < t_dc_on * (100.0 - UV_duty_cycle) / UV_duty_cycle:
                raise ValueError("UV timing must have a maximum duty cycle of 3%!")
        # returns last t_on_dc so that we wait that long at the end of the event list (repeat or not)
        # ~ return LED_UV_Timing[-1][1]-LED_UV_Timing[-1][0]
