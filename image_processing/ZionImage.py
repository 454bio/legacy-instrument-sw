import os
from subprocess import call, check_call, check_output, run
from glob import glob
import time
import multiprocessing
import threading
import numpy as np
import pandas as pd
import cv2
from skimage import filters, morphology, segmentation, measure
from collections import UserDict
from multiprocessing.managers import Namespace
from tifffile import imread, imwrite
from matplotlib import pyplot as plt

from image_processing.raw_converter import jpg_to_raw as jpg_to_raw_py
from image_processing.ZionBase import df_cols, extract_spot_data, csv_to_data, crosstalk_correct, display_signals, base_call, add_basecall_result_to_dataframe

def jpg_to_raw(filepath, target_path):
	# ~ ret = check_output(["./raw_convert_c/convert_raw_c", filepath, target_path])
	# ~ ret = run([f"./raw_convert_c/convert_raw_c {filepath} {target_path}"], shell=True)
	ret = run(["./raw_convert_c/convert_raw_c", filepath, target_path])
	# ~ os.system(f"./raw_convert_c/convert_raw_c {filepath} {target_path}")
	#todo add timer
	# ~ print(f"Wrote {filename}.tif in _ sec"}
	retcode = ret.returncode
	if retcode == 0:
		return ret.returncode
	else:
		raise OSError(f"raw converter failed on image {filepath} with error {retcode}")

def get_wavelength_from_filename(filepath):
	return filepath.split('_')[-3]

def get_cycle_from_filename(filepath):
	cycle_str = filepath.split('_')[-2]
	if cycle_str[0]=='C':
		return int(cycle_str[1:])
	else:
		return None

def get_time_from_filename(filepath):
	return int( os.path.splitext(filepath)[0].split('_')[-1] )

# TODO rebase most skimage stuff into opencv (raspberry pi opencv by default doesn't deal with 16 bit images)
def rgb2gray(img, weights=None):
	if weights is None:
		return np.mean(img, axis=-1).round().astype('uint16')
	else:
		raise ValueError("Invalid weights option!")

def median_filter(in_img, kernel_size, behavior='ndimage'): #rank?
	#TODO make for whole imageset?
	if len(in_img.shape) == 2: # grayscale
		out_img = filters.median(in_img, morphology.disk(kernel_size), behavior=behavior)
	elif len(in_img.shape) == 3: # multi-channel
		if behavior == 'cv2':
			# TODO
			raise ValueError("Invalid behavior option!")
		else:
			for ch in range(in_img.shape[-1]):
				out_img[:,:,ch] = filters.median(in_img[:,:,ch], morphology.disk(kernel_size), behavior=behavior)
	return out_img

def create_labeled_rois(labels, filepath=None, color=[1,0,1], img=None, font=cv2.FONT_HERSHEY_SIMPLEX):
	img = np.zeros_like(labels) if img is None else img
	h,w = labels.shape
	out_img = segmentation.mark_boundaries(img, labels, color=color, outline_color=color, mode='thick')
	out_img = (255*out_img).astype('uint8')
	rp = measure.regionprops(labels)
	s_idx = 0
	for s in range(1, np.max(labels)+1):
		if labels[labels==s].size > 0:
			centroid = rp[s_idx]['centroid']
			s_idx += 1
			text = str(s)
			text_size = cv2.getTextSize(text, font,1,2)[0]
			cv2.putText(out_img, str(s), (int(centroid[1]-text_size[0]/2), int(centroid[0]+text_size[1]/2)), font, 1, (255, 0, 255), 2)
	if filepath is not None:
		cv2.imwrite(filepath+".jpg", out_img)
	return out_img

