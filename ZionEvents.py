import math
import threading
import time

from dataclasses import (
    dataclass,
    field,
    asdict
)

from typing import (
    List,
    Optional,
    Union,
    ClassVar,
    Callable,
)

from functools import reduce
from operator import add, attrgetter

from ZionLED import ZionLEDs

# TODO: make custom capture list class (userlist?)
# ~ class CaptureList(list):

@dataclass
class ZionProtocolEntry():
    is_event: bool
    name: str = ""
    cycles: int = 1
    requested_cycle_time: int = 0
    _cycle_time: int = 0            # Not actually used as a private variable. Just used for property decleration
    _total_time_sec: float = 0.0    # Not actually used as a private variable. Just used for property decleration
    _progress: int = 0

    @staticmethod
    def dict_factory(*args, **kwargs):
        d = dict(*args, **kwargs)
        return {k:v for k,v in d.items() if not k.startswith('_')}

    def to_dict(self):
        d = {k:v for k,v in asdict(self, dict_factory=self.dict_factory).items() if not k.startswith('_')}
        print(f"{self.name}:to_dict -- {list(d.keys())}")
        return d


@dataclass
class ZionEvent(ZionProtocolEntry):
    is_event: bool = True
    capture: list = field(default_factory=lambda: [])
    captureBool: bool = False #Used only for when we flatten event
    _is_wait: bool = False
    group: str = ""
    leds: ZionLEDs = field(default_factory=ZionLEDs)
    _minimum_cycle_time: ClassVar[int] = 0
    _minimum_wait_event_time: ClassVar[int] = 0

    def __post_init__(self):
        if isinstance(self.leds, dict):
            self.leds = ZionLEDs(**self.leds)

        self.cycle_time = self.requested_cycle_time

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEvent":
        # Convert "leds" from a dictionary to ZionLEDs
        capture_json = json_dict.get("capture", {})
        if isinstance(capture_json, bool):
            capture_v3 = [0] if capture_json else []
        elif isinstance(capture_json, list):
            capture_v3 = capture_json
        else:
            raise TypeError("Capture field in protocol file must be bool or list!")
        json_dict.update({
            "leds": ZionLEDs(**json_dict.get("leds", {})),
            "capture": capture_v3,
        })
        return cls(**json_dict)

    @property
    def total_time(self) -> int:
        return self.cycle_time * self.cycles

    @property
    def total_time_sec(self) -> float:
        return self.total_time / 1000.0

    @classmethod
    def set_minimum_cycle_time(cls, minimum_cycle_time : int):
        """ minimum_cycle_time is a class property """
        cls._minimum_cycle_time = minimum_cycle_time
        cls._minimum_wait_event_time = minimum_cycle_time * 10

    @property
    def _time_to_cycles(self):
        """ Returns the number of cycles to fulfill the requested cycle time"""
        return math.ceil(self.requested_cycle_time / ZionEvent._minimum_cycle_time)

    @property
    def cycle_time(self) -> int:
        """ Return the actual cycle time. Which increment in steps of minimum_cycle_time. """
        if self.requested_cycle_time <= ZionEvent._minimum_cycle_time:
            return ZionEvent._minimum_cycle_time
        else:
            return self._time_to_cycles * ZionEvent._minimum_cycle_time

    @cycle_time.setter
    def cycle_time(self, cycle_time_in : int):
        if cycle_time_in < ZionEvent._minimum_cycle_time:
            if cycle_time_in > 0:
                print(f"WARNING: Cannot set 'cycle_time' of '{cycle_time_in}' for the ZionEvent '{self.name}'!")
                print(f"         Defaulting to minimum cycle time of '{ZionEvent._minimum_cycle_time}'.")
            cycle_time_in = ZionEvent._minimum_cycle_time
            self.requested_cycle_time = 0
        else:
            self.requested_cycle_time = cycle_time_in

    @property
    def _additional_cycle_time(self):
        return self.cycle_time - ZionEvent._minimum_cycle_time

    @property
    def is_wait(self) -> bool:
        # return self._is_wait or self.cycle_time > self._minimum_wait_event_time
        return self._is_wait

    def sleep(self, stop_event : threading.Event, progress_bar_func : Optional[Callable] = (lambda *args : None), progress_log_func : Optional[Callable] = (lambda *args: None) ):
        """ If event is a wait event, it will sleep for cycle_time and update it's progress """
        start_time = time.time()
        cycle_time_sec = self.cycle_time / 1000

        self._progress = 0
        _previous_progress = 0
        _previous_log_progress = 0
        progress_log_func(f"Waiting for {int(cycle_time_sec)} seconds...")
        while True:
            elapsed_time = time.time() - start_time
            if elapsed_time > cycle_time_sec:
                self._progress = 100
                progress_log_func(f"Wait of {cycle_time_sec:.0f} complete!")
                break

            self._progress = round(elapsed_time / cycle_time_sec * 100)

            # Set the progress if it's changed by a percent
            if self._progress > _previous_progress:
                _previous_progress = self._progress
                progress_bar_func(_previous_progress / 100)

            # Only send a log update every 5%
            if int(self._progress / 5) > _previous_log_progress:
                _previous_log_progress = int(self._progress / 5)
                progress_log_func(f"{_previous_log_progress * 5}% complete... {cycle_time_sec - elapsed_time:.0f} seconds to go...")

            if stop_event.wait(1.0):
                # We received the stop signal, abort!
                progress_bar_func(0)
                break

    def flatten(self) -> List['ZionEvent']:
        """ This will either return just ourselves in a list. Or ourselves plus a filler event that captures the extra cycle time """

        self.captureBool = True if 0 in self.capture else False #init captureBool

        #total number of frames:
        numFrames = self._time_to_cycles

        #last frame getting captured (1-index):
        lastCaptureFrame = max(self.capture)+1 if len(self.capture)>0 else 1

        #last frame containing led pulse:
        max_pw = max([led for led in self.leds.values()])
        lastPulseFrame = math.ceil(max_pw / ZionEvent._minimum_cycle_time)

        #last frame that is doing SOMETHING (ie not waiting):
        lastBusyFrame = max([lastCaptureFrame, lastPulseFrame])

        equivalent_event = [self,]
        if self._additional_cycle_time:
            for frame_ind in range(1,lastBusyFrame):
                equivalent_event.append(
                    ZionEvent(
                        captureBool=True if frame_ind in self.capture else False,
                        group=self.group,
                        requested_cycle_time = self._minimum_cycle_time,
                        name=f"{self.name} piece {frame_ind+1}"
                    )
                )

            remaining_cycle_time = (numFrames-lastBusyFrame)*ZionEvent._minimum_cycle_time
            if remaining_cycle_time < self._minimum_wait_event_time:
                cycle_filler_event = ZionEvent(
                    captureBool=False,
                    requested_cycle_time=remaining_cycle_time,
                    name=f"{self.name} wait"
                )
                extra_cycles_per_event = numFrames-lastBusyFrame
                equivalent_event.extend([cycle_filler_event,] * extra_cycles_per_event)

            else:
                equivalent_event.append(
                    ZionEvent(
                        captureBool=False,
                        requested_cycle_time=remaining_cycle_time,
                        name=f"{self.name} long wait",
                        _is_wait=True,
                    )
                )

        return equivalent_event * self.cycles


