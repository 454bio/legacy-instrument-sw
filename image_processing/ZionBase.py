
from collections import UserDict, UserString
import numpy as np
import pandas as pd
from skimage.color import rgb2hsv
from matplotlib import pyplot as plt

# ~ from image_processing.ZionImage import ZionImage

BASES = ('A', 'C', 'G', 'T')#, 'S') #todo: include scatter color as a base?
df_cols = [ "roi",
            "wavelength",
            "mean_R",
            "mean_G",
            "mean_B",
            "median_R",
            "median_G",
            "median_B",
            "mean_H",
            "mean_S",
            "mean_V",
            "median_H",
            "median_S",
            "median_V",
            "std_R",
            "std_G",
            "std_B",
            "std_H",
            "std_S",
            "std_V",
            "min_R",
            "min_G",
            "min_B",
            "max_R",
            "max_G",
            "max_B",
            ]

class ZionBase(UserString):

    Names = ('A', 'C', 'G', 'T', '!')

    def __init__(self, char):
        if not isinstance(char, str):
            raise TypeError("Base must be a character!")
        elif len(char) != 1:
            raise ValueError("Base must be a one-character string!")
        elif char not in ZionBase.Names:
            raise ValueError(f"Base must be valid character (not '{char}')!")
        else:
            super().__init__(char)

def extract_spot_data(img, roi_labels:np.array, csvFileName = None):
#bUseMedian:bool = False, bUseHsv:bool = False, ):
    ''' takes in a ZionImage (ie a dict of RGB images) and a 3D image of spot labels. Optionally writes a csv file.
        Outputs a pandas dataframe containing all data.
    '''

    numSpots = np.max(roi_labels)
    df_total = pd.DataFrame()
    spot_data = dict()
    # ~ if csvFileName is not None:
        # ~ with open(csvFileName, "w") as f:
            # ~ #todo write csv labels
    pd_idx = 0
    for s_idx in range(1,numSpots+1): #spots go from [1, numSpots]
        # ~ spot_data = [f"spot_{s_idx:03d}"]
        for w in img.wavelengths:
            spot_data[df_cols[0]] = f"spot_{s_idx:03d}"
            spot_data[df_cols[1]] = w
            hsv_intensities = rgb2hsv(img[w][roi_labels==s_idx])
            rgb_intensities = img[w][roi_labels==s_idx]
            spot_data[df_cols[2]] = np.mean(rgb_intensities, axis=0).tolist()[0]
            spot_data[df_cols[3]] = np.mean(rgb_intensities, axis=0).tolist()[1]
            spot_data[df_cols[4]] = np.mean(rgb_intensities, axis=0).tolist()[2]
            spot_data[df_cols[5]] = np.median(rgb_intensities, axis=0).tolist()[0]
            spot_data[df_cols[6]] = np.median(rgb_intensities, axis=0).tolist()[1]
            spot_data[df_cols[7]] = np.median(rgb_intensities, axis=0).tolist()[2]
            spot_data[df_cols[8]] = np.mean(hsv_intensities, axis=0).tolist()[0]
            spot_data[df_cols[9]] = np.mean(hsv_intensities, axis=0).tolist()[1]
            spot_data[df_cols[10]] = np.mean(hsv_intensities, axis=0).tolist()[2]
            spot_data[df_cols[11]] = np.median(hsv_intensities, axis=0).tolist()[0]
            spot_data[df_cols[12]] = np.median(hsv_intensities, axis=0).tolist()[1]
            spot_data[df_cols[13]] = np.median(hsv_intensities, axis=0).tolist()[2]
            spot_data[df_cols[14]] = np.std(rgb_intensities, axis=0).tolist()[0]
            spot_data[df_cols[15]] = np.std(rgb_intensities, axis=0).tolist()[1]
            spot_data[df_cols[16]] = np.std(rgb_intensities, axis=0).tolist()[2]
            spot_data[df_cols[17]] = np.std(hsv_intensities, axis=0).tolist()[0]
            spot_data[df_cols[18]] = np.std(hsv_intensities, axis=0).tolist()[1]
            spot_data[df_cols[19]] = np.std(hsv_intensities, axis=0).tolist()[2]
            spot_data[df_cols[20]] = np.min(rgb_intensities, axis=0).tolist()[0]
            spot_data[df_cols[21]] = np.min(rgb_intensities, axis=0).tolist()[1]
            spot_data[df_cols[22]] = np.min(rgb_intensities, axis=0).tolist()[2]
            spot_data[df_cols[23]] = np.max(rgb_intensities, axis=0).tolist()[0]
            spot_data[df_cols[24]] = np.max(rgb_intensities, axis=0).tolist()[1]
            spot_data[df_cols[25]] = np.max(rgb_intensities, axis=0).tolist()[2]

            # ~ if csvFileName is not None:
                # ~ with open(csvFileName, "w") as f:
                    # ~ #todo write all data to csv
            df_total = pd.concat([df_total, pd.DataFrame(spot_data, index=[pd_idx])], axis=0)
            pd_idx += 1
    print(df_total)
    return df_total