class ZionImage(UserDict):
	def __init__(self, lstImageFiles, lstWavelengths, cycle=None, subtrahends=None, bgIntensity=None):

		d = dict()
		wl_subs = [get_wavelength_from_filename(fp) for fp in subtrahends] if subtrahends is not None else []

		self.times = []
		self.filenames = dict()
		for wavelength, imagefile in zip(lstWavelengths, lstImageFiles):
			#TODO check validity (uint16, RGB, consistent sizes)
			image = imread(imagefile)
			self.filenames[wavelength] = imagefile

			if subtrahends is not None:
				if wavelength == '000':  #skip dark images
					continue
				elif wavelength in wl_subs:
					d[wavelength] = image - imread(subtrahends[wl_subs.index(wavelength)])
					self.times.append( get_time_from_filename(imagefile) )
					# ~ print(f"adding {imagefile} - {subtrahends[wl_subs.index(wavelength)]}")
					# ~ print(f"image shape: {image.shape}")
				else:
					d[wavelength] = image
					self.times.append( get_time_from_filename(imagefile) )
					# ~ print(f"adding {imagefile}")
					# ~ print(f"image shape: {image.shape}")
			else: #not using difference image
				if wavelength == '000':
					continue
				if '000' in lstWavelengths:
					d[wavelength] = image - imread(lstImageFiles[lstWavelengths.index('000')])
					self.times.append( get_time_from_filename(imagefile) )
					# ~ print(f"adding {imagefile} - {lstImageFiles[lstWavelengths.index('000')]}")
					# ~ print(f"image shape: {image.shape}")
				else:
					d[wavelength] = image
					self.times.append( get_time_from_filename(imagefile) )
					# ~ print(f"adding {imagefile}")
					# ~ print(f"image shape: {image.shape}")

		super().__init__(d)
		#TODO check that all images are same dtype, shape, and dimensionality
		self.dtype = image.dtype
		self.dims = image.shape[:2]
		self.nChannels = len(lstWavelengths)
		self.cycle = cycle
		self.time_avg = round(sum(self.times)/len(self.times))

	def get_mean_spot_vector(self, indices):
		out = []
		for k in self.data.keys():
			out.extend( np.mean(self.data[k][indices], axis=0).tolist() )
		return out

	@property
	def wavelengths(self):
		wls = self.data.keys()
		# should be no dark key in here, but just in case
		if '000' in wls:
			wls.remove('000')
		return wls

	@property
	def view_4D(self):
		out_arr = np.zeros(shape=(self.nChannels,)+self.dims+(3,), dtype=self.dtype)
		for ch_idx, wl in enumerate(sorted(self.data.keys())):
			out_arr[ch_idx,:,:,:] = self.data[wl]
		return out_arr

	@property
	def view_3D(self):
		out_arr = np.zeros(shape=self.dims+(3*self.nChannels,), dtype=self.dtype)
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

	def detect_rois(self, out_path, uv_wl='365', median_ks=9, erode_ks=16, dilate_ks=13, threshold_scale=1):

		print(f"Detecting ROIs using median={median_ks}, erode={erode_ks}, dilate={dilate_ks}, scale={threshold_scale}")

		#Convert to grayscale (needs to access UV channel here when above change occurs):
		img_gs = rgb2gray(self.data[uv_wl])

		img_gs = median_filter(img_gs, median_ks)
		thresh = threshold_scale * filters.threshold_mean(img_gs)
		#TODO: adjust threshold? eg make it based on stats?
		img_bin = img_gs > thresh

		img_bin = morphology.binary_erosion(img_bin, morphology.disk(erode_ks))
		img_bin = morphology.binary_dilation(img_bin, morphology.disk(dilate_ks))
		img_bin = morphology.binary_erosion(img_bin, morphology.disk(4))

		spot_labels, nSpots = measure.label(img_bin, return_num=True)
		print(f"{nSpots} spot candidates found")
		spot_props = measure.regionprops(spot_labels)
		# sort spot labels by centroid locations because we want to identify homopolymer spots by array coords
		# sorted left to right, top to bottom (like 
		# TODO: add some additional channel (eg 525) that suffers from scatter/noise, and test against it to invalidate spots that include bloom of scatter.
		centroids = [p.centroid for p in spot_props]
		# snew_cnew_orted(centroids, key=lambda c: [c[1], c[0])


		# TODO: get stats, centroids of spots, further invalidate improper spots.
		#for s in range(1, nSpots+1):
		#	size = spot_labels[spot_labels==s].shape[0]
		#	if size > 2500:
		#		print(f"removing spot {s} with area {size}")
		#		spot_labels[spot_labels==s] = 0
		#		nSpots -= 1

		np.save(os.path.join(out_path, f"rois.npy"), spot_labels)
		roi_img = [create_labeled_rois(spot_labels, filepath=os.path.join(out_path, f"rois"), color=[1,0,1])]
		for w_ind, w in enumerate(self.wavelengths):
			roi_img.append( create_labeled_rois(spot_labels, filepath=os.path.join(out_path, f"rois_{w}"), color=[1,0,1], img=self[w]) )
		return roi_img, spot_labels, nSpots

