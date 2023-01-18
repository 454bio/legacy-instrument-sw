import os, time
import multiprocessing
import threading
import numpy as np
import pandas as pd
import cv2
import skimage as ski
from collections import UserDict
from multiprocessing.managers import Namespace
from tifffile import imread, imwrite
from matplotlib import pyplot as plt

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
	def __init__(self, lstImageFiles, lstWavelengths, cycle=None):
		d = dict()
		for wavelength, imagefile in zip(lstWavelengths, lstImageFiles):
			#TODO check validity (uint16, RGB, consistent sizes)
			image = imread(imagefile)
			d[wavelength] = image
		super().__init__(d)
		self.dims = image.shape[:2]
		self.nChannels = len(lstWavelengths)
		self.cycle = cycle

	@property
	def view_4D(self):
		out_arr = np.zeros(shape=(self.nChannels,)+self.dims+(3,), dtype='uint16')
		for ch_idx, wl in enumerate(sorted(self.data.keys())):
			out_arr[ch_idx,:,:,:] = self.data[wl]
		return out_arr

	@property
	def view_3D(self):
		out_arr = np.zeros(shape=self.dims+[3*self.nChannels], dtype='uint16')
		for ch_idx, wl in enumerate(sorted(self.data.keys())):
			out_arr[:,:,(3*ch_idx):(3*(ch_idx+1))] = self.data[wl]
		return out_arr

	@property
	def view_8bit(self):
		#contingent on being 16bit data
		# ~ print(self.
		img_8b = np.right_shift(self.view_4D, 8).astype('uint8')
		return img_8b

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
	def __init__(self, gui):
		super().__init__()

		self.gui = gui
		self._mp_manager = multiprocessing.Manager()
		self.mp_namespace = self._mp_manager.Namespace()
		self.stop_event = self._mp_manager.Event()

		self.mp_namespace._bEnable = False
		self.mp_namespace._bShowSpots = False
		self.mp_namespace._bShowBases = False
		self.mp_namespace.cycle_ind = 0

		self.rois_detected_event = self._mp_manager.Event()
		self.imageset_processed_event = self._mp_manager.Event()
		self.image_process_queue = self._mp_manager.Queue()
		self._image_viewer_queue = self._mp_manager.Queue()

	@property
	def enable(self):
		return self.mp_namespace._bEnable

	@enable.setter
	def enable(self, bEnable):
		self.mp_namespace._bEnable = bEnable
		print(f"Image Processor enabled? {bEnable}")

	@property
	def show_spots(self):
		return self.mp_namespace._bShowSpots

	@show_spots.setter
	def show_spots(self, bEnable):
		if bEnable:
			if self.rois_detected_event.is_set():
				self.mp_namespace._bShowSpots = bEnable
				print("Spots/ROIs view enabled")
			else:
				print("ROIs not detected yet!")
		else:
			self.mp_namespace._bShowSpots = bEnable
			print("Spots/ROIs view disabled")

	@property
	def show_bases(self):
		return self.mp_namespace._bShowBases

	@show_bases.setter
	def show_bases(self, bEnable):
		#TODO: check whether bases are called/ready
		self.mp_namespace._bShowBases = bEnable
		print(f"View Spots enabled? {bEnable}")

	def run(self):
		self._start_child_threads()
		print("Image Processor threads started!")
		#Now wait for stop event:
		self.stop_event.wait()
		print("Received stop signal!")
		self._cleanup()

	def _start_child_threads(self):

		self._image_processing_handle = threading.Thread(
			target=self._image_processing_thread,
			args=(self.mp_namespace, self.image_process_queue, self.imageset_processed_event)
		)
		self._image_processing_handle.daemon = True
		self._image_processing_handle.start()

		#todo: same for image view thread

	def _cleanup():
		self.enable = False
		self._image_processing_handle.join(1.0)
		if self._image_processing_handle.is_alive():
			print("_image_processing_thread is still alive!")

		#TODO same for image view thread

	def _image_processing_thread(self, mp_namespace : Namespace, image_process_queue : multiprocessing.Queue, done_event : multiprocessing.Event ):

		while True:
			imageset = image_process_queue.get() #get image set here
			# mark if imageset is first of the cycle (or last?)
			if self.enable:
				# ~ cycle = self.mp_namespace.cycle_ind + 1

				# Todo: Do processing
				done_event.set()
				# ~ self.mp_namespace.cycle_ind += 1

			else:
				while not self.enable:
					continue
				# ~ cycle = self.mp_namespace.cycle_ind + 1

				#Todo: Do processing
				done_event.set()
				# ~ self.mp_namespace.cycle_int +=1

	def _image_view_thread(self, mp_namespace : Namespace, image_viewer_queue : multiprocessing.Queue ):
		return


	# for testing:
	def do_test(self):
		filelist = ['/home/pi/Desktop/zion/rois.tiff']
		wavelengths = ['525']
		test_img = ZionImage(filelist, wavelengths, cycle=1)
		self.gui.IpViewWrapper.images = test_img.view_4D

	def do_something(self):
		filelist = [os.path.join("/home/pi/Desktop/zion/image_sets/S24/cycle1", fname)
						for fname in ["00000007_001A_00007_645_000597170.tif",
									  "00000008_001A_00008_590_000598382.tif",
									  "00000009_001A_00009_525_000599462.tif",
									  "00000010_001A_00010_445_000600526.tif",
									  "00000011_001A_00011_365_000601578.tif",
									 ]
					]
		wavelengths = [get_wavelength_from_filename(fn) for fn in filelist]
		test_img = ZionImage(filelist, wavelengths, cycle=1)
		# ~ print("Zion Image Loaded.")
		print("Attempting to paint to screen.")
		self.gui.IpViewWrapper.images = test_img.view_8bit
		# ~ plt.imshow(test_img['525'])
		return


