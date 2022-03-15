import math

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
)

from functools import reduce
from operator import add, attrgetter

from ZionLED import ZionLEDs


@dataclass
class ZionProtocolEntry():
    is_event: bool
    name: str = ""
    cycles: int = 1
    requested_cycle_time: int = 0
    _cycle_time: int = 0            # Not actually used as a private variable. Just used for property decleration
    _total_time_sec: float = 0.0    # Not actually used as a private variable. Just used for property decleration

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
    capture: bool = True
    group: str = ""
    leds: ZionLEDs = field(default_factory=ZionLEDs)
    _minimum_cycle_time: ClassVar[int] = 0

    def __post_init__(self):
        if isinstance(self.leds, dict):
            self.leds = ZionLEDs(**self.leds)

        self.cycle_time = self.requested_cycle_time

    @classmethod
    def from_json(cls, json_dict: dict) -> "ZionEvent":
        # Convert "leds" from a dictionary to ZionLEDs
        json_dict.update({
            "leds": ZionLEDs(**json_dict.get("leds", {})),
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
    def additional_cycle_time(self):
        return self.cycle_time - ZionEvent._minimum_cycle_time

    def flatten(self) -> List['ZionEvent']:
        """ This will create a list of events that is equivalent to the number of cycles and additional cycle time"""
        extra_cycles_per_event = self._time_to_cycles - 1

        cycle_filler_event = ZionEvent(
            capture=False,
            requested_cycle_time=ZionEvent._minimum_cycle_time
        )

        # equivalent_event will contain a list of this event padded
        # with extra blank events to fulfill the cycle time
        equivalent_event = [self,]
        equivalent_event.extend([cycle_filler_event,] * extra_cycles_per_event)

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
        cycle_filler_event = ZionEvent(
            capture=False,
            requested_cycle_time=ZionEvent._minimum_cycle_time
        )

        flat_events = []
        for _ in range(self.cycles):
            for event in self.entries:
                if isinstance(event, (ZionEvent, ZionEventGroup)):
                    flat_events.extend(event.flatten())
                else:
                    raise RuntimeError(
                        f"Unrecognized type in the event list: {type(event)}"
                    )

            if self._additional_cycles:
                flat_events.extend([cycle_filler_event,] * self._additional_cycles)

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
