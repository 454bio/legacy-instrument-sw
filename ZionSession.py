import os
import time
from operator import itemgetter
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
import keyboard
from ZionCamera import ZionCamera
from ZionGPIO import ZionGPIO
from ZionEvents import check_led_timings, create_event_list, performEventList
from ZionGtk import ZionGUI


class ZionSession(object): #TODO: inherit from some UI/app session class type

	def __init__(self, session_name, Spatial_Res, Frame_Rate, Binning, Blue_Timing, Orange_Timing, UV_Timing, Camera_Captures, RepeatN=0, overwrite=False):
		
		self.Name = session_name
		if not os.path.exists('./'+session_name):
			os.mkdir('./'+session_name)
			self.Dir = './'+session_name
		else:
			if os.path.isdir('./'+session_name):
				self.Dir = './'+session_name
			else:
				#file exists but not a directory...
				raise ValueError('File '+session_name+' already exists but is not a session folder!')		
				

			
		# Shutter Speed = Exposure Time (in microseconds)
		# ~ Shutter_Speed = round(1000./Frame_Rate)  #(0 is automatic) 
		# ~ Shutter_Speed = round(1000000./Frame_Rate)
		Shutter_Speed = 0
		Shutter_Speed_Stepsize = 2000
		Shutter_Speed_Max = 200000000
		# Minimum is 1/Frame_Rate
		# TODO: right now manual shutter speed can't be changed from 1/FR
		
		
		
		check_led_timings(Blue_Timing, Orange_Timing, UV_Timing)
		self.EventList, self.NumGrps = create_event_list(Blue_Timing, Orange_Timing, UV_Timing, Camera_Captures)
		self.RepeatN = RepeatN
		self.GPIO = ZionGPIO()
		self.Camera = ZionCamera(Spatial_Res, Frame_Rate, Binning, Shutter_Speed, Shutter_Speed_Stepsize, Shutter_Speed_Max, gpio_ctrl=self.GPIO)
		self.TimeOfLife = time.time()

		self.gui = ZionGUI(self.Camera, 'night')
		

	def RunProgram(self):
		performEventList(self.EventList, self.Camera, self.GPIO, Repeat_N=self.RepeatN, baseFilename=(self.Dir, self.Name), baseTime=self.TimeOfLife, numGrps=self.NumGrps)
		
	#TODO: move interactive preview here:
	def InteractivePreview(self, window):
		# ~ self.Camera.interactive_preview(baseFilename=(self.Dir, self.Name), window=window, baseTime=self.TimeOfLife)
		self.Camera.start_preview(fullscreen=False, window=window)
		Gtk.main()
		self.Camera.stop_preview()

	def QuitSession(self):
		self.GPIO.turn_off_led('all')
		self.Camera.quit()
