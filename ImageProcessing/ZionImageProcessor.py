import os
import time
import multiprocessing
import threading
from multiprocessing.managers import Namespace
import numpy as np
from tifffile import imread, imwrite
from matplotlib import pyplot as plt

from ImageProcessing.ZionImage import ZionImage, jpg_to_raw, get_imageset_from_cycle, get_cycle_from_filename, get_wavelength_from_filename, create_color_matrix_from_spots
from ImageProcessing.ZionData import df_cols, extract_spot_data, csv_to_data, add_basecall_result_to_dataframe
from ImageProcessing.ZionBaseCaller import project_color, base_call, crosstalk_correct, display_signals
from ImageProcessing.ZionReport import ZionReport

'''
    This module defines the runtime image handler thread (really a multiprocessing.Process). Also contains child threads which perform image processing functions.
'''

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
        self.Reports = []

        self._mp_manager = multiprocessing.Manager()
        self.mp_namespace = self._mp_manager.Namespace()
        self.stop_event = self._mp_manager.Event()

        self.mp_namespace.IP_Enable = False
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

        self.start()

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

        self._image_processing_thread = threading.Thread(
            target=self._image_handler,
            args=(self.mp_namespace, self.new_cycle_detected, self.rois_detected_event, self.basis_spots_chosen_queue, self.base_caller_queue, self.kinetics_analyzer_queue)
        )
        self._image_processing_thread.daemon = True
        self._image_processing_thread.start()

        self._base_calling_thread = threading.Thread(
            target=self._base_caller,
            args=(self.mp_namespace, self.base_caller_queue, self.bases_called_event, 5)
        )

        self._base_calling_thread.daemon = True
        self._base_calling_thread.start()

        #TODO re-enable kinetics thread once metrics are well-defined
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

            # This is the main thread for handling imagesets by cycle.

            # TODO: Program any special tasks based on first j cycles (eg fitting parameters based on fist 5 cycles)

            if new_cycle == 0:
                #TODO: do any calibration here
                print("Cycle 0 calibration (none yet)")
                continue

            else:
                currImageSet = get_imageset_from_cycle(new_cycle, in_path, uv_wl, self.bUseDifferenceImages)
                # Now currImageSet is a ZionImage

                if new_cycle == 1:
                    done = False
                    while not done:
                        while not mp_namespace.bEnable:
                            continue
                        # TODO add minSize and maxSize and gray_weights to GUI and to self.mp_namespace
                        _, self.roi_labels, self.numSpots = currImageSet.detect_rois(self.file_output_path, uv_wl=uv_wl, median_ks=self.mp_namespace.median_ks, erode_ks=self.mp_namespace.erode_ks, dilate_ks=self.mp_namespace.dilate_ks, threshold_scale=mp_namespace.threshold_scale,
                                                                                                 minSize=self.mp_namespace.minSpotSize, maxSize=self.mp_namespace.maxSpotSize, gray_weights=self.mp_namespace.grayWeights)
                        # This is to notify that rois were detected:
                        print(f"About to set roi detected event with {self.numSpots} spots")
                        rois_detected_event.set()

                        # Now wait for info on which spots are basis color spots
                        basis_spotlists = basis_chosen_queue.get() #tuple of spot labels
                        print(f"received basis spotlists: {basis_spotlists}")

                        #TODO this will turn into a tuple of lists (of spot labels)
                        if isinstance(basis_spotlists, tuple) and len(basis_spotlists)==4:
                            done = True
                        else:
                            done = False
                            rois_detected_event.clear()

                    #todo call new function for creating basis vector matrix
                    self.create_basis_vector_matrix(currImageSet, basis_spotlists, self.file_output_path)
                    print(f"\n\nBasis Vector = {self.M}, with shape {self.M.shape}\n\n")
                    # done with all cycle-1 exclusive stuff

                    base_caller_queue.put(currImageSet)

                    #TODO re-enable kinetics thread once metrics are well-defined
                    # ~ vis_cycle_files = [ f for f in cycle_files if not get_wavelength_from_filename(f)==uv_wl]
                    # ~ print(f"kineticsImageSet = {vis_cycle_files}")
                    # ~ for cf in range(0, len(vis_cycle_files), nWls):
                        # ~ wls = [ get_wavelength_from_filename(f) for f in vis_cycle_files[cf:cf+nWls] ]
                        # ~ kinetics_queue.put( ZionImage(vis_cycle_files[cf:cf+nWls], wls, cycle=new_cycle) )

                elif new_cycle > 1:
                    base_caller_queue.put(currImageSet)

                    #TODO re-enable kinetics thread once metrics are well-defined
                    # ~ vis_cycle_files = [ f for f in cycle_files if not get_wavelength_from_filename(f)==uv_wl]
                    # ~ print(f"kineticsImageSet = {vis_cycle_files}")
                    # ~ for cf in range(0, len(vis_cycle_files), nWls):
                        # ~ wls = [ get_wavelength_from_filename(f) for f in vis_cycle_files[cf:cf+nWls] ]
                        # ~ kinetics_queue.put( ZionImage(vis_cycle_files[cf:cf+nWls], wls, cycle=new_cycle) )

                else:
                    raise ValueError(f"Invalid cycle index {new_cycle}!")


    def _base_caller(self, mp_namespace : Namespace, base_caller_queue : multiprocessing.Queue, bases_called_event : multiprocessing.Event, delay : int = 0):
        '''
            This thread is currently responsible for extracting spot data, since we do multiple cycles at once with our reports.
            Later this will be the place to analyze freshly acquired data point(s) and add (in real-time) to existing result/graph.
        '''

        if delay:
            time.sleep(delay)
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

    def set_roi_params(self, median_ks, erode_ks, dilate_ks, threshold_scale, minSpotSize=None, maxSpotSize=None):
        self.mp_namespace.median_ks = median_ks
        self.mp_namespace.erode_ks = erode_ks
        self.mp_namespace.dilate_ks = dilate_ks
        self.mp_namespace.threshold_scale = threshold_scale
        self.mp_namespace.minSpotSize = minSpotSize
        self.mp_namespace.maxSpotSize = maxSpotSize
        self.mp_namespace.grayWeights = None

    def set_basecall_params(self, p, q, r=0):
        self.mp_namespace.p = p
        self.mp_namespace.q = q
        self.mp_namespace.r = r

    # ~ @property
    # ~ def enable(self):
        # ~ return self.mp_namespace.bEnable

    # ~ @enable.setter
    # ~ def enable(self, bEnable):
        # ~ self.mp_namespace.bEnable = bEnable
        # ~ print(f"Image Processor enabled? {bEnable}")

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

    def create_basis_vector_matrix(self, cycle1_imageset, basis_spotlists, out_path):
        if self.roi_labels is not None:
            self.M = create_color_matrix_from_spots(cycle1_imageset, self.roi_labels, basis_spotlists, out_path=out_path)
        else:
            print("ROIs not detected yet!")

    # TODO: replace with / move to ZionReport.py
    # Also should be using FPDF to create pdf reports
    def generate_report(self):

        reportfile = os.path.join(self.file_output_path, "report.txt")
        M = np.load(os.path.join(self.file_output_path, "M.npy"))

        # todo kinetics figure, similar to below
        # generate pre-phase-correction histograms:
        basecall_csv = os.path.join(self.file_output_path, "basecaller_spot_data.csv")
        
        basecall_pd = csv_to_data(basecall_csv)
        #TODO switch this to use project_color instead of crosstalk_correct
        signal_pre_basecall, spotlist, basecall_pd_pre = crosstalk_correct(basecall_pd, M, self.mp_namespace.ip_cycle_ind)
        basecall_pd_pre.to_csv(os.path.join(self.file_output_path, "basecaller_output_data_pre.csv"))
        f1, f2 = display_signals(signal_pre_basecall, spotlist, self.mp_namespace.ip_cycle_ind)

        #now perform phase correction
        signal_post_basecall, Qinv = base_call(signal_pre_basecall, p=self.mp_namespace.p, q=self.mp_namespace.q, r=self.mp_namespace.r)

        # ~ signal_post_basecall = np.transpose( (np.transpose(signal_pre_basecall, axes=(0,2,1)) @ Qinv)[:,:,:-1], axes=(0,2,1))
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

    ### below only for testing:
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
