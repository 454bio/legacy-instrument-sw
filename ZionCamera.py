from picamera import PiCamera, PiRenderer
import pigpio
import keyboard
# ~ from operator import itemgetter
from PIL import Image as PIL_Image
from time import sleep
import time
import os

class ZionCamera(PiCamera):

	def __init__(self, resolution, framerate, binning, initial_values, parent=None):

		print('\nCamera Initializing...')
		sensMode = 2 if binning else 3 #TODO: check framerate range too here
		super(ZionCamera,self).__init__(resolution=resolution, framerate=framerate, sensor_mode=sensMode)
		self.parent = parent
		self.framerate_range = (0.1, 10)

		self.brightness = initial_values['brightness']
		self.contrast = initial_values['contrast']
		self.saturation = initial_values['saturation']
		self.sharpness = initial_values['sharpness']
		self.awb_mode = initial_values['awb']
		self.awb_gains = (initial_values['red_gain'], initial_values['blue_gain'])
		self.exposure_mode = initial_values['exposure_mode']
		self.exposure_time = initial_values['exposure_time']

		self.BaseFilename = None
		self.file_idx = 0 #TODO: move to session
		print('\nCamera Ready')
        
	def quit(self):
		self.stop_preview()
		self.close()
		print('\nCamera Closed')
		
	def capture(self, filename, cropping=(0,0,1,1), baseTime=0, group=None):
		self.zoom = cropping
		fileTimestamp = round(1000*(time.time()-baseTime))
		group = str(group) if group else ''
		fileToWrite = os.path.join(filename[0], group+'_'+filename[1]+'_'+str(fileTimestamp)+'.jpg')
		# ~ group+'_'+filename+'_'+str(self.file_idx)+'_'+str(fileTimestamp)+'.jpg' if useIndex else filename+'.jpg'
		print('\nWriting image to file '+fileToWrite)
		self.parent.GPIO.camera_trigger(True)
		ret = super(ZionCamera,self).capture(fileToWrite)
		self.parent.GPIO.camera_trigger(False)
		self.zoom=(0,0,1,1)
		self.file_idx += 1
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


