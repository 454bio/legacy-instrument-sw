import json
import traceback
import time

from functools import partial
from fractions import Fraction
from types import SimpleNamespace
from dataclasses import (
    is_dataclass,
    asdict,
    fields,
)
from typing import (
    List,
    Optional,
    Union,
    Dict,
    Tuple,
)

from ZionLED import (
    ZionLEDColor,
    ZionLEDs,
)

from ZionEvents import (
    ZionEvent,
    ZionEventGroup,
)
from ZionCamera import ZionCameraParameters
from ZionErrors import ZionProtocolVersionError
from ZionTree import (
    ZionTreeSelection,
    ZionProtocolTree,
)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk


class ZionProtocolEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (ZionEvent, ZionEventGroup)):
            return obj.to_dict()
        elif is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, ZionProtocol):
            return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
        if isinstance(obj, ZionLEDColor):
            return obj.name
        if isinstance(obj, Fraction):
            return float(obj)
        if isinstance(obj, ZionLEDs):
            return {k.name: v for k,v in obj.data.items()}
        return json.JSONEncoder.default(self, obj)


# TODO: Have ZionProtocol manage the TreeStore. It will mirror the Entries.
class ZionProtocol():

    def __init__(self, filename : str = None, camera_parameters : ZionCameraParameters = ZionCameraParameters()):
        self.Version: int = 2
        self.Parameters: ZionCameraParameters = camera_parameters
        self.Entries: List[Union[ZionEvent, ZionEventGroup]] = []
        self._protocoltree = None # type: ZionProtocolTree

        min_cycle_time = max(int(camera_parameters.exposure_speed / 1000), int(1000 / camera_parameters.framerate))
        ZionEvent.set_minimum_cycle_time(min_cycle_time)
        # Set the minimum event time based on the camera parameters
        if filename:
            self.load_from_file(filename, flatten=False)

    def _load_v1(self, json_ns: dict):
        print(f"ERROR: Loading a Version 1 protocol not supported!")

    def _load_v2(self, json_ns: dict):
        print(f"Loading a Version 2 protocol...")

        # TODO: Use a serialization library that's still human editable
        self.Entries = []
        # Ensure each element of Entries looks like an EventGroup
        for eg in json_ns.Entries:
            if eg["is_event"]:
                self.Entries.append(ZionEvent.from_json(eg))
            else:
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

            self._protocoltree.reload_treestore(self.Entries)
        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            print(f"ERROR Loading Protocol File: {filename}\n{tb}")

    def save_to_file(self, filename: str):
        if not filename.endswith(".txt"):
            filename += ".txt"

        if self._protocoltree.is_dirty():
            self.Entries = self._protocoltree.get_entries()
            print(self.Entries)

        with open(filename, "w") as f:
            json.dump(self, f, indent=1, cls=ZionProtocolEncoder)

    def get_entries(self):
        if self._protocoltree.is_dirty():
            self.Entries = self._protocoltree.get_entries()

        return self.Entries

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
            # if parent is not None: event_group._parent = parent
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

        name : str       : Descriptive name for the event (default: "")
        cycles : int     : Number of cycles for the event (default: 1)
        capture : bool   : Wheter to capture an image for the event (default: True)
        group : str      : Group string that's added to the image filename (default: "")
        _cycle_time : int: Number of milliseconds the event should take to complete (default: exposure_time)
        leds : ZionLEDs  : Led settings for the new event (default: ZionLEDs())
        """

        # Create the event if it doesn't exist
        if event is None:
            # if parent is not None:
            #     kwargs["_parent"] = parent
            event = ZionEvent(**kwargs)

        # Grab the list we'll be inserting into
        if parent is None:
            entries = self.Entries
        else:
            # # If an event is passed in that already has a parent define AND we passed in parent as a kwarg, then they should be the same
            # assert event._parent is None or event._parent is parent
            # if event._parent is None:
            #     # If we haven't defined the parent for a passed in event
            #     event._parent = parent

            entries = parent.entries

        # Equivalent to entries.append(..) if index is None
        if index is None:
            index = len(entries)

        # Add the event
        entries.insert(index, event)

        return event

    def flatten(self) -> List[ZionEvent]:
        """
        Convert Entries to an equivalent list of only ZionEvents
        """
        flat_events = []
        for event in self.Entries:
            if isinstance(event, (ZionEvent, ZionEventGroup)):
                flat_events.extend(event.flatten())
            else:
                raise RuntimeError(
                    f"Unrecognized type in the event list: {type(event)}"
                )

        return flat_events

    # The following gtk_* calls are pass through calls from ZionSession or ZionGtk
    def gtk_initialize_treeview(self, treeview : Gtk.TreeView):
        self._protocoltree = ZionProtocolTree(treeview)

    def gtk_new_event(self):
        self._protocoltree.tree_add_entry(is_event=True)

    def gtk_new_group(self):
        self._protocoltree.tree_add_entry(is_event=False)

    def gtk_delete_selection(self, selection: ZionTreeSelection):
        self._protocoltree.tree_delete_selection(selection)

    def gtk_get_current_selection(self) -> ZionTreeSelection:
        return self._protocoltree.get_current_selection()
