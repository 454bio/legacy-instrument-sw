from typing import Tuple
from fractions import Fraction
from operator import eq, gt
from dataclasses import dataclass,  asdict, fields, is_dataclass
import json
from picamera import PiCamera, PiRenderer, mmal, mmalobj, exc
from picamera.array import PiRGBArray
from picamera.mmalobj import to_rational
import pigpio
import keyboard
import numpy as np
from io import BytesIO
from PIL import Image
from time import sleep
import time
import os
from gi.repository import GLib

MMAL_PARAMETER_ANALOG_GAIN = mmal.MMAL_PARAMETER_GROUP_CAMERA + 0x59
MMAL_PARAMETER_DIGITAL_GAIN = mmal.MMAL_PARAMETER_GROUP_CAMERA + 0x5A

# The loading order is very important to ensure the analog/digital gains
# as well as the awb gains are set to fixed values.
PARAMS_LOAD_ORDER = [
	'brightness',
	'contrast',
	'saturation',
	'sharpness',
	'exposure_compensation',
	'hflip',
	'vflip',
	'iso',
	'analog_gain',
	'digital_gain',
	'shutter_speed',
	'exposure_mode',
	'awb_mode',
	'awb_gains',
	'image_denoise',
	'video_denoise',
]

class ZionCameraParametersEncoder(json.JSONEncoder):
    def default(self, obj):
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, Fraction):
            return float(obj)
        return json.JSONEncoder.default(self, obj)

@dataclass
class ZionCameraParameters:
	brightness: int = 50            # 0 <-> 100
	contrast: int = 0               # -100 <-> 100
	saturation: int = 0             # -100 <-> 100
	sharpness: int = 0              # -100 <-> 100
	awb_mode: str = 'off'           # ['off', 'auto', 'sunlight', 'cloudy', 'shade', 'tungsten', 'fluorescent', 'incandescent', 'flash', 'horizon']
	red_gain: float = 1.0           # 0.0 <-> 8.0
	blue_gain: float = 1.0          # 0.0 <-> 8.0
	exposure_mode: str = 'off'      # ['off', 'auto', 'night', 'nightpreview', 'backlight', 'spotlight', 'sports', 'snow', 'beach', 'verylong', 'fixedfps', 'antishake', 'fireworks']
	exposure_speed: int = 250000    # This is a read-only property of picamera
	shutter_speed: int = 250000     # Microseconds (0 is auto)
	exposure_compensation: int = 0  # -25 <-> 25
	iso: int = 0                    # 0 <-> 1600
	image_denoise: bool = False
	video_denoise: bool = False
	analog_gain: float = 8.0        # max is 16
	digital_gain: float = 1.0       # unity gain for avoiding quantization error
	framerate: float = 4.0          # min 0.1 max 42 if binning, else min 0.05 max 10
	vflip: bool = True
	hflip: bool = False
	comment: str = ""

	def is_fixed_capture(self):
		""" Routine to return if the parameters correspond with
			non-auto adjusting gains and exposures """
		return (
			self.awb_mode == 'off' and
			self.exposure_mode == 'off' and
			self.shutter_speed > 0 and
			self.iso == 0
		)

	@classmethod
	def load_from_camera(cls, camera : 'ZionCamera', comment : str = "") -> 'ZionCameraParameters':
		p = cls()
		for field in fields(p):
			if field.name == "red_gain":
				p.red_gain = camera.awb_gains[0]
			elif field.name == "blue_gain":
				p.blue_gain = camera.awb_gains[1]
			elif field.name == "comment" and comment:
				p.comment = str(comment)
			else:
				setattr(p, field.name, field.type(getattr(camera, field.name)))

		return p

	@classmethod
	def load_from_file(cls, filename: dict) -> 'ZionCameraParameters':
		with open(filename) as f:
			json_dict = json.load(f)
		return cls(**json_dict)

	def to_dict(self):
		return asdict(self)

	def save_to_file(self, filename: str):
		if not filename.endswith(".txt"):
			filename += ".txt"

		with open(filename, "w") as f:
			json.dump(self, f, indent=1, cls=ZionCameraParametersEncoder)


