import time
from operator import itemgetter
import keyboard
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
import json
from types import SimpleNamespace
import traceback
from typing import List

class ZionLEDColor(Enum):
	BLUE_GREEN = auto()
	ORANGE = auto()
	UV = auto()

@dataclass
class ZionLED:
	color: ZionLEDColor
	intensity: float

@dataclass
class ZionEvent:
	enabled: bool
	leds: List[ZionLED] = field(default_factory=list)
	
class ZionProtocol:
	N = 0
	Events = []
	Interrepeat_Delay = 0.0

	def __init__(
		self, 
		N: int = 0, 
		Events: list = [], 
		Interrepeat_Delay: float = 0.0, 
		filename: str = None
	):
		if filename:
			self.loadProtocolFromFile(filename)
		else:
			self.N = N
			self.Interrepeat_Delay = Interrepeat_Delay
			self.Events = list(map(tuple, Events))

	def loadProtocolFromFile(self, filename : str):
		try:
			with open(filename) as f:
				json_ns = SimpleNamespace(**json.load(f))
			self.N = json_ns.N
			self.Events = list(map(tuple, json_ns.Events))
			self.Interrepeat_Delay = json_ns.Interrepeat_Delay
		except Exception as e:
			tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
			print(f"ERROR Loading Protocol File: {filename}\n{tb}")

	def saveProtocolToFile(self, filename : str):
		with open(filename, 'w') as f:
			json.dump(self.__dict__, f, indent=1)

	def performEvent(self, event, gpio_ctrl):
		#if not event[0] is None:
		gpio_ctrl.enable_vsync_callback(event[0], event[1], event[2], event[4])
			# ~ gpio_ctrl.enable_vsync_callback()
		if event[3]>0:
			time.sleep(event[3]/1000.)

#Check for well-formed timing arrays:
def check_led_timings(LED_Blu_Timing, LED_Or_Timing, LED_UV_Timing, UV_duty_cycle=3.0):
	for led_array in [LED_Blu_Timing, LED_Or_Timing, LED_UV_Timing]:
		for onOffPair in led_array:
			if len(onOffPair) != 2:
				raise  ValueError('On-Off Pair ' + str(onOffPair) + ' must have length 2!')
			elif onOffPair[1] <= onOffPair[0]:
				raise ValueError('On-Off Pair must be in increasing order (ie time)!')
	if not UV_duty_cycle is None:
		for i in range(len(LED_UV_Timing)-1):
			t_on1 = LED_UV_Timing[i][0]
			t_off1 = LED_UV_Timing[i][1]
			t_dc_on = t_off1-t_on1
			t_on2 = LED_UV_Timing[i+1][0]
			t_dc_off = t_on2 - t_off1
			if t_dc_off < t_dc_on*(100.0-UV_duty_cycle)/UV_duty_cycle:
				raise ValueError('UV timing must have a maximum duty cycle of 3%!')
		#returns last t_on_dc so that we wait that long at the end of the event list (repeat or not)
		# ~ return LED_UV_Timing[-1][1]-LED_UV_Timing[-1][0]

def print_eventList(eventList): #for testing
	for event in eventList:
		print(event)
