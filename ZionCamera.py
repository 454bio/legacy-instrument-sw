from picamera import PiCamera, PiRenderer
import pigpio
import keyboard
# ~ from operator import itemgetter
from PIL import Image as PIL_Image
from time import sleep
import time
import os

class ZionCamera(PiCamera):

	def __init__(self, framerate, binning, initial_values, parent=None):

		print('\nCamera Initializing...')
		
		if binning:
			resolution = (2028, 1520)
			sensor_mode = 2
			framerate_range = (0.1, 42)
		else:
			resolution = (4056, 3040)
			sensor_mode = 3
			framerate_range = (0.05, 10)
		
		super(ZionCamera,self).__init__(resolution=resolution, framerate=framerate, sensor_mode=sensor_mode)
		self.parent = parent
		self.framerate_range = framerate_range
		
		self.image_denoise = False
		self.brightness = initial_values['brightness']
		self.contrast = initial_values['contrast']
		self.saturation = initial_values['saturation']
		self.sharpness = initial_values['sharpness']
		self.awb_mode = initial_values['awb']
		self.awb_gains = (initial_values['red_gain'], initial_values['blue_gain'])
		self.exposure_mode = initial_values['exposure_mode']
		self.exposure_time = initial_values['exposure_time']

		print('\nCamera Ready')

	def quit(self):
		self.stop_preview()
		self.close()
		print('\nCamera Closed')
		
	def capture(self, filename, cropping=(0,0,1,1), use_video_port=False):
		self.zoom = cropping
		fileToWrite = filename+'.jpg'
		# ~ fileToWrite = filename+'.raw'
		print('\nWriting image to file '+fileToWrite)
		if self.parent:
			self.parent.GPIO.camera_trigger(True)
		ret = super(ZionCamera,self).capture(fileToWrite, use_video_port=use_video_port)
		if self.parent:
			self.parent.GPIO.camera_trigger(False)
		self.zoom=(0,0,1,1)
		return ret

	def set_image_denoising(self, bOn):
		if not bOn:
			self.image_denoising = False
			print('\nTurning denoising off')
		else:
			self.image_denoising = True
			print('\nTurning denoising on')

	def set_brightness(self, val):
		self.brightness = val
		print('\nSetting brightness to '+str(val))

	def set_contrast(self, val):
		self.contrast = val
		print('\nSetting contrast to '+str(val))

	def set_saturation(self, val):
		self.saturation = val
		print('\nSetting saturation to '+str(val))

	def set_sharpness(self, val):
		self.sharpness = val
		print('\nSetting sharpness to '+str(val))

	def set_iso(self, val):
		self.iso = val
		print('\nSetting ISO to '+str(val))
		
	def set_exp_comp(self, val):
		self.exposure_compensation = val
		print('\nSetting exposure compensation to '+str(val))
		
	def set_shutter_speed(self, val):
		self.shutter_speed = val
		if val==0:
			print('\nSetting exposure time to auto')
		else:
			print('\nSetting exposure time to '+str(val))
			
	def set_exp_mode(self, val):
		self.exposure_mode = val
		print('\nSetting exposure mode to '+str(val))
		
	def toggle_awb(self):
		if self.awb_mode == 'off':
			self.awb_mode = 'auto'
			print('\nAuto White Balance on')
			ret = (1,0,0)
		elif self.awb_mode == 'auto':
			awb_gains = self.awb_gains
			self.awb_mode = 'off'
			print('\nAuto White Balance off')
			self.awb_gains=awb_gains
			print('\nWhite balance gains are: RED='+str(float(self.awb_gains[0]))+', BLUE='+str(float(self.awb_gains[1])))
			ret = (0,)+awb_gains
		return ret

	def set_red_gain(self, val):
		awb_gains = self.awb_gains
		self.awb_gains = (val, awb_gains[1])
		print('\nSetting AWB red gain to '+str(val))

	def set_blue_gain(self, val):
		awb_gains = self.awb_gains
		self.awb_gains = (awb_gains[0], val)
		print('\nSetting AWB blue gain to '+str(val))

#TODO: link cropping with bounding box UI input