class ZionCamera(PiCamera):

	def __init__(self, binning : bool, initial_values : ZionCameraParameters, parent : 'ZionSession' = None):

		print('\nCamera Initializing...')

		if binning:
			resolution = (2028, 1520)
			sensor_mode = 2
		else:
			resolution = (4056, 3040)
			sensor_mode = 3

		super().__init__(resolution=resolution, framerate = initial_values.framerate, sensor_mode=sensor_mode)
		self.parent = parent

		self.load_params(initial_values)
		# self.vflip = True

		# self.image_denoise = False
		# self.video_denoise = False
		# self.brightness = initial_values['brightness']
		# self.contrast = initial_values['contrast']
		# self.saturation = initial_values['saturation']
		# self.sharpness = initial_values['sharpness']
		# self.awb_mode = initial_values['awb']
		# self.awb_gains = (initial_values['red_gain'], initial_values['blue_gain'])
		# self.exposure_mode = 'auto'
		# self.shutter_speed = initial_values['exposure_time']*1000
		# self.iso = 0
		# self.set_analog_gain(initial_values['a_gain'])
		# self.set_digital_gain(initial_values['d_gain'])
		# self.shutter_speed = initial_values['exposure_time']*1000
		# time.sleep(2)
		# self.exposure_mode = 'off'
		# time.sleep(2)

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

	def get_all_params(self, comment : str = "") -> ZionCameraParameters:
		return ZionCameraParameters.load_from_camera(self, comment=comment)

	def load_params(self, params_in : ZionCameraParameters):
		for param in PARAMS_LOAD_ORDER:
			if param == 'awb_gains':
				self.awb_gains = (params_in.red_gain, params_in.blue_gain)
			elif param == 'analog_gain':
				self.set_analog_gain(params_in.analog_gain)
			elif param == 'digital_gain':
				self.set_digital_gain(params_in.digital_gain)
			else:
				setattr(self, param, getattr(params_in, param))

	def is_fixed_capture(self) -> Tuple[bool, dict]:
		""" Routine to return if the parameters correspond with
			non-auto adjusting gains and exposures """

		# Comparison func, Param name, Good value
		fixed_capture_params = (
			(eq, "awb_mode", 'off'),
			(eq, "exposure_mode", 'off'),
			(gt, "shutter_speed", 0),
			(eq, "iso", 0),
		)

		nonfixed_capture_params = {}
		for (comp_func, param_name, good_value) in fixed_capture_params:
			cur_value = getattr(self, param_name)
			if not comp_func(cur_value, good_value):
				nonfixed_capture_params[param_name] = cur_value

		return (not nonfixed_capture_params, nonfixed_capture_params)

	def capture(self, filename, cropping=(0,0,1,1), bayer=False, splitter=0):
		self.zoom = cropping
		fileToWrite = filename+'.jpg'
		# ~ fileToWrite = filename+'.raw'
		if self.parent:
			self.parent.GPIO.camera_trigger(True)
		if bayer:
			print('\nWriting image to file '+fileToWrite)
			# ret = super(ZionCamera,self).capture(fileToWrite, use_video_port=False)
			ret = super(ZionCamera,self).capture(fileToWrite, use_video_port=False, bayer=True)
		else:
			# fstrobe doesn't fire when using the video port
			print('\nWriting image to file '+fileToWrite+', using splitter port '+str(splitter))
			# ~ print('\nWriting image to file '+fileToWrite)
			ret = super(ZionCamera,self).capture(fileToWrite, use_video_port=True, splitter_port=splitter)
			# ~ ret = super(ZionCamera,self).capture_sequence([fileToWrite], use_video_port=True, splitter_port=splitter)
			# ~ ret = super(ZionCamera,self).capture_sequence([fileToWrite], use_video_port=False, bayer=False, burst=True)

		if self.parent:
			self.parent.GPIO.camera_trigger(False)
			GLib.idle_add(self.parent.update_last_capture, fileToWrite)

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