class ZionImageProcessor(multiprocessing.Process):

	# TODO: is this the best way to handle versions?
	IMAGE_PROCESS_VERSION = 1

	def __init__(self, gui, session_path, bJpgConverter=True, uvWavelength='365'):
		super().__init__()

		self.gui = gui
		self.session_path = session_path
		self.file_output_path = os.path.join(session_path, f"processed_images_v{self.IMAGE_PROCESS_VERSION}")
		self.raws_path = os.path.join(session_path, f"raws")

		self.roi_labels = None
		self.numSpots = None
		self.M = None

		self._mp_manager = multiprocessing.Manager()
		self.mp_namespace = self._mp_manager.Namespace()
		self.stop_event = self._mp_manager.Event()

		# TODO: a Lock, RLock, or condition to enable/disable all IP processes
		# ~ self._enable_condition = self._mp_manager.Condition()
		# ~ self._enable_lock = self._mp_manager.Lock()
		self.mp_namespace.bEnable = False
		self.mp_namespace.bConvertEnable = False

		self.bUseDifferenceImages = False
		self.mp_namespace.bShowSpots = False
		self.mp_namespace.bShowBases = False
		self.mp_namespace.ip_cycle_ind = 0
		self.mp_namespace.convert_cycle_ind = 0
		self.mp_namespace.view_cycle_ind = 0

		self.convert_files_queue = self._mp_manager.Queue()
		self.new_cycle_detected = self._mp_manager.Queue()
		self.spot_extraction_queue = self._mp_manager.Queue()

		self.rois_detected_event = self._mp_manager.Event()
		self.basis_spots_chosen_queue = self._mp_manager.Queue()

		self.base_caller_queue = self._mp_manager.Queue()
		self.bases_called_event = self._mp_manager.Event()
		self.kinetics_analyzer_queue = self._mp_manager.Queue()
		self.kinetics_analyzed_event = self._mp_manager.Event()

		self._image_viewer_queue = self._mp_manager.Queue()

	def run(self):
		self._start_child_threads()
		print("Image Processor threads started!")
		#Now wait for stop event:
		self.stop_event.wait()
		print("Received stop signal!")
		self._cleanup()

	def _cleanup(self):
		self.mp_namespace.bEnable = False

		# TODO do proper ending of each thread by sending each a null object via its queue...

		self._convert_image_thread.join(12.0)
		if self._convert_image_thread.is_alive():
			print("_convert_image_thread is still alive!")
		# ~ self._image_processing_thread.join(10.0)
		# ~ if self._image_processing_thread.is_alive():
			# ~ print("_image_processing_thread is still alive!")

		# ~ self._base_calling_thread.join(10.0)
		# ~ if self._base_calling_thread.is_alive():
			# ~ print("_base_calling_thread is still alive!")

		# ~ self._kinetics_thread.join(10.0)
		# ~ if self._kinetics_thread.is_alive():
			# ~ print("_kinetics_thread is still alive!")

	def _start_child_threads(self):

		self._convert_image_thread = threading.Thread(
			target=self._convert_jpeg,
			args=(self.mp_namespace, self.convert_files_queue, self.new_cycle_detected, self.spot_extraction_queue)
		)
		self._convert_image_thread.daemon = True
		self._convert_image_thread.start()

		# ~ self._image_processing_thread = threading.Thread(
			# ~ target=self._image_handler,
			# ~ args=(self.mp_namespace, self.new_cycle_detected, self.rois_detected_event, self.basis_spots_chosen_queue, self.base_caller_queue, self.kinetics_analyzer_queue)
		# ~ )
		# ~ self._image_processing_thread.daemon = True
		# ~ self._image_processing_thread.start()

		# ~ self._base_calling_thread = threading.Thread(
			# ~ target=self._base_caller,
			# ~ args=(self.mp_namespace, self.base_caller_queue, self.bases_called_event)
		# ~ )

		# ~ self._base_calling_thread.daemon = True
		# ~ self._base_calling_thread.start()

		# ~ self._kinetics_thread = threading.Thread(
			# ~ target=self._kinetics_analyzer,
			# ~ args=(self.mp_namespace, self.kinetics_analyzer_queue, self.kinetics_analyzed_event)
		# ~ )

		# ~ self._kinetics_thread.daemon = True
		# ~ self._kinetics_thread.start()

		# ~ #todo: same for other threads

	def _convert_jpeg(self, mp_namespace : Namespace, image_file_queue : multiprocessing.Queue, new_cycle_queue : multiprocessing.Queue, output_queue : multiprocessing.Queue):
		print("Starting _convert_jpeg thread")
		mp_namespace.convert_cycle_ind = 0
		lock = False
		if not os.path.isdir(self.raws_path):
			os.makedirs(self.raws_path)
			print(f"Creating directory {self.raws_path} for raws")
		while True:
			filepath_args = image_file_queue.get()
			filepath = filepath_args[0]
			if filepath is None: # basically a stop signal
				print("_convert_jpeg -- received stop signal!")
				break
			if mp_namespace.bConvertEnable:
				print(f"Converting jpeg {filepath}")
				filename = os.path.splitext(os.path.basename(filepath))[0]
				jpg_to_raw(filepath, os.path.join(self.raws_path, filename+".tif"))
				cycle = get_cycle_from_filename(filename)
				if cycle is not None:
					if cycle != mp_namespace.convert_cycle_ind:
						if mp_namespace.convert_cycle_ind > 0:
							new_cycle_queue.put(mp_namespace.convert_cycle_ind)
							print(f"_convert_jpg thread: New cycle {mp_namespace.convert_cycle_ind} event being set")
						mp_namespace.convert_cycle_ind = cycle
				else:
					if not lock and mp_namespace.convert_cycle_ind > 0:
						new_cycle_queue.put(mp_namespace.convert_cycle_ind)
						print(f"_convert_jpg thread: Cycle {mp_namespace.convert_cycle_ind} event being set")
						lock = True # only do this once
			else:
				while not mp_namespace.bConvertEnable:
					continue
				print(f"Converting jpeg {filepath} after wait")
				filename = os.path.splitext(os.path.basename(filepath))[0]
				jpg_to_raw(filepath, os.path.join(self.raws_path, filename+".tif"))

	def _image_handler(self, mp_namespace : Namespace, image_ready_queue : multiprocessing.Queue, rois_detected_event, basis_chosen_queue, base_caller_queue, kinetics_queue):
		''' High level handler... will use cycle number (before incrementing)
			to check raws directory for cycles, make decisions on where to send imageset
		'''

		mp_namespace.ip_cycle_ind = 0
		in_path = self.raws_path
		out_path = self.file_output_path
		if not os.path.isdir(self.file_output_path):
			os.makedirs(self.file_output_path)
			print(f"Creating directory {self.file_output_path} for processing")
		rois_detected_event.clear()
		# ~ lock = False

		#TODO: this should come from a ZionLED property or something
		uv_wl = '365'

		while True:
			new_cycle = image_ready_queue.get()
			while not mp_namespace.bEnable:
				continue
			print(f"_image_handler thread: begin processing new cycle {new_cycle}")
			self.mp_namespace.ip_cycle_ind = new_cycle
			if new_cycle == 0:
				#TODO: do any calibration here
				print("Cycle 0 calibration (none yet)")
				continue

			else:
				# TODO: clean this up, allow for no cycles?
				cycle_str = f"C{new_cycle:03d}"
				cycle_files = sorted(glob(os.path.join(in_path, f"*_{cycle_str}_*.tif")))
				# ~ print(f"cycle {new_cycle}'s file list: {cycle_files}")
				wls = list(set(sorted([get_wavelength_from_filename(f) for f in cycle_files])))
				# ~ print(f"cycle {new_cycle}'s wavelengths: {wls}")
				if not uv_wl in wls:
					raise ValueError(f"No {uv_wl} images in cycle {new_cycle}!")
				nWls = len(wls)-1

				# Find earliest images of UV wavelength, but the latest of others:
				imgFileList = []
				diffImgSubtrahends = []

				for wl in wls:
					if wl==uv_wl:
						imgFileList.append(cycle_files[[f"_{wl}_" in fp for fp in cycle_files].index(True)]) #first uv image
					else:
						lst_tmp = [f"_{wl}_" in fp for fp in cycle_files]
						imgFileList.append(cycle_files[ len(lst_tmp) - lst_tmp[-1::-1].index(True) - 1]) # last vis led image
						diffImgSubtrahends.append(cycle_files[[f"_{wl}_" in fp for fp in cycle_files].index(True)]) # first vis led image
				currImageSet = ZionImage(imgFileList, wls, cycle=new_cycle, subtrahends=diffImgSubtrahends) if self.bUseDifferenceImages else ZionImage(imgFileList, wls, cycle=new_cycle)

				if new_cycle == 1:
					done = False
					while not done:
						while not mp_namespace.bEnable:
							continue
						roi_imgs = self.detect_rois( currImageSet )
						rois_detected_event.set()
						basis_spots = basis_chosen_queue.get() #tuple of spot labels
						if isinstance(basis_spots, tuple) and len(basis_spots)==4:
							done = True
						else:
							done = False
							rois_detected_event.clear()
					#this is a real set of basis spots
					self.create_basis_vector_matrix(currImageSet, basis_spots)
					print(f"\n\nBasis Vector = {self.M}, with shape {self.M.shape}\n\n")
					base_caller_queue.put(currImageSet)
					vis_cycle_files = [ f for f in cycle_files if not get_wavelength_from_filename(f)==uv_wl]
					# ~ print(f"kineticsImageSet = {vis_cycle_files}")
					for cf in range(0, len(vis_cycle_files), nWls):
						wls = [ get_wavelength_from_filename(f) for f in vis_cycle_files[cf:cf+nWls] ]
						kinetics_queue.put( ZionImage(vis_cycle_files[cf:cf+nWls], wls, cycle=new_cycle) )

				elif new_cycle > 1:
					base_caller_queue.put(currImageSet)
					# ~ print(f"\n\nBasis Vector = {self.M}, with shape {self.M.shape}\n\n")
					vis_cycle_files = [ f for f in cycle_files if not get_wavelength_from_filename(f)==uv_wl]
					# ~ print(f"kineticsImageSet = {vis_cycle_files}")
					for cf in range(0, len(vis_cycle_files), nWls):
						wls = [ get_wavelength_from_filename(f) for f in vis_cycle_files[cf:cf+nWls] ]
						kinetics_queue.put( ZionImage(vis_cycle_files[cf:cf+nWls], wls, cycle=new_cycle) )

				else:
					raise ValueError(f"Invalid cycle index {new_cycle}!")


	def _base_caller(self, mp_namespace : Namespace, base_caller_queue : multiprocessing.Queue, bases_called_event : multiprocessing.Event):

		csvfile = os.path.join(self.file_output_path, "basecaller_spot_data.csv")
		print(f"_base_caller_thread: creating csv file {csvfile}")
		with open(csvfile, "w") as f:
			f.write(','.join(df_cols)+'\n')
		while True:
			imageset = base_caller_queue.get()
			while not mp_namespace.bEnable:
				continue
			if self.roi_labels is None or self.numSpots is None:
				raise RunTimeError("ROIs haven't been detected yet!")
			elif self.numSpots==0:
				raise ValueError("No spots to use in basecalling!")
			else:
				spot_data = extract_spot_data(imageset, self.roi_labels, csvFileName = csvfile)
				# ~ print(f"roi label image = {self.roi_labels}")

	def _kinetics_analyzer(self, mp_namespace : Namespace, kinetics_queue : multiprocessing.Queue, kinetics_analyzed_event : multiprocessing.Event):

		csvfile = os.path.join(self.file_output_path, "kinetics_spot_data.csv")
		print(f"_base_caller_thread: creating csv file {csvfile}")
		with open(csvfile, "w") as f:
			f.write(','.join(df_cols)+'\n')
		while True:
			imageset = kinetics_queue.get()
			while not mp_namespace.bEnable:
				continue
			if self.roi_labels is None or self.numSpots is None:
				raise RunTimeError("ROIs haven't been detected yet!")
			elif self.numSpots==0:
				raise ValueError("No spots to use in kinetics!")
			else:
				spot_data = extract_spot_data(imageset, self.roi_labels, csvFileName = csvfile, kinetic=True)
				# ~ print(f"adding kinetics data to {csvfile}")


	def _image_view_thread(self, mp_namespace : Namespace, image_viewer_queue : multiprocessing.Queue ):
		return

	def add_to_convert_queue(self, fpath):
		self.convert_files_queue.put_nowait( (fpath,) )
		# ~ self.convert_files_queue.put( (fpath,) )

	def set_roi_params(self, median_ks, erode_ks, dilate_ks, threshold_scale):
		self.mp_namespace.median_ks = median_ks
		self.mp_namespace.erode_ks = erode_ks
		self.mp_namespace.dilate_ks = dilate_ks
		self.mp_namespace.threshold_scale = threshold_scale

	def set_basecall_params(self, p, q):
		self.mp_namespace.p = p
		self.mp_namespace.q = q

	@property
	def enable(self):
		return self.mp_namespace.bEnable

	@enable.setter
	def enable(self, bEnable):
		self.mp_namespace.bEnable = bEnable
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

	def detect_rois(self, in_img, uv_wl='365'):

		print(f"Detecting ROIs using median={self.mp_namespace.median_ks}, erode={self.mp_namespace.erode_ks}, dilate={self.mp_namespace.dilate_ks}, scale={self.mp_namespace.threshold_scale}")

		#Convert to grayscale (needs to access UV channel here when above change occurs):
		img_gs = rgb2gray(in_img.data[uv_wl])

		img_gs = median_filter(img_gs, self.mp_namespace.median_ks)
		thresh = self.mp_namespace.threshold_scale * filters.threshold_mean(img_gs)
		#TODO: adjust threshold? eg make it based on stats?
		img_bin = img_gs > thresh

		img_bin = morphology.binary_erosion(img_bin, morphology.disk(self.mp_namespace.erode_ks))
		img_bin = morphology.binary_dilation(img_bin, morphology.disk(self.mp_namespace.dilate_ks))
		img_bin = morphology.binary_erosion(img_bin, morphology.disk(4))

		spot_labels, nSpots = measure.label(img_bin, return_num=True)
		print(f"{nSpots} spot candidates found")
		spot_props = measure.regionprops(spot_labels)
		# sort spot labels by centroid locations because we want to identify homopolymer spots by array coords
		# sorted left to right, top to bottom (like 
		# TODO: add some additional channel (eg 525) that suffers from scatter/noise, and test against it to invalidate spots that include bloom of scatter.
		centroids = [p.centroid for p in spot_props]
		# snew_cnew_orted(centroids, key=lambda c: [c[1], c[0])


		# TODO: get stats, centroids of spots, further invalidate improper spots.
		for s in range(1, nSpots+1):
			size = spot_labels[spot_labels==s].shape[0]
			if size > 2500:
				print(f"removing spot {s} with area {size}")
				spot_labels[spot_labels==s] = 0
				nSpots -= 1

		self.roi_labels = spot_labels
		np.save(os.path.join(self.file_output_path, f"rois.npy"), spot_labels)
		self.numSpots = nSpots
		roi_img = [create_labeled_rois(self.roi_labels, filepath=os.path.join(self.file_output_path, f"rois"), color=[1,0,1])]
		for w_ind, w in enumerate(in_img.wavelengths):
			roi_img.append( create_labeled_rois(self.roi_labels, filepath=os.path.join(self.file_output_path, f"rois_{w}"), color=[1,0,1], img=in_img[w]) )
		return roi_img

	def create_basis_vector_matrix(self, cycle1_imageset, spot_indices):
		if self.roi_labels is not None:
			self.M = np.array([ cycle1_imageset.get_mean_spot_vector( self.roi_labels==basis_spot ) for basis_spot in spot_indices ]).T
			np.save(os.path.join(self.file_output_path, f"M.npy"), self.M)
		else:
			print("ROIs not detected yet!")

	def generate_report(self):
		#todo kinetics
		reportfile = os.path.join(self.file_output_path, "report.txt")
		M = np.load(os.path.join(self.file_output_path, "M.npy"))

		# todo kinetics figure, similar to below
		# generate pre-phase-correction histograms:
		basecall_csv = os.path.join(self.file_output_path, "basecaller_spot_data.csv")
		basecall_pd = csv_to_data(basecall_csv)
		signal_pre_basecall, spotlist, basecall_pd_pre = crosstalk_correct(basecall_pd, M, self.mp_namespace.ip_cycle_ind)
		basecall_pd_pre.to_csv(os.path.join(self.file_output_path, "basecaller_output_data_pre.csv"))
		f1, f2 = display_signals(signal_pre_basecall, spotlist, self.mp_namespace.ip_cycle_ind)
		#now perform phase correction

		#Transition matrix is numCycles+1 x numCycles+1
		P  = np.diag((self.mp_namespace.ip_cycle_ind+1)*[self.mp_namespace.p])
		P += np.diag((self.mp_namespace.ip_cycle_ind)*[1-self.mp_namespace.p-self.mp_namespace.q], k=1)
		P += np.diag((self.mp_namespace.ip_cycle_ind-1)*[self.mp_namespace.q], k=2)

		Q = np.zeros(shape=(self.mp_namespace.ip_cycle_ind,self.mp_namespace.ip_cycle_ind))
		for t in range(self.mp_namespace.ip_cycle_ind):
			Q[:,t] = np.linalg.matrix_power(P,t+1)[0,1:]
		Qinv = np.linalg.inv(Q)

		signal_post_basecall = np.transpose( (np.transpose(signal_pre_basecall, axes=(0,2,1)) @ Qinv)[:,:,:-1], axes=(0,2,1))
		basecall_pd_post = add_basecall_result_to_dataframe(signal_post_basecall, basecall_pd)
		basecall_pd_post.to_csv(os.path.join(self.file_output_path, "basecaller_output_data_post.csv"))

		# ~ base_call
		f3,f4 = display_signals(signal_post_basecall, spotlist, self.mp_namespace.ip_cycle_ind-1)

		# ~ plt.show() #this hangs
		for f_idx, f in enumerate(f1):
			f.savefig(os.path.join(self.file_output_path, f"Purity Pre-Phase {f_idx+1}.png"))
		for f_idx, f in enumerate(f2):
			f.savefig(os.path.join(self.file_output_path, f"Signal Pre-Phase {f_idx+1}.png"))
		for f_idx, f in enumerate(f3):
			f.savefig(os.path.join(self.file_output_path, f"Purity Post-Phase {f_idx+1}.png"))
		for f_idx, f in enumerate(f4):
			f.savefig(os.path.join(self.file_output_path, f"Signal Post-Phase {f_idx+1}.png"))

		# ~ f3.savefig(os.path.join(self.file_output_path, "Signal Post-Phase.png")
		# ~ f4.savefig(os.path.join(self.file_output_path, "Signal Post-Phase.png")

		with open(reportfile, 'w') as f:
			if self.bUseDifferenceImages:
				print(f"Difference = Temporal", file=f)
			else:
				print(f"Difference = Dark", file=f)

			print(f"Median Filter Kernel Size = {self.mp_namespace.median_ks}", file=f)
			print(f"Erosion Kernel Size = {self.mp_namespace.erode_ks}", file=f)
			print(f"Dilation Kernel Size = {self.mp_namespace.dilate_ks}", file=f)
			print(f"Mean Threshold Scale Factor = {self.mp_namespace.threshold_scale}", file=f)
			print(f"ROI labels at {os.path.join(self.file_output_path, 'rois.jpg')}", file=f)
			print(f"'Cross-talk' matrix M = {M}", file=f)
			#todo list where output csv is?
			print(f"Pre-phase corrected Purity at {os.path.join(self.file_output_path, 'Purity Pre-Phase.png')}", file=f)
			print(f"Pre-phase corrected Signal {os.path.join(self.file_output_path, 'Signal Pre-Phase.png')}", file=f)
			print(f"Base-caller p = {self.mp_namespace.p}", file=f)
			print(f"Base-caller q = {self.mp_namespace.q}", file=f)
			print(f"Post-phase corrected Purity at {os.path.join(self.file_output_path, 'Purity Post-Phase.png')}", file=f)
			print(f"Post-phase corrected Signal {os.path.join(self.file_output_path, 'Signal Post-Phase.png')}", file=f)

	### for testing:
	def do_test(self):
		#todo kinetics
		# ~ self.mp_namespace.ip_cycle_ind
		basecall_csv = os.path.join("/home/pi/Desktop/zion/sessions/20230131_0955_TS_0192/processed_images_v1", "basecaller_spot_data.csv")
		#todo print options, M, and roi labels to text file?
		M = np.load(os.path.join("/home/pi/Desktop/zion/sessions/20230131_0955_TS_0192/processed_images_v1", "M.npy"))
		basecall_pd = csv_to_data(basecall_csv)
		signal_pre_basecall, spotlist, basecall_pd = crosstalk_correct(basecall_pd, M, 2)
		basecall_pd.to_csv(os.path.join(self.file_output_path, "basecaller_output_data.csv"))
		display_signals(signal_pre_basecall, spotlist, 2)

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

