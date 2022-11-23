
from enum import IntEnum
from typing import TypeVar, Union, Dict, Optional
from collections import UserDict
from operator import attrgetter

from ZionErrors import (
    ZionInvalidLEDColor,
    ZionInvalidLEDPulsetime,
    ZionInvalidLEDMaxPulsetime,
)

class ZionLEDColor(IntEnum):
    UV = 0
    BLUE = 1
    GREEN = 2
    ORANGE = 3
    RED = 4
    COLOR5 = 5
    COLOR6 = 6
    COLOR7 = 7

ZionLEDsKT = TypeVar('ZionLEDsKT', str, int, ZionLEDColor)
ZionLEDsVT = int

class ZionLEDs(UserDict):
    _colors = list(map(attrgetter('name'), ZionLEDColor))
    __max_pulsetime = 190
    __pigpio_wave_id = -1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # On the off chance we are expecting that iterating through the
        # items will return them in the order as ZionLEDColor but we're
        # initializing it with out of order keywords/dict
        sorted_dict = {}
        for color in ZionLEDColor:
            sorted_dict[color] = self.setdefault(color, 0)
        self.data = sorted_dict

    def __setitem__(self, led_color: Union[ZionLEDColor, str, int], pulsetime: int) -> None:
        """ Only allow colors and pulse time in a valid range """
        try:
            if isinstance(led_color, str):
                led_color = ZionLEDColor[led_color.upper()]
            elif isinstance(led_color, int):
                led_color = ZionLEDColor(led_color)
        except (ValueError, KeyError):
            raise ZionInvalidLEDColor(f"Invalid LED color/index {led_color}.\nValid colors are: {self._colors} or indices: {list(map(attrgetter('value'), ZionLEDColor))}")

        if not isinstance(pulsetime, int):
            raise TypeError("Value (pulsetime) must be an integer")

        if pulsetime < 0 or pulsetime > self.__max_pulsetime:
            raise ZionInvalidLEDPulsetime(f"Pulsetime must be between 0 and {self.__max_pulsetime}")

        return super().__setitem__(led_color, pulsetime)

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other):
        return hash(repr(self)) == hash(repr(other))

    def __neq__(self, other):
        return hash(repr(self)) != hash(repr(other))

    def __repr__(self):
        # Make sure it will return just the LEDColors in defined order
        return str({k: self[k] for k in ZionLEDColor})

    @classmethod
    def set_max_pulsetime(cls, max_pulsetime_ms : int):
        """ The pulsetime is a class level value. In units of milliseconds """
        if max_pulsetime_ms < 0:
            raise ZionInvalidLEDMaxPulsetime(f"Invalid maximum pulsetime: {max_pulsetime}\nMaximum pulsetime must be greater than or equal to 0")

        cls.__max_pulsetime = max_pulsetime_ms

    @property
    def max_pulsetime(self):
        return self.__max_pulsetime

    def set_wave_id(self, wave_id : int):
        self.__pigpio_wave_id = wave_id

    def get_wave_id(self):
        return self.__pigpio_wave_id

    def has_wave_id(self):
        return self.__pigpio_wave_id > -1

    def clear_wave_id(self):
        self.__pigpio_wave_id = -1

    # ~ def set_pulsetime(
        # ~ self,
        # ~ led : Optional[ZionLEDsKT] = None,
        # ~ pulsetime : Optional[ZionLEDsVT] = None,
        # ~ led_dict : Optional[Dict[ZionLEDsKT, ZionLEDsVT]] = None):

        # ~ # Check valid arguments
        # ~ if led is not None or pulsetime is not None:
            # ~ if led is None:
                # ~ raise TypeError(f"Missing 'led' parameter for 'pulsetime={pulsetime}'!")
            # ~ if pulsetime is None:
                # ~ raise TypeError(f"Can't set 'led={led}' without a 'pulsetime' argument!")
            # ~ self[led] = pulsetime

        # ~ if led_dict is not None:
            # ~ self.update(led_dict)

class ZionLEDTimings(UserDict):
    _colors = list(map(attrgetter('name'), ZionLEDColor))
    __max_pulsetime = 190
    __pigpio_wave_id = -1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # On the off chance we are expecting that iterating through the
        # items will return them in the order as ZionLEDColor but we're
        # initializing it with out of order keywords/dict
        sorted_dict = {}
        for color in ZionLEDColor:
            sorted_dict[color] = self.setdefault(color, None)
        self.data = sorted_dict

    def __setitem__(self, led_color: Union[ZionLEDColor, str, int], pulsetimings: tuple) -> None:
        """ Only allow colors and pulse time in a valid range """
        try:
            if isinstance(led_color, str):
                led_color = ZionLEDColor[led_color.upper()]
            elif isinstance(led_color, int):
                led_color = ZionLEDColor(led_color)
        except (ValueError, KeyError):
            raise ZionInvalidLEDColor(f"Invalid LED color/index {led_color}.\nValid colors are: {self._colors} or indices: {list(map(attrgetter('value'), ZionLEDColor))}")
        if pulsetimings is not None:
            if not isinstance(pulsetimings, tuple) or not len(pulsetimings)==2:
                raise TypeError(f"pulsetimings must be a 2-element tuple!")
            if not isinstance(pulsetimings[0], list) or not isinstance(pulsetimings[1], list):
                raise TypeError(f"pulsetimings must contain 2 lists!")
            if not len(pulsetimings[0]) == len(pulsetimings[1]):
                raise TypeError(f"Timings and levels must be the same length!")
            if any([not isinstance(pl, bool) for pl in pulsetimings[1]]):
                raise TypeError(f"Levels must contain only bools!")
            if any([pt < 0 for pt in pulsetimings[0]]) or any([pt > self.__max_pulsetime for pt in pulsetimings[0]]):
                raise ZionInvalidLEDPulsetime(f"Pulsetime must be between 0 and {self.__max_pulsetime}")

        return super().__setitem__(led_color, pulsetimings)

    def __hash__(self):
        return hash(repr(self))

    def __eq__(self, other):
        return hash(repr(self)) == hash(repr(other))

    def __neq__(self, other):
        return hash(repr(self)) != hash(repr(other))

    def __repr__(self):
        # Make sure it will return just the LEDColors in defined order
        return str({k: self[k] for k in ZionLEDColor})

    @classmethod
    def set_max_pulsetime(cls, max_pulsetime_ms : int):
        """ The pulsetime is a class level value. In units of milliseconds """
        if max_pulsetime_ms < 0:
            raise ZionInvalidLEDMaxPulsetime(f"Invalid maximum pulsetime: {max_pulsetime}\nMaximum pulsetime must be greater than or equal to 0")

        cls.__max_pulsetime = max_pulsetime_ms

    @property
    def max_pulsetime(self):
        return self.__max_pulsetime

    def set_wave_id(self, wave_id : int):
        self.__pigpio_wave_id = wave_id

    def get_wave_id(self):
        return self.__pigpio_wave_id

    def has_wave_id(self):
        return self.__pigpio_wave_id > -1

    def clear_wave_id(self):
        self.__pigpio_wave_id = -1

    def set_pulsetimings(
        self,
        led : Optional[ZionLEDsKT] = None,
        # TODO: Use Optional()? Use ZionLEDsKT or ZionLEDsVT?
        pulsetimings : tuple = None):

        # Check valid arguments
        if led is not None or pulsetimings is not None:
            if led is None:
                raise TypeError(f"Missing 'led' parameter for 'pulsetimings={pulsetimings}'!")
            if pulsetimings is None:
                raise TypeError(f"Can't set 'led={led}' without a 'pulsetimings' argument!")
            self[led] = pulsetimings
