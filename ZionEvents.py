from dataclasses import (
    dataclass,
    field,
)

from typing import (
    List,
    Optional,
    Union,
    ClassVar,
)

from functools import reduce
from operator import add, attrgetter

from ZionLED import ZionLEDs


@dataclass
class ZionProtocolEntry():
    is_event: bool
    name: str = ""
    cycles: int = 1
    _cycle_time: int = 0
    _total_time: int = 0
    _parent: Optional['ZionEventGroup'] = None

    @property
    def total_time(self) -> int:
        return self._cycle_time * self.cycles

    @property
    def cycle_time(self) -> int:
        return self._cycle_time

    @cycle_time.setter
    def cycle_time(self, cycle_time_in : int):
        self._cycle_time = cycle_time_in

@dataclass
class ZionEvent(ZionProtocolEntry):
    is_event: bool = True
    capture: bool = True
    group: str = ""
    leds: ZionLEDs = field(default_factory=ZionLEDs)
    minimum_cycle_time: ClassVar[int] = 0

    def __post_init__(self):
        if isinstance(self.leds, dict):
            self.leds = ZionLEDs(**self.leds)

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEvent":
        # Convert "leds" from a dictionary to ZionLEDs
        json_dict.update({"leds": ZionLEDs(**json_dict.get("leds", {}))})
        return cls(**json_dict)

    @property
    def total_time(self) -> int:
        return self._cycle_time * self.cycles

    def set_minimum_cycle_time(minimum_cycle_time : int):
        """ minimum_cycle_time is a class property """
        ZionEvent.minimum_cycle_time = minimum_cycle_time

    @property
    def cycle_time(self) -> int:
        if self._cycle_time < ZionEvent.minimum_cycle_time:
            self._cycle_time = ZionEvent.minimum_cycle_time

        return self._cycle_time

    @cycle_time.setter
    def cycle_time(self, cycle_time_in : int):
        if cycle_time_in == 0:
            cycle_time_in = ZionEvent.minimum_cycle_time
        elif cycle_time_in < ZionEvent.minimum_cycle_time:
            print(f"WARNING: Cannot set 'cycle_time' of '{cycle_time_in}' for the ZionEvent '{self.name}'!")
            print(f"         Defaulting to minimum cycle time of '{ZionEvent.minimum_cycle_time}'.")
            cycle_time_in = ZionEvent.minimum_cycle_time

        self._cycle_time = cycle_time_in

@dataclass
class ZionEventGroup(ZionProtocolEntry):
    is_event: bool = False
    entries: List[Union[ZionEvent, "ZionEventGroup"]] = field(default_factory=list)

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEventGroup":
        # Remove "eventries" from the dictionary
        entries_list = json_dict.pop("entries", [])
        entries : Union[List[ZionEvent], List["ZionEventGroup"], List] = []
        for event_or_group in entries_list:
            # This is not a robust way to go from json <-> python...
            # But for now it allows people to edit the JSON directly without crazy class names
            if event_or_group["is_event"]:
                entries.append(ZionEvent.from_json(event_or_group))
            else:
                # Hurray recursion!
                entries.append(cls.from_json(event_or_group))

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

    @property
    def total_time(self) -> int:
        return self.cycle_time * self.cycles

    def minimum_cycle_time(self):
        return reduce(add, map(attrgetter('total_time'), self.entries), 0)

    @property
    def cycle_time(self) -> int:
        if self._cycle_time < self.minimum_cycle_time():
            self._cycle_time = self.minimum_cycle_time()

        return self._cycle_time

    @cycle_time.setter
    def cycle_time(self, cycle_time_in : int):
        min_cycle_time = self.minimum_cycle_time()
        if cycle_time_in == 0:
            # Reset the cycle time to the minimum allowed
            cycle_time_in = min_cycle_time
        elif cycle_time_in < min_cycle_time:
            # Don't print the warning message if 0 passed in. Means we just want the minimum time.
            print(f"WARNING: Cannot set 'cycle_time' of '{cycle_time_in}' for the EventGroup '{self.name}'!")
            print(f"         Defaulting to minimum cycle_time of '{min_cycle_time}'.")
            cycle_time_in = min_cycle_time

        self._cycle_time = cycle_time_in
