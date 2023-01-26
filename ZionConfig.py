import os
import glob
import json
from collections import UserDict

CONFIG_FILEPATH = "/home/pi/zion.cfg"
SHARE_FILEPATH = "/home/pi/SharedData"
DATA_FILEPATH_REL = "GoogleData/InstrumentData"
INVALID_SERIAL = "_INVALID"

class ZionConfig(dict):

	DEVICE_CPUID_REGISTERY = { # (cpuid, )
		# {serial}: cpuid  #can add things later by turning into tuple
		"Zach_Dev": "417c8eb2",
		"MK26_03F": "fe04ffd5",
		"MK27_01":  "8273400a",
		"MK27_02":  "28a62a16",
		"MK27_04":  "e7e7af47",
		"MK27_05":  "b3ff81ad",
		"MK26_07":  "cdfc750b",
		"MK26_08":  "bad5a0cf",
	}

	def __init__(self):
		super().__init__(read_config_file())
		cpu_serial = get_cpu_serial()
		if cpu_serial == INVALID_SERIAL:
			raise ValueError("Couldn't read cpu serial number!")
		else:
			try:
				if cpu_serial != self.DEVICE_CPUID_REGISTERY[self["serial"]]:
					raise ValueError(f"CPU ID {cpu_serial} is not registered to unit with serial number '{self['serial']}'")
				else:
					self["cpusn"] = cpu_serial
					print(f"CPU ID {cpu_serial} is registered to this unit (SN: '{self['serial']}')")
			except KeyError:
				raise KeyError(f"Serial number '{self['serial']}' is not in device directory!")
		self["path"] = os.path.join(SHARE_FILEPATH, DATA_FILEPATH_REL, self["serial"].strip())

		try:
			if os.path.isdir(SHARE_FILEPATH):
				# Now see if serial number folder exists
				if os.path.isdir(self["path"]):
					return
				else:
					os.makedirs(self["path"])
					print(f"Creating data directory {self['path']}")
			else: #create local directory instead
				cfg["path"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")
				if not os.path.isdir(self["path"]):
					os.makedirs(self["path"])
				#TODO make an actual (python) warning?
				print(f"WARNING: SMB Share {SHARE_FILEPATH} not found. Using local path {self['path']} instead.")
		# TODO handle any exceptions?
		except Exception as e:
			raise e

def get_cpu_serial():
	cpu_serial = INVALID_SERIAL
	try:
		with open("/proc/cpuinfo", 'r') as f:
			for line in f:
				if line[0:6] == "Serial":
					cpu_serial = line[10:26]
	except:
		cpu_serial = INVALID_SERIAL
	return cpu_serial[-8:]

def read_config_file():
	cfg = dict()
	with open(CONFIG_FILEPATH) as f:
		for line in f:
			if line:
				line_split = line.split(':')
				if len(line_split) == 2:
					cfg[ line_split[0].strip() ] = line_split[1].strip()
				else:
					print(f"Skipping parameter, too many colons in line {line}")
	return cfg