def get_imageset_from_cycle(new_cycle, input_dir_path, uv_wl, useDifferenceImage):
	cycle_str = f"C{new_cycle:03d}"
	cycle_files = sorted(glob(os.path.join(input_dir_path, f"*_{cycle_str}_*.tif")))
	wls = list(set(sorted([get_wavelength_from_filename(f) for f in cycle_files])))
	if not uv_wl in wls:
		raise ValueError(f"No {uv_wl} images in cycle {new_cycle}!")
	nWls = len(wls)-1
	imgFileList = []
	diffImgSubtrahends = []
	for wl in wls:
		if wl==uv_wl:
			imgFileList.append(cycle_files[[f"_{wl}_" in fp for fp in cycle_files].index(True)]) #first uv image
		else:
			lst_tmp = [f"_{wl}_" in fp for fp in cycle_files]
			imgFileList.append(cycle_files[ len(lst_tmp) - lst_tmp[-1::-1].index(True) - 1]) # last vis led image
			diffImgSubtrahends.append(cycle_files[[f"_{wl}_" in fp for fp in cycle_files].index(True)]) # first vis led image
	currImageSet = ZionImage(imgFileList, wls, cycle=new_cycle, subtrahends=diffImgSubtrahends) if useDifferenceImage else ZionImage(imgFileList, wls, cycle=new_cycle)
	return currImageSet
