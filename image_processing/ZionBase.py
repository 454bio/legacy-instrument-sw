
from collections import UserDict, UserString
import numpy as np
import pandas as pd
import skimage as ski
from matplotlib import pyplot as plt

from ZionImage import ZionImage, ZionDifferenceImage

BASES = ('A', 'C', 'G', 'T', 'S')

class ZionBase: # TODO decide whether to subclass UserDict
	def __init__(self, label, color=None):
		self.char = label
		self.color = color
		# TODO: add more properties


class ZionBase(UserString):

	Names = ('A', 'C', 'G', 'T', '!')

	def __init__(self, char):
		if not isinstance(char, str):
			raise TypeError("Base must be a character!")
		elif len(char) != 1:
			raise ValueError("Base must be a one-character string!")
		elif char not in ZionBase.Names:
			raise ValueError(f"Base must be valid character (not '{c}')!")
