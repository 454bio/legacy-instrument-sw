import os
import glob
import json
from collections import UserDict
import signal

CONFIG_FILEPATH = "/home/pi/zion.cfg"
SHARE_FILEPATH = "/home/pi/SharedData"
DATA_FILEPATH_REL = "GoogleData/InstrumentData"
INVALID_SERIAL = "_INVALID"
CPUID_DIGITS = 8

class ZionConfig(dict):

	DEVICE_CPUID_REGISTRY = { # (cpuid, )
		# {serial}: cpuid  #can add things later by turning into tuple
		"Zach_Dev": "417c8eb2",
		"Dry_Imager": "cdfc750b",
		"MK26_03F": "fe04ffd5",
		"MK27_01":  "8273400a",
		"MK27_02":  "28a62a16",
		"MK27_04":  "e7e7af47",
		"MK27_05":  "b3ff81ad",
		"MK26_07":  "cdfc750b",
		"MK27_09":  "bad5a0cf",
		"MK27_11":  "d0c4a2c9",
		"MK29_14":  "eda8f92c",
		"MK27_13":  "4e68d646",
	}

	def __init__(self):
		print(f"Reading config file {CONFIG_FILEPATH}...")
		super().__init__(read_config_file())
		cpu_serial = get_cpu_serial()
		if cpu_serial == INVALID_SERIAL:
			raise ValueError("Couldn't read cpu serial number!")
		else:
			try:
				if cpu_serial != self.DEVICE_CPUID_REGISTRY[self["serial"]]:
					raise ValueError(f"CPU ID {cpu_serial} is not registered to unit with serial number '{self['serial']}'")
				else:
					self["cpusn"] = cpu_serial
					print(f"CPU ID {cpu_serial} is registered to this unit (SN: '{self['serial']}')")
			except KeyError:
				raise KeyError(f"Serial number '{self['serial']}' is not in device registry!")
		remote_path = os.path.join(SHARE_FILEPATH, DATA_FILEPATH_REL, self["serial"].strip())

		print(f"Testing connectivity to cloud...")
		try:
			ismount = os.path.ismount(SHARE_FILEPATH)
		except OSError as e:
			ismount = False

		if ismount: #see if it's a mount point
			if not os.path.isdir(remote_path):
				os.makedirs(self["remote_path"])
				print(f"Creating cloud directory {remote_path}")
				self["remote_path"] = remote_path
			else:
				print(f"Cloud directory {remote_path} already exists")
				self["remote_path"] = remote_path

		else: #create local directory instead
			print(f"Could not find network mount point at {SHARE_FILEPATH}")
			self["remote_path"] = None

def get_cpu_serial():
	cpu_serial = INVALID_SERIAL
	print(f"Reading CPU ID...")
	try:
		with open("/proc/cpuinfo", 'r') as f:
			for line in f:
				if line[0:6] == "Serial":
					cpu_serial = line[10:26]
		print(f"CPU ID = {cpu_serial}, using last {CPUID_DIGITS} digits: {cpu_serial[-CPUID_DIGITS:]}")
	except:
		cpu_serial = INVALID_SERIAL
	return cpu_serial[-CPUID_DIGITS:]

def read_config_file():
	cfg = dict()
	#TODO error handle here
	with open(CONFIG_FILEPATH) as f:
		for line in f:
			if line:
				line_split = line.split(':')
				if len(line_split) == 2:
					cfg[ line_split[0].strip() ] = line_split[1].strip()
				else:
					print(f"Skipping parameter, too many colons in line {line}")
	return cfg
