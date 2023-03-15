import numpy as np
import pandas as pd
from skimage.color import rgb2hsv

'''
    Module contains low-level interface to handle pandas dataframes (and associated csv files)
    Originally came from ZionImage.py but refactored to be separate module.
'''

# TODO: change df_cols to df_cols2 below (contains measurement property, could add more props
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
            "cycle",
            "time",
            ]

df_cols2 = [ ("roi", False),
             ("wavelength", False),
             ("mean_R", True),
             ("mean_G", True),
             ("mean_B", True),
             ("median_R", True),
             ("median_G", True),
             ("median_B", True),
             ("mean_H", True),
             ("mean_S", True),
             ("mean_V", True),
             ("median_H", True),
             ("median_S", True),
             ("median_V", True),
             ("std_R", True),
             ("std_G", True),
             ("std_B", True),
             ("std_H", True),
             ("std_S", True),
             ("std_V", True),
             ("min_R", True),
             ("min_G", True),
             ("min_B", True),
             ("max_R", True),
             ("max_G", True),
             ("max_B", True),
             ("cycle", False),
             ("time", False),
            ]

def extract_spot_data(img, roi_labels, csvFileName = None, kinetic=False):
    ''' takes in a ZionImage and a 2D image of spot labels. Optionally writes a csv file.
        Outputs a pandas dataframe containing all data for the cycle.
    '''

    numSpots = np.max(roi_labels)
    df_total = pd.DataFrame()
    spot_data = dict()
    pd_idx = 0
    w_idx = []
    #TODO check to see that csvFileName exists since we are appending later
    
    for s_idx in range(1,numSpots+1): #spots go from [1, numSpots]
        if roi_labels[roi_labels==s_idx].size > 0: #we removed ones that are too big but didn't change the labels...
            for w_ind, w in enumerate(img.wavelengths):
                spot_data[df_cols[0]] = f"spot_{s_idx:03d}"
                spot_data[df_cols[1]] = w
                hsv_intensities = rgb2hsv(img[w][roi_labels==s_idx])
                rgb_intensities = img[w][roi_labels==s_idx]
                spot_data[df_cols[2]], spot_data[df_cols[3]], spot_data[df_cols[4]] = np.mean(rgb_intensities, axis=0).tolist()
                spot_data[df_cols[5]], spot_data[df_cols[6]], spot_data[df_cols[7]] = np.median(rgb_intensities, axis=0).tolist()
                spot_data[df_cols[8]], spot_data[df_cols[9]], spot_data[df_cols[10]] = np.mean(hsv_intensities, axis=0).tolist()
                spot_data[df_cols[11]], spot_data[df_cols[12]], spot_data[df_cols[13]] = np.median(hsv_intensities, axis=0).tolist()
                spot_data[df_cols[14]], spot_data[df_cols[15]], spot_data[df_cols[16]] = np.std(rgb_intensities, axis=0).tolist()
                spot_data[df_cols[17]], spot_data[df_cols[18]], spot_data[df_cols[19]] = np.std(hsv_intensities, axis=0).tolist()
                spot_data[df_cols[20]], spot_data[df_cols[21]], spot_data[df_cols[22]] = np.min(rgb_intensities, axis=0).tolist()
                spot_data[df_cols[23]], spot_data[df_cols[24]], spot_data[df_cols[25]] = np.max(rgb_intensities, axis=0).tolist()
                spot_data[df_cols[26]] = int(img.cycle)
                if not kinetic:
                    spot_data[df_cols[27]] = int(img.time_avg)
                else:
                    spot_data[df_cols[27]] = int(img.times[w_ind])

                if csvFileName is not None:
                    with open(csvFileName, "a") as f:
                        lineToWrite = ','.join( [str(spot_data[k]) for k in df_cols])
                        f.write( lineToWrite + '\n')
                        # ~ print(f"Appending to {csvFileName}:\n{lineToWrite}")
                df_total = pd.concat([df_total, pd.DataFrame(spot_data, index=[pd_idx])], axis=0)
                pd_idx += 1
    df_total.set_index(["roi", "time", "cycle", "wavelength"], inplace=True)
    df_total = df_total.unstack()

    w_idx = []
    for w in img.wavelengths:
        w_idx += 3*[w]
    ch_idx = []
    # TODO: dependent on df_cols def above, but this could be accessed once move to df_cols2 above
    for c in [2,5,8,11,14,17,20,23]:
        ch_idx += len(img.wavelengths) * df_cols[c:(c+3)]
    try:
        mi = pd.MultiIndex.from_arrays([ch_idx, int(len(ch_idx)/len(w_idx))*w_idx])
    except ValueError as e:
        print(f"ch_idx = {ch_idx}, w_idx = {w_idx}")
        raise e
    df_total = df_total.reindex(columns=mi)
    
    #TODO now write to csv, not earlier?

    return df_total

def csv_to_data(csvfile):
    df_total = pd.read_csv(csvfile)
    df_total.set_index(["roi", "cycle", "wavelength"], inplace=True)
    wavelengths = list(set(df_total.index.get_level_values('wavelength').to_list()))
    df_total = df_total.unstack()
    w_idx = []
    for w in wavelengths:
        w_idx += 3*[w]
    ch_idx = []
    # TODO: dependent on df_cols def above, but this could be accessed once move to df_cols2 above
    for c in [2,5,8,11,14,17,20,23]:
        ch_idx += len(wavelengths) * df_cols[c:(c+3)]
    try:
        mi = pd.MultiIndex.from_arrays([ch_idx, int(len(ch_idx)/len(w_idx))*w_idx])
    except ValueError as e:
        print(f"ch_idx = {ch_idx}, w_idx = {w_idx}")
        raise e
    df_total = df_total.reindex(columns=mi)
    return df_total

def add_basecall_result_to_dataframe(data, df):
    spotlist = list(set(df.index.get_level_values('roi').to_list()))
    coeffs_pd = pd.DataFrame(index=df.index, columns = [("Signal", base) for base in BASES])
    numCycles = data.shape[1]
    for s_idx, spot in enumerate(spotlist):
        for cycle in range(numCycles):
            coeffs_pd.loc[(spot, cycle+1)] = data[s_idx, cycle, :]
    return pd.concat([df, coeffs_pd], axis=1)

