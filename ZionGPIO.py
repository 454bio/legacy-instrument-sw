import pigpio
import glob
import time
from functools import partial
from typing import List, Dict
import threading

from ZionEvents import ZionEvent, ZionLED, ZionLEDColor

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
UV = [12] #pin 32
BLUE = [16] #pins 36
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

	LED_IDX : Dict[ZionLEDColor, int] = {
		ZionLEDColor.UV : 0,
		ZionLEDColor.BLUE : 1,
		ZionLEDColor.ORANGE : 2,
	}

	LED_DC : Dict[ZionLEDColor, int] = {
		ZionLEDColor.UV : 100,
		ZionLEDColor.BLUE : 100,
		ZionLEDColor.ORANGE : 100,
	}

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

		self.gpioList = {
			ZionLEDColor.UV: UV_gpios,
			ZionLEDColor.BLUE: Blue_gpios,
			ZionLEDColor.ORANGE: Orange_gpios
		}

		self.pS = {c: 0.0 for c in ZionLEDColor} #UV, Blue, Orange
		self.dc = {c: 0.0 for c in ZionLEDColor}
		self.old_wid = None
		self.stop_event = threading.Event()

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
		for color in ZionLEDColor:
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

	def set_pulse_start_in_micros(self, color : ZionLEDColor, start : int):
		start %= self.micros
		self.pS[color] = start / self.micros

	def set_duty_cycle(self, color : ZionLEDColor, dc : float):
		self.dc[color] = dc
		if dc > 0:
			self.LED_DC[color] = int(dc * 100)

	def update_pwm_settings(self):

		null_wave = True
		for color, gpios in self.gpioList.items():
			for g in gpios:
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
			if not self.stop_event.is_set():
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
		for color in ZionLEDColor:
			self.set_duty_cycle(color, 0)
		self.update_pwm_settings()

	def enable_leds(self, leds : List[ZionLED], verbose=False):
		for l in leds:
			self.enable_led(l.color, l.intensity/100, verbose=verbose, update=False)
		self.update_pwm_settings()

	def disable_leds(self, leds : List[ZionLED], verbose=False):
		for l in leds:
			self.enable_led(l.color, 0, verbose=verbose, update=False)
		self.update_pwm_settings()

	def enable_led(self, color : ZionLEDColor, amt : float, verbose : bool = False, update: bool =True):
		self.set_duty_cycle(color, amt)
		print(f"\nSetting {color.name} to {amt}")
		if verbose:
			self.parent.gui.printToLog(f"{color.name} set to {amt}")

		if update:
			self.update_pwm_settings()

	def turn_on_led(self, color : ZionLEDColor, verbose : bool = False):
		amt = self.LED_DC[color] / 100.
		self.set_duty_cycle(self.LED_IDX[color], amt)
		print(f"\nSetting {color.name} to {amt}")
		if verbose:
			self.parent.gui.printToLog(f"{color.name} set to {amt}")

		self.update_pwm_settings()

	def send_uv_pulse(self, pulsetime : float, dc : int):
		self.enable_led(ZionLEDColor.UV, dc)
		time.sleep(pulsetime / 1000.)
		self.enable_led(ZionLEDColor.UV, 0)

	def enable_vsync_callback(self, event : ZionEvent):
		self.callback_for_uv_pulse = self.callback(
			XVS,
			pigpio.RISING_EDGE,
			partial(self.parent.pulse_on_trigger, event)
		)
