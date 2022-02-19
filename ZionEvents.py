import time
from dataclasses import dataclass, field, asdict, is_dataclass
from enum import Enum, auto
import json
from types import SimpleNamespace
import traceback
from typing import List
from fractions import Fraction

from ZionErrors import (
    ZionProtocolVersionError,
    ZionProtocolFileError,
)

from ZionCamera import ZionCameraParameters

class ZionLEDColor(Enum):
    UV = auto()
    BLUE = auto()
    ORANGE = auto()


@dataclass
class ZionLED:
    color: ZionLEDColor
    pulsetime: int

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionLED":
        return cls(ZionLEDColor[json_dict["color"]], json_dict["pulsetime"])


@dataclass
class ZionEvent:
    capture: bool = False
    group: str = ""
    postdelay: float = 0.0
    cycles: int = 1
    leds: List[ZionLED] = field(default_factory=list)

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEvent":
        # Remove "leds" from the dictionary
        leds_list = json_dict.pop("leds", [])
        leds = [ZionLED.from_json(led) for led in leds_list]
        return cls(**json_dict, leds=leds)


@dataclass
class ZionEventGroup:
    name: str = ""
    cycles: int = 1
    events: List[ZionEvent] = field(default_factory=list)

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
        """ " Convert a ZionEventGroup to an equivalent list of ZionEvents"""
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


class ZionProtocol:
    def __init__(self, filename: str = None):
        self.Version: int = 2
        self.Parameters: ZionCameraParameters = ZionCameraParameters()
        self.EventGroups: List[ZionEventGroup] = [ZionEventGroup()]

        if filename:
            self.load_from_file(filename, flatten=False)

    def _load_v1(self, json_ns: dict):
        print(f"Loading a Version 1 protocol...")
        self.EventGroups = []

        events = []
        for e in json_ns.Events:
            leds = []
            if e[0]:
                for color, intensity in e[0].items():
                    leds.append(ZionLED(ZionLEDColor[color.upper()], intensity, e[1]))
            events.append(
                ZionEvent(capture=e[2], group=e[4], postdelay=e[3], leds=leds)
            )

        event_group = ZionEventGroup(cycles=json_ns.N + 1, events=events)
        self.EventGroups.append(event_group)

    def _load_v2(self, json_ns: dict):
        print(f"Loading a Version 2 protocol...")

        # TODO: Use a serialization library that's still human editable
        self.EventGroups = []
        # Ensure each element of EventGroups looks like an EventGroup
        for eg in json_ns.EventGroups:
            if "events" not in eg:
                raise ZionProtocolFileError(
                    "Each top-level element in 'EventGroups' must be an EventGroup!"
                )

            self.EventGroups.append(ZionEventGroup.from_json(eg))

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
                # Unwrap nested event groups for now
                # TODO: Add support for multiple/nested event groups in the GUI
                if flatten:
                    if len(self.EventGroups) > 1:
                        raise ZionProtocolFileError(
                            "Multiple top-level EventsGroups is not supported yet...."
                        )

                    flat_events = self.EventGroups[0].flatten()
                    self.EventGroups[0].events = flat_events
            else:
                raise ZionProtocolVersionError(
                    f"Version {file_version} is not supported... "
                    "Check if there's an newer version of the GUI available"
                )

            print(self.EventGroups)
        except Exception as e:
            tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            print(f"ERROR Loading Protocol File: {filename}\n{tb}")

    def save_to_file(self, filename: str):
        if not filename.endswith(".txt"):
            filename += ".txt"

        with open(filename, "w") as f:
            json.dump(self, f, indent=1, cls=ZionProtocolEncoder)

    def get_event_groups(self):
        return self.EventGroups

    def performEvent(self, event: ZionEvent, gpio_ctrl: "ZionGPIO"):
        gpio_ctrl.enable_vsync_callback(event)
        if event.postdelay > 0:
            time.sleep(event.postdelay / 1000.0)


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
