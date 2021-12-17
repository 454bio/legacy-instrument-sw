from picamera import PiCamera, PiRenderer, mmal, mmalobj, exc
from picamera.array import PiRGBArray
from picamera.mmalobj import to_rational
import pigpio
import numpy as np
from io import BytesIO
from PIL import Image
from time import sleep
import time
import os

MMAL_PARAMETER_ANALOG_GAIN = mmal.MMAL_PARAMETER_GROUP_CAMERA + 0x59
MMAL_PARAMETER_DIGITAL_GAIN = mmal.MMAL_PARAMETER_GROUP_CAMERA + 0x5A

class ZionCamera(PiCamera):

	def __init__(self, binning, initial_values, parent=None):

		print('\nCamera Initializing...')
		
		if binning:
			resolution = (2028, 1520)
			sensor_mode = 2
			# ~ framerate_range = (0.1, 42)
		else:
			resolution = (4056, 3040)
			sensor_mode = 3
			# ~ framerate_range = (0.05, 10)
		framerate_range = (0.05, 10)
		
		super(ZionCamera,self).__init__(resolution=resolution, framerate = initial_values['framerate'], sensor_mode=sensor_mode)
		self.parent = parent
		# ~ self.framerate_range = framerate_range
		
		self.vflip = True
		
		self.image_denoise = False
		self.brightness = initial_values['brightness']
		self.contrast = initial_values['contrast']
		self.saturation = initial_values['saturation']
		self.sharpness = initial_values['sharpness']
		self.awb_mode = initial_values['awb']
		self.awb_gains = (initial_values['red_gain'], initial_values['blue_gain'])
		self.exposure_mode = 'auto'
		self.shutter_speed = initial_values['exposure_time']*1000
		self.iso = 0
		self.set_analog_gain(initial_values['a_gain'])
		self.set_digital_gain(initial_values['d_gain'])
		self.shutter_speed = initial_values['exposure_time']*1000
		time.sleep(2)
		self.exposure_mode = 'off'
		time.sleep(2)

		# TODO: check for zero for Jose
		
		# TODO: when getting bayer data, need to account for vflip we introduced
		# ~ stream = BytesIO()
		# ~ super(ZionCamera,self).capture(stream, format='jpeg', bayer=True)
		# ~ data = stream.getvalue()[-18711040:]
		# ~ data = data[32768:]
		# ~ data = np.fromstring(data, dtype=np.uint8)
		# ~ data = data.reshape((3056, 6112))[:3040, :6084].astype(np.uint16)
		# ~ img = np.zeros((3040, 4056), dtype=np.uint16)
		# ~ for byte in range(2):
			# ~ img[:,byte::2] = (data[:,byte::3] << 4) | ( (data[:,2::3]>>(byte*4)) & 0b1111)
		# ~ data = img
		# ~ self.center_pixel_value = data[1520, 2048]
	
		print('\nCamera Ready')

	def quit(self):
		self.stop_preview()
		self.close()
		print('\nCamera Closed')
		
	def get_all_params(self):
		params_list = {
			
			'brightness':    self.brightness,
			'contrast':      self.contrast,
			'saturation':    self.saturation,
			'sharpness':     self.sharpness,
			'awb':           self.awb_mode,
			'red_gain':      float(self.awb_gains[0]),
			'blue_gain':     float(self.awb_gains[1]),
			'exposure_mode': self.exposure_mode,
			'exposure_time': self.exposure_speed,
			'shutter_time':  self.shutter_speed,
			
			'exposure_comp': self.exposure_compensation,
			'ISO':			 self.iso,
			'denoise':		 self.image_denoise,
			
			'a_gain':   	 float(self.analog_gain),
			'd_gain':    	 float(self.digital_gain),
			
			'framerate':     float(self.framerate)
		}
		return params_list
		
	def load_params(self, params):
		for key in params.keys():
			if key=='brightness':
				self.brightness = params[key]
			elif key=='contrast':
				self.contrast = params[key]
			elif key=='saturation':
				self.saturation = params[key]
			elif key=='sharpness':
				self.sharpness = params[key]
			elif key=='awb':
				self.awb_mode = params[key]
			elif key=='red_gain':
				self.set_red_gain(params[key])
				sleep(0.25)
				# ~ self.awb_gains =  (params[key], self.awb_gains[1])
			elif key=='blue_gain':
				self.set_blue_gain(params[key])
				sleep(0.25)
				# ~ self.awb_gains = (self.awb_gains[0], params[key])
			# ~ elif key=='exposure_mode':
				# ~ self.exposure_mode = params[key]
			elif key=='shutter_time':
				self.shutter_speed = params[key]
			elif key=='ISO':
				self.iso = params[key]
			elif key=='exposure_comp':
				self.exposure_compensation = params[key]
			elif key=='denoise':
				self.image_denoise = params[key]
			elif key=='a_gain':
				self.set_analog_gain(params[key])
			elif key=='d_gain':
				self.set_digital_gain(params[key])
			elif key=='framerate':
				self.set_framerate(params[key])
			else:
				pass

	def capture(self, filename, cropping=(0,0,1,1), bayer=False, splitter=0):
		self.zoom = cropping
		fileToWrite = filename+'.jpg'
		# ~ fileToWrite = filename+'.raw'
		if self.parent:
			self.parent.GPIO.camera_trigger(True)
		if bayer:
			print('\nWriting image to file '+fileToWrite)
			ret = super(ZionCamera,self).capture(fileToWrite, use_video_port=False, bayer=True)
		else:
			print('\nWriting image to file '+fileToWrite+', using splitter port '+str(splitter))
			# ~ print('\nWriting image to file '+fileToWrite)
			ret = super(ZionCamera,self).capture(fileToWrite, use_video_port=True, splitter_port=splitter)
			# ~ ret = super(ZionCamera,self).capture_sequence([fileToWrite], use_video_port=True, splitter_port=splitter)
			# ~ ret = super(ZionCamera,self).capture_sequence([fileToWrite], use_video_port=False, bayer=False, burst=True)
		if self.parent:
			self.parent.GPIO.camera_trigger(False)
		self.zoom=(0,0,1,1)
		return ret

	def stream_preview(self):
		stream = BytesIO()
		#quality is 1 to 40, 20-25 recommended
		super(ZionCamera, self).start_recording(stream, format='h264', quality=23)
		super(ZionCamera, self).wait_recording(15)
		super(ZionCamera, self).stop_recording()
		stream.seek(0)
		image = Image.open(stream)
		#use capture_sequence()

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

	def set_gain(self, gain, val):
		if gain not in [MMAL_PARAMETER_ANALOG_GAIN, MMAL_PARAMETER_DIGITAL_GAIN]:
			raise ValueError("The gain parameter was not valid")
		ret = mmal.mmal_port_parameter_set_rational(self._camera.control._port, gain, to_rational(val))
		if ret == 4:
			raise exc.PiCameraMMALError(ret, "Are you running the latest version of the userland libraries? Gain setting was introduced in late 2017.")
		elif ret != 0:
			raise exc.PiCameraMMALError(ret)

	def set_analog_gain(self, val):
		self.set_gain(MMAL_PARAMETER_ANALOG_GAIN, val)
	
	def set_digital_gain(self, val):
		self.set_gain(MMAL_PARAMETER_DIGITAL_GAIN, val)
		
	def set_framerate(self, val):
		if val>0:
			# ~ self.exposure_mode = 'auto'
			if self.sensor_mode==2:
				if val<=42 and val>=0.1:
					self.exposure_mode='auto'
					self.framerate = val
					time.sleep(1)
					self.exposure_mode = 'off'
				else:
					print('\nWith binning on, framerate must be between 0.1 and 42!')
			elif self.sensor_mode==3:
				if val<=10 and val>=0.05:
					self.exposure_mode = 'auto'
					self.framerate = val
					time.sleep(1)
					self.exposure_mode = 'off'
				else:
					print('\nWith binning off, framerate must be between 0.05 and 10!')
		else:
			if self.sensor_mode==2:
				self.framerate_range = (0.1, 42)
				# ~ self.exposure_mode = 'auto'
				time.sleep(3)
				self.exposure_mode = 'off'
			elif self.sensor_mode==3:
				self.framerate_range = (0.05, 10)
				# ~ self.exposure_mode = 'auto'
				time.sleep(3)
				self.exposure_mode = 'off'

	def start_preview(self, fullscreen=False, window=(560,75,640,480)):
		super(ZionCamera,self).start_preview(fullscreen=False, window=window)

#TODO: link cropping with bounding box UI input
