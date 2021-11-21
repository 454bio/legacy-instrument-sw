import pigpio
import os
import itertools
import glob
import time
import threading
from functools import partial

# Gpio Pin Lookup Table. Index is GPIO #, format is (pin #, enabled, alternate function)
# (can remove/trim if memory is an issue)
GpioPins = (
	(None, None,  None  ), #No GPIO 0
	(None, None,  None  ), #No GPIO 1
	(3,    False, 'I2C' ),
	(5,    False, 'I2C' ),
	(7,    True,  None  ), #Default pin for 1-wire interface
	(29,   True,  '1W'  ), #Using this pin for 1-wire instead (GPIO5 referenced in boot config)
	(31,   True,  None  ),
	(26,   False, 'SPI' ), #used for TFT
	(24,   False, 'SPI' ), #used for TFT
	(21,   False, 'SPI' ), #used for TFT
	(19,   False, 'SPI' ), #used for TFT
	(23,   False, 'SPI' ), #used for TFT
	(32,   True,  None  ),
	(33,   True,  None  ),
	(8,    False, 'UART'),
	(10,   False, 'UART'),
	(36,   True,  None  ),
	(11,   True,  None  ),
	(12,   True,  'PCM' ),
	(35,   True,  'PCM' ),
	(38,   True,  'PCM' ),
	(40,   True,  'PCM' ),
	(15,   True,  None  ),
	(16,   True,  None  ),
	(18,   True,  None  ),
	(22,   True,  None  ),
	(37,   True,  None  ))

# Now define GPIO uses for Zion:

# 2 GPIOs for each LED:
# ~ UV = [6,12] #pins 31, 32
UV = [12] #pin 32
# ~ BLUE = [19,16] #pins 35,36
BLUE = [16] #pins 36
# ~ ORANGE = [26,20] #pins 37,38
ORANGE = [20] #pin 38

# 1 GPIO for camera capture timing testing:
CAMERA_TRIGGER = 21 #pin 40

#1 GPIO for heat control:
TEMP_OUTPUT = 13 #pin 33

# 1 GPIOs for temp sensing (to use 1-wire):
TEMP_INPUT_1W = 5 #pin 29

#1 GPIO for UV safety switch:
#TODO

#2 GPIOs for testing camera sync signals:
FSTROBE = 23 #pin 16
XVS = 24 #pin 18

