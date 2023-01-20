import os
from glob import glob
import time
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

from image_processing.raw_converter import jpg_to_raw, get_wavelength_and_cycle_from_filename

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

def overlay_image(img, labels, color):
	return ski.segmentation.mark_boundaries(img, labels, color=color, mode='thick')

class ZionImage(UserDict):
	def __init__(self, lstImageFiles, lstWavelengths, cycle=None, subtrahends=None):
		d = dict()
        if subtrahends is not None:
            wl_subs = [get_wavelength_from_file(fp) for fp in subtrahends]
		for wavelength, imagefile in zip(lstWavelengths, lstImageFiles):
			#TODO check validity (uint16, RGB, consistent sizes)
			image = imread(imagefile)
            if subtrahends is not None:
                if wavelength in wl_subs:
                    d[wavelength] = image - imread(subtrahends[wl_subs.index(wavelength)])
                else:
                    d[wavelength] = image
            else:
                d[wavelength] = image
		super().__init__(d)
		self.dtype = image.dtype
		self.dims = image.shape[:2]
		self.nChannels = len(lstWavelengths)
		self.cycle = cycle

	@property
	def view_4D(self):
		out_arr = np.zeros(shape=(self.nChannels,)+self.dims+(3,), dtype=self.dtype)
		for ch_idx, wl in enumerate(sorted(self.data.keys())):
			out_arr[ch_idx,:,:,:] = self.data[wl]
		return out_arr

	@property
	def view_3D(self):
		out_arr = np.zeros(shape=self.dims+[3*self.nChannels], dtype=self.dtype)
		for ch_idx, wl in enumerate(sorted(self.data.keys())):
			out_arr[:,:,(3*ch_idx):(3*(ch_idx+1))] = self.data[wl]
		return out_arr

	@property
	def view_8bit(self):
		#contingent on being 16bit data
		if self.dtype == 'uint16':
			img_8b = np.right_shift(self.view_4D, 8).astype('uint8')
		elif self.dtype =='uint8':
			img_8b = self.view_4D
		else:
			raise ValueError(f"Invalid datatype given!")
		return img_8b

    def detect_rois(self, uv_wl='365', median_ks=9, erosion_ks=35, dilation_ks=30):

        #Convert to grayscale (needs to access UV channel here when above change occurs):
        img_gs = rgb2gray(self.data[uv_wl])

        img_gs = median_filter(img_gs, median_ks)
        thresh = ski.filters.threshold_mean(img_gs)
        #TODO: adjust threshold? eg make it based on stats?
        img_bin = img_gs > thresh

        img_bin = ski.morphology.binary_erosion(img_bin, ski.morpoholgy.disk(erosion_ks))
        img_bin = ski.morphology.binary_dilation(img_bin, ski.morphology.disk(dilation_ks))
        img_bin = ski.morphology.binary_erosion(img_bin, ski.morpoholgy.disk(4))

        # TODO: add some additional channel (eg 525) that suffers from scatter/noise, and test against it to invalidate spots that include bloom of scatter.

        spot_ind, nSpots = ski.measure.label(img_bin, return_num=True)
        print(f"{nSpots} spot candidates found")

        # TODO: get stats, centroids of spots, further invalidate improper spots. (a la cv2.connectedComponentsWithStats)

        return img_bin, spot_ind

	def median_filter(self, wl_idx, kernel_size, method='sk2', inplace=False, timer=False):
        # TODO: necesary?
    
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
        return

