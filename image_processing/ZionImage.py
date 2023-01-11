import os, time
import multiprocessing
import threading
import numpy as np
import pandas as pd
import cv2
import skimage as ski
from collections import UserDict
from tifffile import imread, imwrite

from image_processing.raw_converter import jpg_to_raw, get_wavelength_from_filename, get_cycle_from_filename

def rgb2gray(img, weights=None):
	if weights is None:
		return np.mean(img, axis=-1).round().astype('uint16')
	else:
		raise ValueError("Invalid weights option!")

def median_filter(in_img, kernel_size, behavior='ndimage'): #rank?
	if len(in_img.shape) == 2: # grayscale
		out_img = ski.filters.median(in_img, ski.morphology.disk(kernel_size), behavior=behavior)
	elif len(in_img.shape) == 3: # multi-channel
		if behavior == 'cv2':
			# TODO
			raise ValueError("Invalid behavior option!")
		else:
			for ch in range(in_img.shape[-1]):
				out_img[:,:,ch] = ski.filters.median(in_img[:,:,ch], ski.morphology.disk(kernel_size), behavior=behavior)
	return out_img

def detect_rois(in_img, median_ks=9, erosion_ks=35, dilation_ks=30):

	# TODO: make in_img a ZionImage and access non-UV channels

	#Convert to grayscale (needs to access UV channel here when above change occurs):
	img_gs = rgb2gray(in_img)

	img_gs = median_filter(img_gs, median_ks)
	thresh = ski.filters.threshold_mean(img_gs)
	#TODO: adjust threshold? eg make it based on stats?
	img_bin = img_gs > thresh

	img_bin = ski.morphology.binary_erosion(img_bin, ski.morpoholgy.disk(erosion_ks))
	img_bin = ski.morphology.binary_dilation(img_bin, ski.morphology.disk(dilation_ks))
	img_bin = ski.morphology.binary_erosion(img_bin, ski.morpoholgy.disk(4))

	# TODO: add some additional channel (eg 525) that suffers from scatter/noise, and test against it to invalidate spots that include bloom of scatter.

	spot_ind, nSpots = ski.measure.label(img_bin, return_num=True)
	print(f"{nSpots} spots found")

	# TODO: get stats, centroids of spots, further invalidate improper spots. (a la cv2.connectedComponentsWithStats)

	return img_bin, spot_ind

def overlay_image(img, labels, color):
	return ski.segmentation.mark_boundaries(img, labels, color=color, mode='thick')

class ZionImage(UserDict):
	def __init__(self, lstImages, lstWavelengths, cycle=None):
		d = dict()
		for wavelength, image in zip(listWavelengths, lstImages):
			#TODO check validity (uint16, RGB, consistent sizes)
			d[wavelength] = image
		super().__init__(d)
		self.dims = image.shape[0,1]
		self.nChannels = len(lstWavelengths)
		self.cycle = cycle

	@property
	def view_4D(self):
		out_arr = np.zeros(shape=self.dims+[self.nChannels]+[3])
		for ch_idx, wl in enumerate(sorted(self.data.keys())):
			out_arr[:,:,ch_idx,:] = self.data[wl]
		return out_arr

	@property
	def view_3D(self):
		out_arr = np.zeros(shape=self.dims+[3*self.nChannels])
		for ch_idx, wl in enumerate(sorted(self.data.keys())):
			out_arr[:,:,(3*ch_idx):(3*(ch_idx+1))] = self.data[wl]
		return out_arr

	def get_8bit_view(self, wl):
		return np.right_shift(self.data[wl], 8).astype('uint8')

	# ~ def median_filter(self, wl_idx, kernel_size, method='sk2', inplace=False, timer=False):
		# ~ in_img = self.data[:,:,wl_idx]

		# ~ if timer:
			# ~ t0 = time.perf_counter()

		# ~ if method=='sk1':
			# ~ img_filt = ski.filters.median(in_img, ski.morphology.disk(kernel_size), behavior='ndimage')
		# ~ elif method=='sk2':
			# ~ img_filt = ski.filters.median(in_img, ski.morphology.disk(kernel_size), behavior='rank')
		# ~ elif method=='cv':
			# ~ print("Warning, cv method only allows kernel size of 5")
			# ~ img_filt = cv2.medianBlur(in_img, 5)
		# ~ else:
			# ~ print(f"Invalid Method {method}!")
			# ~ return None

		# ~ if timer:
			# ~ t1 = time.perf_counter()
			# ~ print(f"Elapsed time for median filtering: {t1-t0}")

		# ~ if inplace:
			# ~ self.data = img_filt
		# ~ return img_filt

# ~ class ZionDifferenceImage(ZionImage):
	# ~ def __init__(self, posImage:ZionImage, negImage:ZionImage, cycle=None):

		# ~ if cycle is None:
			# ~ self.cycle = posImage.cycle
		# ~ else:
			# ~ self.cycle = cycle

		# ~ self.wavelengths = posImage.wavelengths
		# ~ self.nChannels = posImage.nChannels
		# ~ for ind, w in enumerate(self.wavelengths):
			# ~ if w in negImage.wavelengths:
				# ~ negInd = negImage.wavelengths.index(w)
				# ~ self.data[:,:,ind] = posImage.data[:,:,ind]-negImage.data[:,:,negInd]
			# ~ else:
				# ~ self.data[:,:,ind] = posImage.data[:,:,ind]

		# ~ #ensure data is unsigned integer:
		# ~ self.data = self.data - np.min(self.data)

class ZionImageProcessor(multiprocessing.Process):
	def __init__(self):
		super().__init__()

		self._bEnable = False
		self._bShowSpots = False
		self._bShowBases = False

		self._mp_manager = multiprocessing.Manager()
		self.mp_namespace = self._mp_manager.Namespace()

		self.example_queue = self._mp_manager.Queue()
		self.example_event = self._mp_manager.Event()

	def set_enable(self, bEnable):
		self._bEnable = bEnable
		print(f"Image Processor enabled? {bEnable}")

