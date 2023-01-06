import os
import multiprocessing
import threading
import numpy as np
import pandas as pd
import cv2
import skimage as ski
# ~ from collections import UserDict
from tifffile import imread, imwrite

from image_processing.raw_converter import jpg_to_raw, get_wavelength_from_filename, get_cycle_from_filename

class ZionImage:
	def __init__(self, image_list, cycle=None, wavelengths=None, fromFiles=True):
		if fromFiles: # image_list is a list of filepaths
			imgs = []
			dims = []
			cycles = []
			wls = []

			for i in image_list:
				img = imread(i)
				imgs.append(img)
				dims.append(img.shape)
				wls.append( get_wavelength_from_filename(i))
				#cycles.append
		else: #image_list is list of numpy arrays
			imgs = image_list
		# TODO check validity
		self.cycle = cycle
		if wavelengths is None:
			self.wavelengths = wavelengths
		else:
			self.wavelengths = wavelengths
		self.data = np.array(imgs)
		self.nChannels = len(imgs)

	def as_dict(self):
		return
		# TODO

	def as_stack(self):
		return

	def median_filter(self, wl_idx, kernel_size, method='sk1', inplace=False):
		in_img = self.data[:,:,wl_idx]
		if method=='sk1':
			img_filt = ski.filters.median(in_img, ski.morphology.disk(kernel_size), behavior='ndimage')
		elif method=='sk2':
			img_filt = ski.filters.median(in_img, ski.morphology.disk(kernel_size), behavior='rank')
		elif method=='cv':
			print("Warning, cv method only allows kernel size of 5")
			img_filt = cv2.medianBlur(in_img, 5)
		else:
			print(f"Invalid Method {method}!")
			return None
		if inplace:
			self.data = img_filt
		return img_filt

class ZionDifferenceImage(ZionImage):
	def __init__(self, posImage:ZionImage, negImage:ZionImage, cycle=None):

		if cycle is None:
			self.cycle = posImage.cycle
		else:
			self.cycle = cycle

		self.wavelengths = posImage.wavelengths
		self.nChannels = posImage.nChannels
		for ind, w in enumerate(self.wavelengths):
			if w in negImage.wavelengths:
				negInd = index(negImage.wavelengths, w)
				self.data[:,:,ind] = posImage.data[:,:,ind]-negImage.data[:,:,negInd]
			else:
				self.data[:,:,ind] = posImage.data[:,:,ind]

		#ensure data is unsigned integer:
		self.data = self.data - np.min(self.data)

class ZionImageProcessor(multiprocessing.Process):
	pass
