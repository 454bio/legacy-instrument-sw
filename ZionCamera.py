from typing import Tuple
from fractions import Fraction
from operator import eq, gt
from dataclasses import dataclass,  asdict, fields, is_dataclass
import json
from ZionLED import ZionLEDs, ZionLEDTimings
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
import math
from gi.repository import GLib

MMAL_PARAMETER_ANALOG_GAIN = mmal.MMAL_PARAMETER_GROUP_CAMERA + 0x59
MMAL_PARAMETER_DIGITAL_GAIN = mmal.MMAL_PARAMETER_GROUP_CAMERA + 0x5A

# The loading order is very important to ensure the analog/digital gains
# as well as the awb gains are set to fixed values.
# It's counter-intiuative but we first need exposure_mode to be on auto
# then fix the shutter speed, fix the awb_gains, and iso set to 0
# THEN we can set the analog/digital gains with mmal
# Then we can turn exposure_mode to 'off' to lock them in....
PARAMS_LOAD_ORDER = [
	'brightness',
	'contrast',
	'saturation',
	'sharpness',
	'exposure_compensation',
	'image_denoise',
	'video_denoise',
	'hflip',
	'vflip',
	'shutter_speed',
	'awb_mode',
	'awb_gains',
	'iso',
	'analog_gain',
	'digital_gain',
	'exposure_mode',
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
			elif field.name == "comment":
				if comment:
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
		# from rich import print as rprint

		print(f"\nCamera Initializing...")
		print(f"\tbinning: {binning}")
		print(f"\tinitial_values: {initial_values}")

		if binning:
			resolution = (2028, 1520)
			sensor_mode = 2
		else:
			resolution = (4056, 3040)
			sensor_mode = 3

		clock_mode = 'raw'

		super().__init__(resolution=resolution, framerate = initial_values.framerate, sensor_mode=sensor_mode, clock_mode=clock_mode)
		# from rich import print as rprint
		sleep(1)
		# print("[bold yellow] Properties after init")
		# print(self.get_camera_props(['exposure_mode', 'iso', 'analog_gain', 'digital_gain']))
		# sleep(5)
		# print("[bold yellow] Properties after another sleep(2)")
		# print(self.get_camera_props())

		self.parent = parent
		self.load_params(initial_values)

		print("[bold yellow] Properties after load_params(...)")
		print(self.get_camera_props())

		# Set the max pulse width from the framerate and readout time
		ZionLEDs.set_max_pulsetime(0)#math.floor(1000 / self.framerate))
		#TODO: merging ZionLEDs and ZionLEDTimings may make this unnecessary
		ZionLEDTimings.set_max_pulsetime(math.floor(1000000 / self.framerate))

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

	@property
	def exposure_speed_ms(self):
		return int(self.exposure_speed / 1000)

	@property
	def readout_ms(self):
		# Calculated row readout time by varying fstrobe delay (units are rows)
		# This gave 28.567 usec / row.
		# Using "active" rows (3040 Rows) readout is: 86.8422816
		# Using "effective" rows (3064 Rows) readout is: 87.52787856
		return 86.8422816

	def get_raw_buffer_size(self):
		res_pad = self.resolution.pad(width=32, height=16)
		return res_pad.height * res_pad.width * 2

	def get_all_params(self, comment : str = "") -> ZionCameraParameters:
		return ZionCameraParameters.load_from_camera(self, comment=comment)

	def load_params(self, params_in : ZionCameraParameters):
		for param in PARAMS_LOAD_ORDER:
			if param == 'awb_gains':
				print(f"Setting {param} to {(params_in.red_gain, params_in.blue_gain)}")
				self.awb_gains = (params_in.red_gain, params_in.blue_gain)
			elif param == 'analog_gain':
				print(f"Setting {param} to {getattr(params_in, param)}")
				if params_in.analog_gain > 0:
					self.set_analog_gain(params_in.analog_gain)
				else:
					print(f"Skipping setting analog_gain of {params_in.analog_gain} since it's <= 0")
			elif param == 'digital_gain':
				print(f"Setting {param} to {getattr(params_in, param)}")
				if params_in.digital_gain > 0:
					self.set_digital_gain(params_in.digital_gain)
				else:
					print(f"Skipping setting digital_gain of {params_in.digital_gain} since it's <= 0")
			elif param == 'exposure_mode':
				# Wait a maximum of 5 seconds for all the values to take a hold, to be sure the gains are correct before fixing them in place
				sleep(1)
				for _ in range(5):
					settings_ok = True
					if self.analog_gain != params_in.analog_gain:
						print(f"WARNING: Analog gain does not match expected value!  expected: {params_in.analog_gain}  actual: {self.analog_gain}")
						settings_ok = False

					if self.digital_gain != params_in.digital_gain:
						print(f"WARNING: Digital gain does not match expected value!  expected: {params_in.digital_gain}  actual: {self.digital_gain}")
						settings_ok = False

					expected_awb_gains = (Fraction(params_in.red_gain), Fraction(params_in.blue_gain))
					if self.awb_gains != expected_awb_gains:
						print(f"WARNING: AWB gains do not match expected values!  expected: {expected_awb_gains}  actual: {self.awb_gains}")
						settings_ok = False

					if settings_ok:
						break

					print("Sleeping another two second for settings to propogate...")
					sleep(2)

				if not settings_ok:
					# By skipping the `exposure_mode` settings if we failed, then we will pop a error to the user
					print("ERROR: Setting the camera settings failed!!!")
				else:
					self.exposure_mode = params_in.exposure_mode
			else:
				print(f"Setting {param} to {getattr(params_in, param)}")
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

	def capture(self, filename, cropping=(0,0,1,1), bayer=True, splitter=0):
		self.zoom = cropping
		fileToWrite = filename+'.jpg'
		# ~ fileToWrite = filename+'.raw'
		if self.parent:
			self.parent.GPIO.camera_trigger()
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
			GLib.idle_add(self.parent.update_last_capture)

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

		print(f"Actual exposure time: {self.exposure_speed / 1000:.3f} ms")
		print(f"shutter_speed: {self.shutter_speed}")

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
		print("!!!!!!!!!!! ENTERED SET_FRAMERATE !!!!!!!!!!!!")
		# if val>0:
		# 	# ~ self.exposure_mode = 'auto'
		# 	if self.sensor_mode==2:
		# 		if val<=42 and val>=0.1:
		# 			self.exposure_mode='auto'
		# 			self.framerate = val
		# 			time.sleep(1)
		# 			self.exposure_mode = 'off'
		# 		else:
		# 			print('\nWith binning on, framerate must be between 0.1 and 42!')
		# 	elif self.sensor_mode==3:
		# 		if val<=10 and val>=0.05:
		# 			self.exposure_mode = 'auto'
		# 			self.framerate = val
		# 			time.sleep(1)
		# 			self.exposure_mode = 'off'
		# 		else:
		# 			print('\nWith binning off, framerate must be between 0.05 and 10!')
		# else:
		# 	if self.sensor_mode==2:
		# 		self.framerate_range = (0.1, 42)
		# 		# ~ self.exposure_mode = 'auto'
		# 		time.sleep(3)
		# 		self.exposure_mode = 'off'
		# 	elif self.sensor_mode==3:
		# 		self.framerate_range = (0.05, 10)
		# 		# ~ self.exposure_mode = 'auto'
		# 		time.sleep(3)
		# 		self.exposure_mode = 'off'

	def start_preview(self, fullscreen=False, window=(560,75,640,480)):
		super(ZionCamera,self).start_preview(fullscreen=False, window=window)

	def get_camera_props(self, props=PARAMS_LOAD_ORDER):
		print(f"getting properities {props}")
		props_ret = {}
		for k in filter(lambda x: not x.startswith('_'), dir(self)):
			if props and not (k in props):
				continue
			try:
				if not callable(getattr(self, k)):
					props_ret[k] = getattr(self, k)
				else:
					print(f"Skipping {k} due to being a method")
			except:
				print(f"Could not get property {k}")
		return props_ret

#TODO: link cropping with bounding box UI input