@dataclass
class ZionEventGroup(ZionProtocolEntry):
    is_event: bool = False
    entries: List[Union[ZionEvent, "ZionEventGroup"]] = field(default_factory=list)
    _minimum_cycle_time: int = 0

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEventGroup":
        # Remove "eventries" from the dictionary
        entries_list = json_dict.pop("entries", [])
        entries : Union[List[ZionEvent], List["ZionEventGroup"], List] = []
        for event_or_group in entries_list:
            # Use the "is_event" field to determine which type
            if event_or_group["is_event"]:
                entries.append(ZionEvent.from_json(event_or_group))
            else:
                # Hurray recursion!
                entries.append(cls.from_json(event_or_group))

        return cls(**json_dict, entries=entries)

    def __post_init__(self):
        self.refresh_minimum_cycle_time()
        self.cycle_time = self.requested_cycle_time

    def flatten(self) -> List[ZionEvent]:
        """
        Convert a ZionEventGroup to an equivalent list of ZionEvents
        """

        # Pre-calcute the wait events or filler events we'll use to get the cycle time correct
        wait_events = []
        if self._additional_cycle_time:
            if self._additional_cycle_time > ZionEvent._minimum_wait_event_time:
                wait_events = [
                    ZionEvent(
                        capture=[],
                        requested_cycle_time=self._additional_cycle_time,
                        name=f"{self.name} long wait",
                        _is_wait=True,
                    ),
                ]
            else:
                cycle_filler_event = ZionEvent(
                    capture=[],
                    requested_cycle_time=ZionEvent._minimum_cycle_time,
                    name=f"{self.name} wait"
                )
                wait_events.extend([cycle_filler_event,] * self._additional_cycles)

        flat_events = []
        for _ in range(self.cycles):
            for event in self.entries:
                if isinstance(event, (ZionEvent, ZionEventGroup)):
                    flat_events.extend(event.flatten())
                else:
                    raise RuntimeError(
                        f"Unrecognized type in the event list: {type(event)}"
                    )

            flat_events.extend(wait_events)

        return flat_events

    @property
    def total_time(self) -> int:
        return self.cycle_time * self.cycles

    @property
    def total_time_sec(self) -> float:
        return self.total_time / 1000.0

    @property
    def _additional_cycle_time(self):
        return self.cycle_time - self._minimum_cycle_time

    @property
    def _additional_cycles(self):
        return math.ceil(self._additional_cycle_time / ZionEvent._minimum_cycle_time)

    @property
    def _time_to_cycles(self):
        """ Returns the number of cycles to fulfill the requested cycle time"""
        return math.ceil(self.requested_cycle_time / ZionEvent._minimum_cycle_time)

    @property
    def cycle_time(self) -> int:
        """ Return the actual cycle time. Which increment in steps of ZionEvent._minimum_cycle_time. """
        if self.requested_cycle_time <= self._minimum_cycle_time:
            return self._minimum_cycle_time
        else:
            return self._time_to_cycles * ZionEvent._minimum_cycle_time

    @cycle_time.setter
    def cycle_time(self, cycle_time_in : int):
        if cycle_time_in < self._minimum_cycle_time:
            if cycle_time_in > 0:
                print(f"WARNING: Cannot set 'cycle_time' of '{cycle_time_in}' for the ZionEvent '{self.name}'!")
                print(f"         Defaulting to minimum cycle time of '{self._minimum_cycle_time}'.")
            cycle_time_in = self._minimum_cycle_time
            self.requested_cycle_time = 0
        else:
            self.requested_cycle_time = cycle_time_in

    def refresh_minimum_cycle_time(self):
        """
        This will get called if one of the entries (or decendents of entries) updates their cycle time
        """
        print(f"'{self.name}' -- refresh_minimum_cycle_time()")
        old_min_cycle_time = self._minimum_cycle_time
        self._minimum_cycle_time = reduce(add, map(attrgetter('total_time'), self.entries), 0)
        if self._minimum_cycle_time != old_min_cycle_time:
            self.cycle_time = self.requested_cycle_time
