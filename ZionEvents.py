from time import sleep
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
						event_type = event_params[1].strip('\'')
						event += (int(event_params[0]), event_type, event_params[2].strip('\''))
						if event_type=='LED':
							event += (int(event_params[3]),)
						elif event_type=='Capture':
							#TODO: read back capture tuples
							event += (None,)
						eventList.append(event)
			self.N = N
			eventList.sort(key=itemgetter(0))
			self.Events = eventList
			self.capture_threads = []
		else:
			self.N = 0
			self.Events = []
			self.capture_threads = []

	def performEvent(self, event, camera, gpio_ctrl, repeat_idx=0):
		event_type=event[1]
		if event_type == 'Capture':
			if event[3]:
				if event[2]:
					kwargs = {'cropping':event[3], 'group':event[2], 'verbose':True}
					# ~ camera.parent.CaptureImage(cropping=event[2], group=event[3], verbose=True)
				else:
					kwargs = {'cropping':event[3], 'verbose':True}
					# ~ camera.parent.CaptureImage(cropping=event[2], verbose=True)
			else:
				if event[2]:
					kwargs = {'group':event[2], 'verbose':True}
					# ~ camera.parent.CaptureImage(group=event[3], verbose=True)
				else:
					kwargs = {'verbose':True}
					# ~ camera.parent.CaptureImage(verbose=True)
			# ~ self.capture_threads.append( threading.Thread(target=camera.parent.CaptureImage, kwargs=kwargs) )
			# ~ self.capture_threads[-1].daemon = True
			# ~ self.capture_threads[-1].start()
			capture_thread = threading.Thread(target=camera.parent.CaptureImage, kwargs=kwargs)
			capture_thread.daemon = True
			capture_thread.start()
		elif event_type == 'LED':
			gpio_ctrl.enable_led(event[2], event[3], verbose=True)
		elif event == 'Wait':
			pass
		else:
			#This is impossible to happen, but putting it here just in case
			raise ValueError('Unknown Event Type!')

	def performEventList(self, camera, gpio_ctrl, Repeat_N=0, baseFilename='capture_file_', baseTime=0, numGrps=0):
		eventList = self.Events
		saved_capture_idx = camera.file_idx
		for n in range(Repeat_N+1):
			#initial sleep (ie before first listed event
			sleep(eventList[0][0]/1000.)
			#now perform each event (except last, that'll be done later), and if it's a capture, increment saved_capture_idx
			#TODO: cover case of simultaneous events
			for e in range(len(eventList)-1):
				event = eventList[e]
				self.performEvent(event, camera, gpio_ctrl, baseFilename, baseTime=baseTime, repeat_idx=n*numGrps)
				sleep((eventList[e+1][0]-event[0])/1000.)
			#after for loop, now perform last event:
			self.performEvent(eventList[-1], camera, gpio_ctrl, baseFilename, baseTime=baseTime, repeat_idx=n*numGrps)

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
