import os
from subprocess import call, check_call, check_output, run
from glob import glob
import numpy as np
import pandas as pd
import cv2
from skimage import filters, morphology, segmentation, measure
from collections import UserDict

from ImageProcessing.ZionBaseCaller import crosstalk_correct, display_signals, base_call, add_basecall_result_to_dataframe
from ImageProcessing.ZionData import extract_spot_data, csv_to_data, df_cols

# First, some low-level image file handling functions:
def jpg_to_raw(filepath, target_path):
    # This runs the C raw converter, which must be in the following location
    ret = run(["./raw_convert_c/convert_raw_c", filepath, target_path])
    # ~ ret = check_output(["./raw_convert_c/convert_raw_c", filepath, target_path])
    retcode = ret.returncode
    if retcode == 0:
        return ret.returncode
    else:
        raise OSError(f"raw converter failed on image {filepath} with error {retcode}")

def get_wavelength_from_filename(filepath):
    #TODO: make compatible with non-cycle-indexed files
    return filepath.split('_')[-3]

def get_cycle_from_filename(filepath):
    cycle_str = filepath.split('_')[-2]
    if cycle_str[0]=='C':
        return int(cycle_str[1:])
    else:
        return None

def get_time_from_filename(filepath):
    return int( os.path.splitext(filepath)[0].split('_')[-1] )

# Now some image processing tools or shortcuts that are useful OUTSIDE of a "ZionImage":

def rgb2gray(img, weights=None):
    return np.average(img, axis=-1, weights=weights).round().astype('uint16')

# TODO rebase to opencv to preserve 16bit images (port to C for speed?)
# (raspberry pi opencv by default doesn't deal with 16 bit images)
def median_filter(in_img, kernel_size, behavior='ndimage'): #rank?
    #TODO make for whole imageset?
    if len(in_img.shape) == 2: # grayscale
        out_img = filters.median(in_img, morphology.disk(kernel_size), behavior=behavior)
    elif len(in_img.shape) == 3: # multi-channel
        if behavior == 'cv2':
            # see above TODO
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
    '''
    This class is designed to hold a multichannel RGB imageset for a given timepoint (or cycle)
    eg one RGB per excitation channel (000, 445, 525, 590, 645, 365)
    '''
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

    def detect_rois(self, out_path, uv_wl='365', median_ks=9, erode_ks=16, dilate_ks=13, threshold_scale=1, minSize=None, maxSize=None, gray_weights=None):

        print(f"Detecting ROIs using median={median_ks}, erode={erode_ks}, dilate={dilate_ks}, scale={threshold_scale}")

        #Convert to grayscale (needs to access UV channel here when above change occurs):
        img_gs = rgb2gray(self.data[uv_wl], weights=gray_weights)

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
        for s in range(1, nSpots+1):
            size = spot_labels[spot_labels==s].shape[0]
            if maxSize is not None and size > maxSize:
                print(f"removing spot {s} with area {size} -- too large")
                spot_labels[spot_labels==s] = 0
                nSpots -= 1
            elif minSize is not None and size < minSize:
                print(f"removing spot {s} with area {size} -- too small")
                spot_labels[spot_labels==s] = 0
                nSpots -= 1

        np.save(os.path.join(out_path, f"rois.npy"), spot_labels)
        roi_img = [create_labeled_rois(spot_labels, filepath=os.path.join(out_path, f"rois"), color=[1,0,1])]
        for w_ind, w in enumerate(self.wavelengths):
            roi_img.append( create_labeled_rois(spot_labels, filepath=os.path.join(out_path, f"rois_{w}"), color=[1,0,1], img=self[w]) )
        return roi_img, spot_labels, nSpots

# This is a useful way to construct a Zion Image given a directory of images and a cycle index of interest
def get_imageset_from_cycle(new_cycle, input_dir_path, uv_wl, useDifferenceImage, useTiff=False):
    cycle_str = f"C{new_cycle:03d}"
    cycle_files = sorted(glob(os.path.join(input_dir_path, f"*_{cycle_str}_*.tiff"))) if useTiff else sorted(glob(os.path.join(input_dir_path, f"*_{cycle_str}_*.tif")))
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