class ZionGPIO(pigpio.pi):
	
	UV_idx = 0
	BLUE_idx = 1
	ORANGE_idx = 2
	
	#TODO: add UV off command to appropriate error handles?
	
	def __init__(self, pwm_freq, UV_gpios=UV, Blue_gpios=BLUE, Orange_gpios=ORANGE, temp_out_gpio=TEMP_OUTPUT, temp_in_gpio=TEMP_INPUT_1W, camera_trigger_gpio=CAMERA_TRIGGER, parent=None):
		super(ZionGPIO, self).__init__()
		
		self.parent=parent
		self.frequency = pwm_freq #not changing for different gpios
		self.micros = 1000000./self.frequency #period in microseconds

		# Check that GPIO settings are valid:
		#TODO: may need adjustment for temperature output (eg if it takes more than one pin)
		for g in UV_gpios+Blue_gpios+Orange_gpios+[temp_out_gpio, camera_trigger_gpio]:
			if GpioPins[g][1]:
				super(ZionGPIO,self).set_mode(g, pigpio.PUD_DOWN)
				if g in UV_gpios+Blue_gpios+Orange_gpios:
					# ~ super(ZionGPIO,self).set_pull_up_down(g, pigpio.PUD_DOWN)
					super(ZionGPIO,self).set_PWM_range(g, 100)
			else:
				raise ValueError('Chosen GPIO is not enabled!')
		
		# Now make camera sync signals inputs:
		for g in [FSTROBE, XVS]:
			if GpioPins[g][1]:
				super(ZionGPIO,self).set_mode(g, pigpio.INPUT)
		
		self.gpioList = [UV_gpios, Blue_gpios, Orange_gpios] #Order is important
		self.pS = [0.0]*3 #UV, Blue, Orange
		self.dc = [0.0]*3
		self.old_wid = None
		self.stop = False
		
		self.Blue_DC = 100
		self.Orange_DC = 100
		self.UV_DC = 100
		
		#Now set up register methods of setting/clearing led outputs:		
		# (not used for pwm)
		# ~ self.UV_Reg = 0
		# ~ for bit in UV_gpios:
			# ~ self.UV_Reg |= (1<<bit)
		# ~ self.Blue_Reg = 0
		# ~ for bit in Blue_gpios:
			# ~ self.Blue_Reg |= (1<<bit)
		# ~ self.Orange_Reg = 0
		# ~ for bit in Orange_gpios:
			# ~ self.Orange_Reg |= (1<<bit)
		
		self.Camera_Trigger = camera_trigger_gpio
        
		self.Temp_Output_GPIO = temp_out_gpio
		#TODO: implement heat control output
        
        #No check for Temperature Input GPIO pin, this is done in boot config file (including GPIO choice)
		base_dir = '/sys/bus/w1/devices/'
		try:
			self.Temp_1W_device = glob.glob(base_dir + '28*')[0]
		except IndexError:
			print('Warning: 1-Wire interface not connected.')
			self.Temp_1W_device = None 
		
		# Last thing is to ensure all gpio outputs are off:
		for color in range(3):
			self.enable_led(color, 0)
		self.camera_trigger(False)
		
		self.test_delay = 0
		self.test_pulse_width = 1

	def camera_trigger(self, bEnable):
		super(ZionGPIO, self).write(self.Camera_Trigger, bEnable)

	def read_temperature(self):
		if self.Temp_1W_device:
			f = open(self.Temp_1W_device+'/w1_slave', 'r')
			lines = f.readlines()
			f.close()
			if not lines[0][-4:-1]=='YES':
				print('Serial communications issue!')
			else:
				equals_pos = lines[1].find('t=')
				temp_c = float(lines[1][equals_pos+2:])/1000.
				# ~ print('\nTemperature = '+str(temp_c)+' C')
			return temp_c
		else:
			return None
			
	def set_pulse_start_in_micros(self, color, start):
		start %= self.micros
		self.pS[color] = start / self.micros
	
	def set_duty_cycle(self, color, dc):
		self.dc[color] = dc
		if dc>0:
			if color==ZionGPIO.UV_idx:
				self.UV_DC = int(dc*100)
			elif color==ZionGPIO.BLUE_idx:
				self.Blue_DC = int(dc*100)
			elif color==ZionGPIO.ORANGE_idx:
				self.Orange_DC = int(dc*100)

	def update_pwm_settings(self):

		null_wave = True
		for color in range(len(self.gpioList)):
			for g in self.gpioList[color]:
				null_wave = False
				on = int(self.pS[color] * self.micros)
				length = int(self.dc[color] * self.micros)
				micros = int(self.micros)
				if length <= 0:
					self.wave_add_generic([pigpio.pulse(0, 1<<g, micros)])
				elif length >= micros:
					self.wave_add_generic([pigpio.pulse(1<<g, 0, micros)])
				else:
					off = (on + length) % micros
					if on<off:
						self.wave_add_generic([
							pigpio.pulse(   0, 1<<g,           on),
							pigpio.pulse(1<<g,    0,     off - on),
							pigpio.pulse(   0, 1<<g, micros - off),
						])
					else:
						self.pi.wave_add_generic([
							pigpio.pulse(1<<g,    0,         off),
							pigpio.pulse(   0, 1<<g,    on - off),
							pigpio.pulse(1<<g,    0, micros - on),
						])
		if not null_wave:
			if not self.stop:
				new_wid = self.wave_create()
				if self.old_wid is not None:
					self.wave_send_using_mode(new_wid, pigpio.WAVE_MODE_REPEAT_SYNC)
					while self.wave_tx_at() != new_wid:
						pass
					self.wave_delete(self.old_wid)
				else:
					self.wave_send_repeat(new_wid)
				self.old_wid = new_wid
				
	def cancel_PWM(self):
		for color in range(3):
			self.set_duty_cycle(color, 0)
		self.update_pwm_settings()
		# ~ self.stop = True
		# ~ self.wave_tx_stop()
		# ~ if self.old_wid is not None:
			# ~ self.wave_delete(self.old_wid)
			
	def enable_leds(self, dcDict, verbose=False):
		for color in dcDict.keys():
			self.enable_led(color, dcDict[color]/100, verbose=verbose, update=False)
		self.update_pwm_settings()
		
	def disable_leds(self, dcDict, verbose=False):
		for color in dcDict.keys():
			self.enable_led(color, 0, verbose=verbose, update=False)
		self.update_pwm_settings()

	def enable_led(self, color, amt, verbose=False, update=True):
		# ~ amt = amt
		# ~ if amt<0 or amt>1:
			# ~ raise ValueError("Duty Cycle must be between 0 and 1!")
		if color=='UV':
			self.set_duty_cycle(ZionGPIO.UV_idx, amt)
			print('\nSetting UV to '+str(amt))
			if verbose:
				self.parent.gui.printToLog('UV set to '+str(amt))
		if color=='Blue':
			self.set_duty_cycle(ZionGPIO.BLUE_idx, amt)
			print('\nSetting Blue to '+str(amt))
			if verbose:
				self.parent.gui.printToLog('Blue set to '+str(amt))
		if color=='Orange':
			self.set_duty_cycle(ZionGPIO.ORANGE_idx, amt)
			print('\nSetting Orange to '+str(amt))
			if verbose:
				self.parent.gui.printToLog('Orange set to '+str(amt))
		if update:
			self.update_pwm_settings()

	def turn_on_led(self, color, verbose=False):
		if color=='UV':
			amt = self.UV_DC/100.
			self.set_duty_cycle(ZionGPIO.UV_idx, amt)
			print('\nSetting UV to '+str(amt))
			if verbose:
				self.parent.gui.printToLog('UV set to '+str(amt))
		if color=='Blue':
			amt = self.Blue_DC/100.
			self.set_duty_cycle(ZionGPIO.BLUE_idx, amt)
			print('\nSetting Blue to '+str(amt))
			if verbose:
				self.parent.gui.printToLog('Blue set to '+str(amt))
		if color=='Orange':
			amt = self.Orange_DC/100.
			self.set_duty_cycle(ZionGPIO.ORANGE_idx, amt)
			print('\nSetting Orange to '+str(amt))
			if verbose:
				self.parent.gui.printToLog('Orange set to '+str(amt))
		self.update_pwm_settings()
		
	def send_uv_pulse(self, pulsetime, dc):
		self.enable_led('UV', dc)
		time.sleep(pulsetime/1000.)
		self.enable_led('UV', 0)

	def enable_vsync_callback(self, colors, pw, capture):
		self.callback_for_uv_pulse = super(ZionGPIO,self).callback(XVS, pigpio.RISING_EDGE, lambda gpio,level,ticks: self.parent.pulse_on_trigger(colors, pw, capture, gpio, level, ticks))
	
	# ~ def enable_vsync_callback(self):
		# ~ self.callback_for_uv_pulse = super(ZionGPIO,self).callback(XVS, pigpio.RISING_EDGE, lambda gpio,level,ticks: self.uv_pulse_on_trigger(gpio, level, ticks))


