import pigpio
import os
import itertools
import glob
import time

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
UV = [6,12] #pins 31, 32
BLUE = [19,16] #pins 35,36
ORANGE = [26,20] #pins 37,38

# 1 GPIO for camera capture timing testing:
CAMERA_TRIGGER = 21 #pin 40

#1 GPIO for heat control:
TEMP_OUTPUT = 13 #pin 33

# 1 GPIOs for temp sensing (to use 1-wire):
TEMP_INPUT_1W = 5 #pin 29

#1 GPIO for UV safety switch:
#TODO

class ZionGPIO(pigpio.pi):
	
	#TODO: add UV off command to appropriate error handles?
	
	def __init__(self, pwm_freq, UV_gpios=UV, Blue_gpios=BLUE, Orange_gpios=ORANGE, temp_out_gpio=TEMP_OUTPUT, temp_in_gpio=TEMP_INPUT_1W, camera_trigger_gpio=CAMERA_TRIGGER, parent=None):
		super(ZionGPIO, self).__init__()
		
		self.parent=parent
		self.frequency = pwm_freq

		# Check that GPIO settings are valid:
		#TODO: may need adjustment for temperature output (eg if it takes more than one pin)
		for g in UV_gpios+Blue_gpios+Orange_gpios+[temp_out_gpio, camera_trigger_gpio]:
			if GpioPins[g][1]:
				super(ZionGPIO,self).set_mode(g, pigpio.OUTPUT)
				if g in UV_gpios+Blue_gpios+Orange_gpios:
					# ~ super(ZionGPIO,self).set_pull_up_down(g, pigpio.PUD_DOWN)
					super(ZionGPIP,self).set_PWM_range(g, 100)
			else:
				raise ValueError('Chosen GPIO is not enabled!')

		self.UV_GPIOs = UV_gpios
		self.Blue_GPIOs = Blue_gpios
		self.Orange_GPIOs = Orange_gpios
		
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
		self.turn_off_led('all')
		self.camera_trigger(False)
		
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
				print('\nTemperature = '+str(temp_c)+' C')
			return temp_c
		else:
			# ~ print('No digital thermometer connected')
			return None
			
	def set_pulse_start_in_fraction(self, gpio, start):
		
		
	def turn_on_led(self, color, verbose=False):

	def turn_off_led(self, color, verbose=False):

	def send_uv_pulse(self, pulsetime):
		self.turn_on_led('UV')
		#TODO: use different timer (from gtk?)
		time.sleep(float(pulsetime/1000.))
		self.turn_off_led('UV')

