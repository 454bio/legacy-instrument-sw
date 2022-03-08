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
    _cycle_time: int = 0  # Not actually used as a private variable. Just used for property decleration
    _total_time: int = 0  # Not actually used as a private variable. Just used for property decleration

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
        # print(f"-->{self.name}:total_time")
        # tot_time = self._cycle_time * self.cycles
        # print(f"<--{self.name}:total_time = {tot_time}")
        return self.cycle_time * self.cycles

    @classmethod
    def set_minimum_cycle_time(cls, minimum_cycle_time : int):
        """ minimum_cycle_time is a class property """
        cls._minimum_cycle_time = minimum_cycle_time

    @property
    def cycle_time(self) -> int:
        if self.requested_cycle_time < ZionEvent._minimum_cycle_time:
            return ZionEvent._minimum_cycle_time
        else:
            return self.requested_cycle_time

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
        # print(f"-->{self.name}:total_time")
        # tot_time = self.cycle_time * self.cycles
        # print(f"<--{self.name}:total_time = {tot_time}")
        return self.cycle_time * self.cycles

    @property
    def cycle_time(self) -> int:
        if self.requested_cycle_time < self._minimum_cycle_time:
            return self._minimum_cycle_time
        else:
            return self.requested_cycle_time

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
