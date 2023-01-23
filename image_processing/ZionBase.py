
from collections import UserDict, UserString
import numpy as np
import pandas as pd
from skimage.color import rgb2hsv
from matplotlib import pyplot as plt

from ZionImage import ZionImage

BASES = ('A', 'C', 'G', 'T')#, 'S') #todo: include scatter color as a base?
df_cols = [ "wavelength",
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

def extract_spot_data(img:ZionImage, roi_labels:np.array, csvFileName = None):
#bUseMedian:bool = False, bUseHsv:bool = False, ):
    ''' takes in a ZionImage (ie a dict of RGB images) and a 3D image of spot labels. Optionally writes a csv file.
        Outputs a pandas dataframe containing all data.
    '''

    numSpots = np.max(roi_labels)
    df_total = pd.DataFrame()
    spot_data = []
    if csvFileName is not None:
        with open(csvFileName, "w") as f:
            #todo write csv labels
    for s_idx in range(1,numSpots+1): #spots go from [1, numSpots]
        spot_data = [f"spot_{s_idx:03d}"]
        for w in img.wavelengths:
            spot_data.append(w)
            hsv_intensities = rgb2hsv(img[w][roi_labels==s_idx])
            rgb_intensities = img[w][roi_labels==s_idx]
            spot_data.extend( np.mean(rgb_intensities, axis=(1,2)).tolist() )
            spot_data.extend( np.median(rgb_intensities, axis=(1,2)).tolist() )
            spot_data.extend( np.mean(hsv_intensities, axis=(1,2)).tolist() )
            spot_data.extend( np.median(hsv_intensities, axis=(1,2)).tolist() )
            spot_data.extend( np.std(rgb_intensities, axis=(1,2)).tolist() )
            spot_data.extend( np.std(hsv_intensities, axis=(1,2)).tolist() )
            spot_data.extend( np.min(rgb_intensities, axis=(1,2)).tolist() )
            spot_data.extend( np.max(rgb_intensities, axis=(1,2)).tolist() )

            if csvFileName is not None:
                with open(csvFileName, "w") as f:
                    #todo write all data to csv
        #df = pd.DataFrame(data = spot_data, columns = df_cols, index=f"spot_{s_idx:03d}")
        df_total = pd.concat([df_total, pd.DataFrame(data=spot_data, columns=df_cols, index=f"spot_{s_idx:03d}")], axis=0)
    print(df_total)
    return df_total