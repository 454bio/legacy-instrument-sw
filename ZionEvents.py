from time import sleep
from operator import itemgetter
import keyboard

class ZionScript():
	def __init__(LED_Blu_Timing, LED_Or_Timing, LED_UV_Timing, Camera_Capture_Times, Repeat_N=0):
		#first take last UV time on to create refactory period:
		uv_time_on = LED_UV_Timing[-1][1]-LED_UV_Timing[-1][0]
		#First we create all events (we'll sort later):
		eventList = []
		eventList += [(time_pair[0], 'led_on', 'Blue') for time_pair in LED_Blu_Timing]
		eventList += [(time_pair[1], 'led_off', 'Blue', time_pair[1]) for time_pair in LED_Blu_Timing]
		eventList += [(time_pair[0], 'led_on', 'Orange', time_pair[0]) for time_pair in LED_Or_Timing]
		eventList += [(time_pair[1], 'led_off', 'Orange', time_pair[1]) for time_pair in LED_Or_Timing]
		eventList += [(time_pair[0], 'led_on', 'UV', time_pair[0]) for time_pair in LED_UV_Timing]
		eventList += [(time_pair[1], 'led_off', 'UV', time_pair[1]) for time_pair in LED_UV_Timing]
		for capture_event in Camera_Capture_Times:
			eventList += [(capture_event[0], 'take_snapshot', capture_event[1], capture_event[2])]
		#TODO: dependency on group number starting at 1 and incrementing by 1
		self.NumGroups = Camera_Capture_Times[-1][2]
		#Now sort by time:
		eventList.sort(key=itemgetter(0))
		self.EventList = eventList
		self.RepeatN = Repeat_N

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

def create_event_list(LED_Blu_Timing, LED_Or_Timing, LED_UV_Timing, Camera_Capture_Times):
	#first take last UV time on to create refactory period:
	uv_time_on = LED_UV_Timing[-1][1]-LED_UV_Timing[-1][0]
	
	#First we create all events (we'll sort later):
	eventList = []
	eventList += [(time_pair[0], 'led_on', 'Blue') for time_pair in LED_Blu_Timing]
	eventList += [(time_pair[1], 'led_off', 'Blue', time_pair[1]) for time_pair in LED_Blu_Timing]
	eventList += [(time_pair[0], 'led_on', 'Orange', time_pair[0]) for time_pair in LED_Or_Timing]
	eventList += [(time_pair[1], 'led_off', 'Orange', time_pair[1]) for time_pair in LED_Or_Timing]
	eventList += [(time_pair[0], 'led_on', 'UV', time_pair[0]) for time_pair in LED_UV_Timing]
	eventList += [(time_pair[1], 'led_off', 'UV', time_pair[1]) for time_pair in LED_UV_Timing]
	for capture_event in Camera_Capture_Times:
		eventList += [(capture_event[0], 'take_snapshot', capture_event[1], capture_event[2])]
	#TODO: dependency on group number starting at 1 and incrementing by 1
	numGrps = Camera_Capture_Times[-1][2]
	#Now sort by time:
	eventList.sort(key=itemgetter(0))
	
	# TODO: add refractory period?
	return eventList, numGrps
	
def performEvent(event, camera, gpio_ctrl, capture_file_name, baseTime=0, repeat_idx=0):
	event_type=event[1]
	if event_type == 'take_snapshot':
		if event[2]:
			if event[3]:
				camera.capture(capture_file_name, cropping=event[2], baseTime=baseTime, group=event[3]+repeat_idx)
			else:
				camera.capture(capture_file_name, cropping=event[2], baseTime=baseTime)
		else:
			if event[3]:
				camera.capture(capture_file_name, group=event[3]+repeat_idx, baseTime=baseTime)			
			else:
				camera.capture(capture_file_name)		
	elif event_type == 'led_off':
		gpio_ctrl.turn_off_led(event[2])
	elif event_type == 'led_on':
		gpio_ctrl.turn_on_led(event[2])
	elif event == 'wait':
		pass
	else:
		#This is impossible to happen, but putting it here just in case
		raise ValueError('Unknown Event Type!')
	
def performEventList(eventList, camera, gpio_ctrl, Repeat_N=0, baseFilename='capture_file_', baseTime=0, numGrps=0):
	saved_capture_idx = camera.file_idx
	for n in range(Repeat_N+1):
		#initial sleep (ie before first listed event
		sleep(eventList[0][0]/1000.)
		#now perform each event (except last, that'll be done later), and if it's a capture, increment saved_capture_idx
		#TODO: cover case of simultaneous events
		for e in range(len(eventList)-1):
			event = eventList[e]
			performEvent(event, camera, gpio_ctrl, baseFilename, baseTime=baseTime, repeat_idx=n*numGrps)
			sleep((eventList[e+1][0]-event[0])/1000.)
		#after for loop, now perform last event:
		performEvent(eventList[-1], camera, gpio_ctrl, baseFilename, baseTime=baseTime, repeat_idx=n*numGrps)
	
def print_eventList(eventList): #for testing
	for event in eventList:
		print(event)