class ZionImageProcessor(multiprocessing.Process):

	#TODO: add jpg_converter thread here!

	# TODO: is this the best way to handle versions?
	IMAGE_PROCESS_VERSION = 1

	def __init__(self, gui, session_path):
		super().__init__()

		self.gui = gui

		self.session_path = session_path
		self.file_output_path = os.path.join(session_path, f"processed_images_v{self.IMAGE_PROCESS_VERSION}")
		if not os.isdir(self.file_output_path):
			os.makedirs(self.file_output_path)
			print(f"Creating directory {self.file_output_path} for image processing file output")

		self._mp_manager = multiprocessing.Manager()
		self.mp_namespace = self._mp_manager.Namespace()
		self.stop_event = self._mp_manager.Event()

		self.mp_namespace._bEnable = False
		self.mp_namespace._bShowSpots = False
		self.mp_namespace._bShowBases = False
		self.mp_namespace.ip_cycle_ind = 0
		self.mp_namespace.view_cycle_ind = 0

		self.new_cycle_detected = self._mp_manager.Event()
		# ~ self.output_data_ready_event = self._mp_manager.Event()

		self.rois_detected_event = self._mp_manager.Event()
		self.imageset_processed_event = self._mp_manager.Event()
		self.image_process_queue = self._mp_manager.Queue()
		self._image_viewer_queue = self._mp_manager.Queue()

	def run(self):
		self._start_child_threads()
		print("Image Processor threads started!")
		#Now wait for stop event:
		self.stop_event.wait()
		print("Received stop signal!")
		self._cleanup()

	def _cleanup():
		self.enable = False
		self._image_processing_handle.join(1.0)
		if self._image_processing_handle.is_alive():
			print("_image_processing_thread is still alive!")
		#TODO same for image view thread

	def _start_child_threads(self):

		self._image_processing_handle = threading.Thread(
			target=self._image_processing_handler,
			args=(self.mp_namespace, self.image_process_queue, self.imageset_processed_event)
		)
		self._image_processing_handle.daemon = True
		self._image_processing_handle.start()
		#todo: same for image view thread

	def _image_processing_handler(self, mp_namespace : Namespace, image_process_queue : multiprocessing.Queue, done_event : multiprocessing.Event ):
		''' High level handler... will use cycle number (before incrementing)
			to check raws directory for cycles, make decisions on where to send imageset
		'''

		mp_namespace.ip_cycle_ind = 0
		in_path = os.path.join(self.session_path, "raws")
		out_path = self.file_output_path

		#TODO: this should come from a ZionLED property or something
		uv_wl = '365'
		bg_wl = '000'

		while True:

			self.new_cycle_detected.wait()
			cycle_ind = mp_namespace.ip_cycle_ind
			cycle_str = f"C{cycle_ind:03d}"
			cycle_files = sorted(glob(in_path, '*cycle_str*.tif'))
			wls = unique([get_wavelength_from_file(f) for f in files_this_cycle])
			if not uv_wl in wls:
					raise ValueError(f"No {uv_wl} images in cycle {cycle_ind}!")

			if cycle_ind == 0:
				#TODO: do any calibration here
				mp_namespace.ip_cycle_ind += 1

			elif cycle_ind == 1:
				# Find earliest images of UV wavelength, but the latest of others:
				imgFileList = []
				diffImgSubtrahends = []
				for wl in wls:
					if wl==uv_wl:
						fileList.append(cycle_files[[f"_{wl}_" in fp for fp in cycle_files].index(True)])
					else:
						lst_tmp = [f"_{wl}_" in fp for fp in cycle_files]
						fileList.append(cycle_files[ len(lst_tmp) - lst_tmp[-1::-1].index(True) - 1]) # last vis led image
						diffImgSubtrahends.append(cycle_files[[f"_{wl}_" in fp for fp in cycle_files].index(True)])
				currImageSet = ZionImage(imgFileList, wls, cycle=cycle_ind, subtrahends=diffImgSubtrahends) if self.bUseDifferenceImages else ZionImage(imgFileList, wls, cycle=cycle_ind)
				#TODO send to ROI detector

				#TODO send to base-caller

                #TODO do kinetics analysis

				mp_namespace.ip_cycle_ind += 1

			elif cycle_ind > 1
				# do what we did before but no ROI stuff
				imgFileList = []
				diffImgSubtrahends = []
				for wl in wls:
					if wl==uv_wl:
						fileList.append(cycle_files[[f"_{wl}_" in fp for fp in cycle_files].index(True)])
					else:
						lst_tmp = [f"_{wl}_" in fp for fp in cycle_files]
						fileList.append(cycle_files[ len(lst_tmp) - lst_tmp[-1::-1].index(True) - 1]) # last vis led image
						diffImgSubtrahends.append(cycle_files[[f"_{wl}_" in fp for fp in cycle_files].index(True)])
				currImageSet = ZionImage(imgFileList, wls, cycle=cycle_ind, subtrahends=diffImgSubtrahends) if self.bUseDifferenceImages else ZionImage(imgFileList, wls, cycle=cycle_ind)
				#TODO: send to base caller

                #TODO do kinetics analysis

				mp_namespace.ip_cycle_ind += 1

			else:
				raise ValueError(f"Invalid cycle index {mp_namespace.ip_cycle_ind}!")

#			imageset = image_process_queue.get() #get image set here
			# mark if imageset is first of the cycle (or last?)
			if self.enable:
				# ~ cycle = self.mp_namespace.ip_cycle_ind + 1

				# Todo: Do processing
				done_event.set()
				# ~ self.mp_namespace.ip_cycle_ind += 1

			else:
				while not self.enable:
					continue
				# ~ cycle = self.mp_namespace.ip_cycle_ind + 1

				#Todo: Do processing
				done_event.set()
				# ~ self.mp_namespace.cycle_int +=1

	def _image_view_thread(self, mp_namespace : Namespace, image_viewer_queue : multiprocessing.Queue ):
		return

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



	### for testing:
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


