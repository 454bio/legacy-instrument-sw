import pigpio
import os
import itertools
import glob

# Gpio Pin Lookup Table. Index is GPIO #, format is (pin #, enabled, alternate function)
# (can remove/trim if memory is an issue)
GpioPins = (
	(None, None,  None  ), #No GPIO 0
	(None, None,  None  ), #No GPIO 1
	(3,    False, 'I2C' ),
	(5,    False, 'I2C' ),
	(7,    True,  '1W'  ), #Default pin for 1-wire interface
	(29,   True,  None  ),
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
TEMP_OUTPUT = 13

# 1 GPIOs for temp sensing (to use 1-wire):
TEMP_INPUT_1W = 5
'''
TODO:
edit /boot/config.txt
dtoverlay=w1-gpio (for 4)
dtoverlay=w1-gpio,gpiopin=5 (for 5)
4.7k pull-up to 3.3v (pin 1 or 17)
ls /sys/bus/w1/devices
'''




#1 GPIO for UV safety switch:
#TODO

class ZionGPIO(pigpio.pi):
	
	#TODO: add UV off command to appropriate error handles?
	
	def __init__(self, UV_gpios=UV, Blue_gpios=BLUE, Orange_gpios=ORANGE, temp_out_gpio=TEMP_OUTPUT, temp_in_gpio=TEMP_INPUT_1W, camera_trigger_gpio=CAMERA_TRIGGER):
		
		#os.system("sudo pigpiod") #This is now done upon boot (actually ~/.bashrc)
		super(ZionGPIO, self).__init__()

		# Check that GPIO settings are valid:
		#TODO: may need adjustment for temperature output (eg if it takes more than one pin)
		for g in UV_gpios+Blue_gpios+Orange_gpios+[temp_out_gpio, camera_trigger_gpio]:
			if GpioPins[g][1]:
				super(ZionGPIO, self).set_mode(g, pigpio.OUTPUT)
			else:
				raise ValueError('Chosen GPIO is not enabled!')

		#Now set up register methods of setting/clearing led outputs:		
		self.UV_GPIOs = UV_gpios
		self.Blue_GPIOs = Blue_gpios
		self.Orange_GPIOs = Orange_gpios
		self.UV_Reg = 0
		for bit in UV_gpios:
			self.UV_Reg |= (1<<bit)
		self.Blue_Reg = 0
		for bit in Blue_gpios:
			self.Blue_Reg |= (1<<bit)
		self.Orange_Reg = 0
		for bit in Orange_gpios:
			self.Orange_Reg |= (1<<bit)
		
		# Just assign a trigger here. There is no routine here because
		# this pin is set directly by Camera object
		self.Camera_Trigger = camera_trigger_gpio
		
		self.Temp_Output_GPIO = temp_out_gpio
		#TODO: implement heat control output
				
		base_dir = '/sys/bus/w1/devices/'
		try:
			self.Temp_1W_device = glob.glob(base_dir + '28*')[0]
		except IndexError:
			print('Warning: 1-Wire interface not connected.')
			self.Temp_1W_device = None 
		# ~ f = open(device_folder+'', 'r')
		# ~ self.Temp_1W_address = f.readline()
		# ~ f.close()
		# ~ self.Temp_1W_device_file = device_folder+self.Temp_1W_address+'/w1_slave'
		
		# ~ #TODO: finish setting up 1-wire for temp input
		
		# Last thing is to ensure all leds are off:
		self.turn_off_led('all')
		
		
		
	#TODO: add simultaneous led events
	def turn_on_led(self, color):
		if color=='all':
			print('\nTurning all LEDs on')
			super(ZionGPIO,self).set_bank_1( self.UV_Reg | self.Blue_Reg | self.Orange_Reg )
		elif color=='UV':
			print('\nTurning UV on')
			super(ZionGPIO,self).set_bank_1( self.UV_Reg )
		elif color == 'Blue':
			print('\nTurning Blue on')
			super(ZionGPIO,self).set_bank_1( self.Blue_Reg )	
		elif color == 'Orange':
			print('\nTurning Orange on')
			super(ZionGPIO,self).set_bank_1( self.Orange_Reg )
		else:
			raise ValueError('Invalid color choice!')

	#TODO: add simultaneous led events
	def turn_off_led(self, color):
		if color=='all':
			print('\nTurning all LEDs off')
			super(ZionGPIO,self).clear_bank_1( self.UV_Reg | self.Blue_Reg | self.Orange_Reg )
		elif color=='UV':
			print('\nTurning UV off')
			super(ZionGPIO,self).clear_bank_1( self.UV_Reg )
		elif color == 'Blue':
			print('\nTurning Blue off')
			super(ZionGPIO,self).clear_bank_1( self.Blue_Reg )	
		elif color == 'Orange':
			print('\nTurning Orange off')
			super(ZionGPIO,self).clear_bank_1( self.Orange_Reg )
		else:
			raise ValueError('Invalid color choice!')
	
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
			print('No digital thermometer connected')
			return None