'''		
	def toggle_denoise(self):
		if self.image_denoise:
			self.image_denoise = False
			print('\nTurning off denoising')
		else:
			self.image_denoise = True
			print('\nTurning on denoising')

	def increase_brightness(self, amt=brightness_info[-1]):
		if self.brightness == brightness_info[1]:
			return
		else:
			self.brightness += amt
			print('\nBrightness = ' + str(self.brightness))
	def decrease_brightness(self, amt=brightness_info[-1]):
		if self.brightness == brightness_info[0]:
			return
		else:
			self.brightness -= amt
			print('\nBrightness = ' + str(self.brightness))
	def reset_brightness(self):
		self.brightness = brightness_info[2]
		print('\nBrightness = ' + str(self.brightness))
			
	def increase_contrast(self, amt=contrast_info[-1]):
		if self.contrast == contrast_info[1]:
			return
		else:
			self.contrast += amt
			print('\nContrast = ' + str(self.contrast))
	def decrease_contrast(self, amt=contrast_info[-1]):
		if self.contrast == contrast_info[0]:
			return
		else:
			self.contrast -= amt
			print('\nContrast = ' + str(self.contrast))
	def reset_contrast(self):
		self.contrast = contrast_info[2]
		print('\nContrast = ' + str(self.contrast))
					
	def increase_saturation(self, amt=saturation_info[-1]):
		if self.saturation == saturation_info[1]:
			return
		else:
			self.saturation += amt
			print('\nSaturation = ' + str(self.saturation))
	def decrease_saturation(self, amt=saturation_info[-1]):
		if self.saturation == saturation_info[0]:
			return
		else:
			self.saturation -= amt
			print('\nSaturation = ' + str(self.saturation))
	def reset_saturation(self):
		self.saturation = saturation_info[2]		
		print('\nSaturation = ' + str(self.saturation))

	def increase_sharpness(self, amt=sharpness_info[-1]):
		if self.sharpness == sharpness_info[1]:
			return
		else:
			self.sharpness += amt
			print('\nSharpness = ' + str(self.sharpness))
	def decrease_sharpness(self, amt=sharpness_info[-1]):
		if self.sharpness == sharpness_info[0]:
			return
		else:
			self.sharpness -= amt
			print('\nSharpness = ' + str(self.sharpness))
	def reset_sharpness(self):
		self.sharpness = sharpness_info[2]
		print('\nSharpness = ' + str(self.sharpness))
			
	def set_iso(self, value):
		self.iso = value
		if value==0:
			print('\nISO set to automatic')
		else:
			print('\nISO = '+str(self.iso))
		
	def set_meter_mode(self, value):
		self.meter_mode = value
		print('\nMetering mode = ' + self.meter_mode)
	
	def set_exposure_mode(self, value):
		self.exposure_mode = value
		print('\nExposure mode = ' + self.exposure_mode)
		
	def increase_exposure(self, amt=exposure_info[-1]):
		if self.exposure_compensation == exposure_info[1]:
			return
		else:
			self.exposure_compensation += amt
			print('\nExposure compensation = ' + str(self.exposure_compensation))
	def decrease_exposure(self, amt=exposure_info[-1]):
		if self.exposure_compensation == exposure_info[0]:
			return
		else:
			self.exposure_compensation -= amt
			print('\nExposure compensation = ' + str(self.exposure_compensation))
	def reset_exposure(self):
		self.exposure_compensation = exposure_info[2]
		print('\nExposure compensation = ' + str(self.exposure_compensation))
	
	def increase_shutter_speed(self, amt):
		# ~ print('stepsize is '+str(amt))
		# ~ print('max is '+str(self.shutter_speed_max))
		if not self.shutter_speed==0:
			if self.shutter_speed+amt >= self.shutter_speed_max:
				return
			else:
				self.shutter_speed += amt
				print('\nShutter speed set to '+str(self.shutter_speed))
	def decrease_shutter_speed(self, amt):
		# ~ print('stepsize is '+str(amt))
		# ~ print('max is '+str(self.shutter_speed_max))
		if not self.shutter_speed==0:
			if self.shutter_speed-amt <= 1000000./self.framerate:
				return
			else:
				self.shutter_speed -= amt
				print('\nShutter speed set to '+str(self.shutter_speed))
	def reset_shutter_speed(self):
		self.shutter_speed = self.shutter_speed_default
		print('\nShutter speed set to '+str(self.shutter_speed))
	def toggle_auto_shutter_speed(self):
		if self.shutter_speed:
			self.shutter_speed = 0
			print('\nShutter speed set to automatic')
		else:
			self.shutter_speed = self.exposure_speed
			print('\nShutter speed set to '+str(self.shutter_speed))

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
			
	def increase_red_awb(self, amt=awb_gains_red_info[-1]):
		if self.awb_mode=='off':
			current_awb_gains = self.awb_gains
			if current_awb_gains[0]+amt >= awb_gains_red_info[1]:
				return
			else:
				new_red_awb = current_awb_gains[0] + amt
				self.awb_gains = (new_red_awb, current_awb_gains[1])
				print('\nAuto White Balance Gain (RED) = '+str(new_red_awb))			
	def decrease_red_awb(self, amt=awb_gains_red_info[-1]):
		if self.awb_mode=='off':
			current_awb_gains = self.awb_gains
			if current_awb_gains[0]-amt <= awb_gains_red_info[0]:
				return
			else:
				new_red_awb = current_awb_gains[0] - amt
				self.awb_gains = (new_red_awb, current_awb_gains[1])
				print('\nAuto White Balance Gain (RED) = '+str(new_red_awb))
	def reset_red_awb(self):
		if self.awb_mode=='off':
			self.awb_gains = (awb_gains_red_info[2], self.awb_gains[1])
			print('\nAuto White Balance Gain (RED) = '+str(awb_gains_red_info[2]))		
	
	def increase_blue_awb(self, amt=awb_gains_blue_info[-1]):
		if self.awb_mode=='off':		
			current_awb_gains = self.awb_gains
			if current_awb_gains[1]+amt >= awb_gains_blue_info[1]:
				return
			else:
				new_blue_awb = current_awb_gains[1] + amt
				self.awb_gains = (current_awb_gains[0], new_blue_awb)			
				print('\nAuto White Balance Gain (BLUE) = '+str(new_blue_awb))		
	def decrease_blue_awb(self, amt=awb_gains_blue_info[-1]):
		if self.awb_mode=='off':
			current_awb_gains = self.awb_gains
			if current_awb_gains[1]-amt <= awb_gains_blue_info[0]:
				return
			else:
				new_blue_awb = current_awb_gains[1] - amt
				self.awb_gains = (current_awb_gains[0], new_blue_awb)
				print('\nAuto White Balance Gain (BLUE) = '+str(new_blue_awb))		
	def reset_blue_awb(self):
		if self.awb_mode=='off':
			self.awb_gains = (self.awb_gains[0], awb_gains_blue_info[2])
			print('\nAuto White Balance Gain (BLUE) = '+str(awb_gains_blue_info[2]))	

	def read_all_gains(self):
		print('\nAnalog Gain = '+str(float(self.analog_gain)))
		print('\nDigital Gain = '+str(float(self.digital_gain)))
		print('\nExposure Time = '+str(self.exposure_speed))
		print('\nShutter Time = '+str(self.shutter_speed))
		# ~ awb_gains = self.awb_gains
		# ~ print('\nAWB Gain (RED) = '+str(float(awb_gains[0])))
		# ~ print('\nAWB Gain (BLUE) = '+str(float(awb_gains[1])))

	def interactive_preview(self, baseFilename=None, init_file_idx=0, cropping=(0,0,1,1), window=None, baseTime=0):
		self.file_idx = init_file_idx
		keyboard.add_hotkey('space', self.capture, args=(baseFilename, cropping, baseTime, 'P'))
		
		keyboard.add_hotkey('u', self.parent.GPIO.turn_on_led, args=('Blue',))
		keyboard.add_hotkey('j', self.parent.GPIO.turn_off_led, args=('Blue',))
		keyboard.add_hotkey('i', self.parent.GPIO.turn_on_led, args=('Orange',))
		keyboard.add_hotkey('k', self.parent.GPIO.turn_off_led, args=('Orange',))
		keyboard.add_hotkey('o', self.parent.GPIO.turn_on_led, args=('UV',))
		keyboard.add_hotkey('l', self.parent.GPIO.turn_off_led, args=('UV',))
		
		keyboard.add_hotkey('tab', self.toggle_denoise)
		
		keyboard.add_hotkey('a', self.increase_brightness)
		keyboard.add_hotkey('z', self.decrease_brightness)
		keyboard.add_hotkey('q', self.reset_brightness)
		keyboard.add_hotkey('s', self.increase_contrast)
		keyboard.add_hotkey('x', self.decrease_contrast)
		keyboard.add_hotkey('w', self.reset_contrast)
		keyboard.add_hotkey('d', self.increase_saturation)
		keyboard.add_hotkey('c', self.decrease_saturation)
		keyboard.add_hotkey('e', self.reset_saturation)
		keyboard.add_hotkey('f', self.increase_sharpness)
		keyboard.add_hotkey('v', self.decrease_sharpness)
		
		keyboard.add_hotkey('`', self.set_iso, args=(iso_info[0],))
		keyboard.add_hotkey('1', self.set_iso, args=(iso_info[1],))
		keyboard.add_hotkey('2', self.set_iso, args=(iso_info[2],))
		keyboard.add_hotkey('3', self.set_iso, args=(iso_info[3],))
		keyboard.add_hotkey('4', self.set_iso, args=(iso_info[4],))
		keyboard.add_hotkey('5', self.set_iso, args=(iso_info[5],))
		keyboard.add_hotkey('6', self.set_iso, args=(iso_info[6],))
		keyboard.add_hotkey('7', self.set_iso, args=(iso_info[7],))
		keyboard.add_hotkey('8', self.set_iso, args=(iso_info[8],))
		keyboard.add_hotkey('9', self.set_meter_mode, args=(metering_mode[0],))	
		keyboard.add_hotkey('0', self.set_meter_mode, args=(metering_mode[1],))
		keyboard.add_hotkey('-', self.set_meter_mode, args=(metering_mode[2],))
		keyboard.add_hotkey('=', self.set_meter_mode, args=(metering_mode[3],))
		
		keyboard.add_hotkey('b', self.decrease_exposure)
		keyboard.add_hotkey('g', self.increase_exposure)
		keyboard.add_hotkey('t', self.reset_exposure)
		# ~ keyboard.add_hotkey('n', self.decrease_shutter_speed, args=(self.shutter_speed_step,))
		# ~ keyboard.add_hotkey('h', self.increase_shutter_speed, args=(self.shutter_speed_step,))
		# ~ keyboard.add_hotkey('y', self.reset_shutter_speed)
		# ~ keyboard.add_hotkey('u', self.toggle_auto_shutter_speed)
		
		keyboard.add_hotkey('F1', self.set_exposure_mode, args=(exposure_mode_info[0],), suppress=True)
		keyboard.add_hotkey('F2', self.set_exposure_mode, args=(exposure_mode_info[1],), suppress=True)
		keyboard.add_hotkey('F3', self.set_exposure_mode, args=(exposure_mode_info[2],), suppress=True)
		# ~ keyboard.add_hotkey('F4', self.set_exposure_mode, args=(exposure_mode_info[3],), suppress=True)
		# ~ keyboard.add_hotkey('F5', self.set_exposure_mode, args=(exposure_mode_info[4],), suppress=True)
		# ~ keyboard.add_hotkey('F6', self.set_exposure_mode, args=(exposure_mode_info[5],), suppress=True)
		# ~ keyboard.add_hotkey('F7', self.set_exposure_mode, args=(exposure_mode_info[6],), suppress=True)
		# ~ keyboard.add_hotkey('F8', self.set_exposure_mode, args=(exposure_mode_info[7],), suppress=True)
		# ~ keyboard.add_hotkey('F9', self.set_exposure_mode, args=(exposure_mode_info[8],), suppress=True)
		keyboard.add_hotkey('F4', self.set_exposure_mode, args=(exposure_mode_info[9],), suppress=True)
		keyboard.add_hotkey('F11', self.set_exposure_mode, args=(exposure_mode_info[10],), suppress=True)
		keyboard.add_hotkey('F12', self.set_exposure_mode, args=(exposure_mode_info[11],), suppress=True)

		keyboard.add_hotkey('\\', self.toggle_awb)
		keyboard.add_hotkey('apostrophe', self.increase_red_awb)
		keyboard.add_hotkey('/', self.decrease_red_awb)
		keyboard.add_hotkey(']', self.reset_red_awb)
		keyboard.add_hotkey(';', self.increase_blue_awb)
		keyboard.add_hotkey('.', self.decrease_blue_awb)
		keyboard.add_hotkey('[', self.reset_blue_awb)
		
		keyboard.add_hotkey('backspace', self.read_all_gains)
		
		#TODO: move preview to gui
		if window:
			self.start_preview(fullscreen=False, window=window)
		else:
			self.start_preview()
		keyboard.wait('esc')
		self.stop_preview()
'''
#TODO: link cropping with bounding box UI input
