from typing import Tuple
from fractions import Fraction
from operator import eq, gt
from dataclasses import dataclass, asdict, fields, is_dataclass
import json
from ZionLED import ZionLEDs, ZionLEDTimings

#from picamera import PiCamera, PiRenderer, mmal, mmalobj, exc
#from picamera.array import PiRGBArray
#from picamera.mmalobj import to_rational

from picamera2 import Picamera2, Preview
import libcamera
from libcamera import Transform, controls

import pigpio
import numpy as np
from io import BytesIO
from PIL import Image
from time import sleep
import time
import os
import math
from gi.repository import GLib

#shouldn't need this anymore
#MMAL_PARAMETER_ANALOG_GAIN = mmal.MMAL_PARAMETER_GROUP_CAMERA + 0x59
#MMAL_PARAMETER_DIGITAL_GAIN = mmal.MMAL_PARAMETER_GROUP_CAMERA + 0x5A

# The loading order is very important to ensure the analog/digital gains
# as well as the awb gains are set to fixed values.
# It's counter-intiuative but we first need exposure_mode to be on auto
# then fix the shutter speed, fix the awb_gains, and iso set to 0
# THEN we can set the analog/digital gains with mmal
# Then we can turn exposure_mode to 'off' to lock them in....
PARAMS_LOAD_ORDER = [
	'NoiseReductionMode',
	'Brightness',
	'Contrast',
	'Saturation',
	'Sharpness',
	'AeExposureMode',
	'AeMeteringMode',
	'AeConstraintMode',
	'AeEnable',
	'ExposureValue',
	'ExposureTime',
	'AnalogueGain',
	'AwbMode',
	'AwbEnable',
	'ColourGains',
	#'ScalerCrop',
]
CONTROLS_WRITE_ORDER = [
	'Brightness',
	'Contrast',
	'Saturation',
	'Sharpness',
	'ExposureValue',
	'ExposureTime',
	'AnalogueGain',
	'ColourGains',
	'FrameRate',
	#'ScalerCrop',
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
	
	#todo: move this somewhere else?
	FrameRate: float = 1.0          # min 0.1 max 42 if binning, else min 0.05 max 10
	
	Brightness: float = 0.0			# -1.0 <-> 1.0
	Contrast: float = 1.0			# 0.0 <-> 32.0
	Saturation: float = 1.0         # 0.0 <-> 32.0
	Sharpness: float = 1.0          # 0.0 <-> 16.0
	
	AeExposureMode: controls.AeExposureModeEnum = controls.AeExposureModeEnum.Normal
	AeConstraintMode: controls.AeConstraintModeEnum = controls.AeConstraintModeEnum.Normal
	AeMeteringMode: controls.AeMeteringModeEnum = controls.AeMeteringModeEnum.Spot
	AeEnable: bool = False			#Auto-exposure / auto-gain
	ExposureValue: float = 0.0  	# -8.0 <-> 8.0 This is exposure "compensation"
	ExposureTime: int = 250000		# Microseconds
	
	AnalogueGain: float = 8.0       # max is 16? (or twenty something?)
	#DigitalGain: float = 1.0        # unity gain for avoiding quantization error
	
	AwbMode: controls.AwbModeEnum = controls.AwbModeEnum.Auto	
	AwbEnable: bool = False			#Awb affects color gains
	RedGain: float = 2.0			# 0.0 <-> 32.0
	BlueGain: float = 2.0			# 0.0 <-> 32.0

	NoiseReductionMode: controls.draft.NoiseReductionModeEnum = controls.draft.NoiseReductionModeEnum.Off
	
	#todo: add digital crop if necessary
	#ScalerCrop: libcamera.Rectangle = (x_offset, y_offset, width, height) 

	#Todo: move following to Transform for preview and _____ for stream/capture
	vflip: bool = True
	hflip: bool = False

	comment: str = ""

	def is_fixed_capture(self):
		""" Routine to return if the parameters correspond with
			non-auto adjusting gains and exposures """		
		return (
			not self.AwbEnable and
			not self.AeEnable
		)

	@classmethod
	def load_from_camera(cls, camera : 'ZionCamera', comment : str = "") -> 'ZionCameraParameters':
		p = cls()
		#TODO: ensure camera is running first
		metadata = camera.capture_metadata()
		for field in fields(p):
			if field.name == "RedGain":
				p.RedGain = metadata["ColourGains"][0]
			elif field.name == "BlueGain":
				p.BlueGain = metadata["ColourGains"][1]
			elif field.name == "comment":
				if comment:
					p.comment = str(comment)
			else:
				#TODO: update this to access metadata dictionary keys, vals instead
				setattr(p, field.name, field.type(getattr(camera, field.name)))
		return p

	@classmethod
	def load_from_file(cls, filename: dict) -> 'ZionCameraParameters':
		with open(filename) as f:
			json_dict = json.load(f)
		return cls(**json_dict)

	def to_dict(self):
		return asdict(self)
		
	def to_config_dicts(self):
		d_controls = dict()
		d_config = self.to_dict()
		transform = Transform(hflip = self.hflip, vflip = self.vflip)
		del(d_config['hflip'])
		del(d_config['vflip'])
		for param in CONTROLS_WRITE_ORDER:
			if param == "ColourGains":
				d_controls["ColourGains"] = (self.RedGain, self.BlueGain)
				del(d_config["RedGain"])
				del(d_config["BlueGain"])
			else:
				d_controls[param] = getattr(self, param)
				del(d_config[param])
		#print(f"\ncontrols = {d_controls}\nconfig = {d_config}")
		return d_config, transform, d_controls

	def save_to_file(self, filename: str):
		if not filename.endswith(".txt"):
			filename += ".txt"

		with open(filename, "w") as f:
			json.dump(self, f, indent=1, cls=ZionCameraParametersEncoder)


class ZionCamera(Picamera2):

	def __init__(self, binning : bool, initial_values : ZionCameraParameters, parent : 'ZionSession' = None):
		# from rich import print as rprint

		print(f"\nCamera Initializing...")
		print(f"\tbinning: {binning}")
		print(f"\tinitial_values: {initial_values}")
		
		# Split camera setup into configuration and controls:
		
		# Set up Configuration:
		
		self.ConfigDict, self.transform, self.ControlsDict = initial_values.to_config_dicts()
		
		#TODO: Change for different camera (eg e-con, arducam, etc) - only valid for imx477!
		if binning:
			resolution = (2028, 1520)
			sensor_mode = 2
		else:
			resolution = (4056, 3040)
			sensor_mode = 3
		
		self.framerate = initial_values.FrameRate
		frameduration = int(1000000/initial_values.FrameRate)
		
		
		clock_mode = 'raw'
		#super().__init__(resolution=resolution, framerate = initial_values.framerate, sensor_mode=sensor_mode, clock_mode=clock_mode)
		
		super().__init__()
		
		#TODO: choose XBGR8888 or BGR888 (affects choice of preview)
		#TODO: change the way sensor mode is chosen based on actual camera
		#self.config = super().create_preview_configuration({"size": resolution, "format": "BGR888"}, buffer_count=2, transform=self.transform, controls=controls_obj, raw=super().sensor_modes[sensor_mode])
		print(f"\nAvailable Sensor Modes: {self.sensor_modes}")
		self.config = self.create_zion_configuration({"size": resolution, "format": "BGR888"}, buffer_count=3, transform=self.transform, controls=self.ControlsDict, raw=super().sensor_modes[sensor_mode])
		#self.config = super().create_preview_configuration({"size": resolution, "format": "BGR888"}, buffer_count=3, transform=Transform(hflip = initial_values.hflip, vflip = initial_values.vflip), controls=controls_obj, raw=super().sensor_modes[sensor_mode])
		print(f"\nConfiguration = {self.config}")
		super().configure(self.config)
		
		self.parent = parent
		
		super().start()
		sleep(5)
		
		#print(self.camera_controls)
		#print(f"Controls = {self.controls}")
		metadata = self.capture_metadata()
		print(f"\nInitial Metadata = {self.capture_metadata()}")
		self.exposure_speed = metadata["ExposureTime"]
		self.analog_gain = metadata["AnalogueGain"]
		self.digital_gain = metadata["DigitalGain"]
		
		#self.load_params(initial_values)
		#print(self.capture_metadata())

		#print("[bold yellow] Properties after load_params(...)")
		#print(self.get_camera_props())

		# Set the max pulse width from the framerate and readout time
		ZionLEDs.set_max_pulsetime(math.floor(1000 / self.framerate))
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
		
	def create_zion_configuration(self, main={}, lores=None, raw=None, transform=libcamera.Transform(), colour_space=libcamera.ColorSpace.Sycc(), buffer_count=1, controls={}, display="main", encode=None):
		"""Make a configuration suitable for Zion applications.."""
		if self.camera is None:
			raise RunTimeError("Camera not opened")
		main = self._make_initial_stream_config({"format": "BGR888", "size": self.camera_properties_["PixelArraySize"]}, main)
		self.align_stream(main, optimal=False)
		lores = self._make_initial_stream_config({"format": "YUV420", "size": main["size"]}, lores)
		if lores is not None:
			self.align_stream(lores, optimal=False)
		raw = self._make_initial_stream_config({"format": self.sensor_format, "size":main["size"]}, raw, self._raw_stream_ignore_list)
		# Let the framerate vary?
		controls = {"NoiseReductionMode": libcamera.controls.draft.NoiseReductionModeEnum.Off,
					"FrameDurationLimits": (1000000//self.framerate, 1000000//self.framerate)} | controls
		config = {"use_case": "still",
				  "transform": transform,
				  "colour_space": colour_space,
				  "buffer_count": buffer_count,
				  "main": main,
				  "lores": lores,
				  "raw": raw,
				  "controls": controls}
		self._add_display_and_encode(config, display, encode)
		return config
		
	# @property
	# def exposure_speed(self):
		# return self.ControlsDict["ExposureTime"]

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
			#if param == 'AnalogueGain':
			#	print(f"Setting {param} to {getattr(params_in, param)}")
			#	if params_in.AnalogueGain > 0:
			#		self.set_analog_gain(params_in.AnalogueGain)
			#	else:
			#		print(f"Skipping setting analog_gain of {params_in.AnalogueGain} since it's <= 0")
			if param == 'DigitalGain':
				print(f"Setting {param} to {getattr(params_in, param)}")
			#	if params_in.DigitalGain > 0:
			#		self.set_digital_gain(params_in.DigitalGain)
			#	else:
			#		print(f"Skipping setting digital_gain of {params_in.DigitalGain} since it's <= 0")
			#elif param == 'AeEnable':
			#	# Wait a maximum of 5 seconds for all the values to take a hold, to be sure the gains are correct before fixing them in place
			#	sleep(1)
			##	for _ in range(5):
			#		settings_ok = True
			#		if self.controls.AnalogueGain != params_in.AnalogueGain:
			#			print(f"WARNING: Analog gain does not match expected value!  expected: {params_in.AnalogueGain}  actual: {self.controls.AnalogueGain}")
			#			settings_ok = False
#
			#		if self.controls.DigitalGain != params_in.DigitalGain:
			#			print(f"WARNING: Digital gain does not match expected value!  expected: {params_in.DigitalGain}  actual: {self.controls.DigitalGain}")
			#			settings_ok = False
			#			
			#		if settings_ok:
			#			break
			#			
			#		print("Sleeping another second for settings to propogate...")
			#		sleep(1)
					
			#	if not settings_ok:
			#		# By skipping the `AeEnable` settings if we failed, then we will pop a error to the user
			#		print("ERROR: Setting the camera settings failed!!!")
			#	else:
			#		self.controls.AeEnable = params_in.AeEnable
					
			elif param == "ColourGains":
				print(f"Setting {param} to {(params_in.RedGain, params_in.BlueGain)}")
				self.set_controls({param: (params_in.RedGain, params_in.BlueGain)})
			else:
				print(f"Setting {param} to {getattr(params_in, param)}")
				#setattr(self, param, getattr(params_in, param))
				self.set_controls({param: getattr(params_in, param)})

	def is_fixed_capture(self) -> Tuple[bool, dict]:
		""" Routine to return if the parameters correspond with
			non-auto adjusting gains and exposures """

		# Comparison func, Param name, Good value
		fixed_capture_params = (
			#(eq, "AwbEnable", False),
			#(eq, "AeEnable", False),
			#(gt, "shutter_speed", 0),
			#(eq, "iso", 0),
		)

		nonfixed_capture_params = {}
		
		metadata = self.capture_metadata()
		print(f"Controls = {self.controls}")
		print(f"Current metadata = {metadata}")
		for (comp_func, param_name, good_value) in fixed_capture_params:
			cur_value = metadata[param_name]
			if not comp_func(cur_value, good_value):
				nonfixed_capture_params[param_name] = cur_value

		return (not nonfixed_capture_params, nonfixed_capture_params)

	def capture(self, filename, cropping=(0,0,1,1), bayer=True, splitter=0):
		#self.zoom = cropping
		fileToWrite = filename+'.jpg'
		# ~ fileToWrite = filename+'.raw'
		if self.parent:
			self.parent.GPIO.camera_trigger()
			
		#img = self.capture_array("main")
		#print(f"Captured image size = {img.shape}")
		
		#raw = self.capture_array("raw")
		#print(f"Captured raw image size = {raw.shape}")
		
		pil_img = self.capture_image("main")
		self.parent.gui.cameraPreviewWrapper.draw_pillow_image(pil_img)
		
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

#		if self.parent:
#			GLib.idle_add(self.parent.update_last_capture, fileToWrite)

#		self.zoom=(0,0,1,1)
#		return ret
		return

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
		#self.brightness = val
		with self.controls as controls:
			controls.Brightness = val
		self.ControlsDict["Brightness"] = val
		print('\nSetting brightness to '+str(val))

	def set_contrast(self, val):
		#self.contrast = val
		with self.controls as controls:
			controls.Contrast = val
		self.ControlsDict["Contrast"] = val
		('\nSetting contrast to '+str(val))

	def set_saturation(self, val):
		#self.saturation = val
		with self.controls as controls:
			controls.Saturation = val
		self.ControlsDict["Saturation"] = val
		print('\nSetting saturation to '+str(val))

	def set_sharpness(self, val):
		#self.sharpness = val
		with self.controls as controls:
			controls.Sharpness = val
		self.ControlsDict["Sharpness"] = val
		print('\nSetting sharpness to '+str(val))

	def set_iso(self, val):
		self.iso = val
		print('\nSetting ISO to '+str(val))

	def set_exp_comp(self, val):
		#self.exposure_compensation = val
		with self.controls as controls:
			controls.ExposureValue = val
		self.ControlsDict["ExposureValue"] = val
		print('\nSetting exposure compensation to '+str(val))

	def set_shutter_speed(self, val):
		#TODO update camera control AND property
		#self.shutter_speed = val
		#if val==0:
		#	print('\nSetting exposure time to auto')
		#else:
		#	print('\nSetting exposure time to '+str(val))
		
		with self.controls as controls:
			controls.ExposureTime = val
		self.ControlsDict["ExposureTime"] = val
		#self.exposure_speed = val

		#todo check?
		print(f"Actual exposure time: {self.exposure_speed / 1000:.3f} ms")
		#print(f"shutter_speed: {self.shutter_speed}")

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
		#awb_gains = self.awb_gains
		#self.awb_gains = (val, awb_gains[1])
		with self.controls as controls:
			controls.ColourGains = (val, self.ControlsDict["ColourGains"][1])
		#todo check?
		self.ControlsDict["ColourGains"] = (val, self.ControlsDict["ColourGains"][1])
		print('\nSetting AWB red gain to '+str(val))

	def set_blue_gain(self, val):
		#awb_gains = self.awb_gains
		#self.awb_gains = (awb_gains[0], val)
		with self.controls as controls:
			controls.ColourGains = (self.ControlsDict["ColourGains"][0], val)
		#todo check?
		self.ControlsDict["ColourGains"] = (self.ControlsDict["ColourGains"][0], val)
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
		#todo range check
		with self.controls as controls:
			controls.AnalogueGain = val
		#todo: check value?
		self.ControlsDict["AnalogueGain"] = val
		sleep(1)
	
	def set_digital_gain(self, val):
		#not writable!
		#self.set_gain(MMAL_PARAMETER_DIGITAL_GAIN, val)
		return
		
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
		#super().start_preview(Preview.DRM, x=window[0], y=window[1], width=window[2], height=window[3], transform=self.transform)
		super().start_preview(Preview.NULL)


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
