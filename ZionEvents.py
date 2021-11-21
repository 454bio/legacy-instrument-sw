import time
from operator import itemgetter
import keyboard
import threading

class ZionProtocol:
	def __init__(self, filename=None):
		eventList = []
		if filename:
			with open(filename) as f:
				for line in f:
					if line[0]=='N':
						N = int(line[2:-1])
					else:
						event = tuple()
						event_params = line[1:-2].split(', ')
						event_time = float(event_params[1])
						event_color = event_params[0].strip('\'')
						if event_color=='None':
							event += (None, event_time, None, None)
						else:
							event += (event_color, event_time, int(event_params[2]))
							if event_params[3]=='True':
								event += (True,)
							else:
								event += (False,)
						eventList.append(event)
			self.N = N
			self.Events = eventList
			self.capture_threads = []
		else:
			self.N = 0
			self.Events = []
			self.capture_threads = []

	def performEvent(self, event, gpio_ctrl):
		if not event[0] is None:
			gpio_ctrl.enable_vsync_callback(event[0], event[1], event[2])
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
