
from collections import UserDict, UserString
import numpy as np
import pandas as pd
from skimage.color import rgb2hsv
from scipy.optimize import nnls
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
            "cycle",
            "time",
            ]

class ZionBase(UserString):

    Names = ('A', 'C', 'G', 'T', '!')
    # TODO change color based on dye colors?
    Colors = ("orange", "green", "blue", "red")

    def __init__(self, char):
        if not isinstance(char, str):
            raise TypeError("Base must be a character!")
        elif len(char) != 1:
            raise ValueError("Base must be a one-character string!")
        elif char not in ZionBase.Names:
            raise ValueError(f"Base must be valid character (not '{char}')!")
        else:
            super().__init__(char)

def extract_spot_data(img, roi_labels, csvFileName = None, kinetic=False):
    ''' takes in a ZionImage (ie a dict of RGB images) and a 3D image of spot labels. Optionally writes a csv file.
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
    # Note: dependent on df_cols def above
    for c in [2,5,8,11,14,17,20,23]:
        ch_idx += len(img.wavelengths) * df_cols[c:(c+3)]
    try:
        mi = pd.MultiIndex.from_arrays([ch_idx, int(len(ch_idx)/len(w_idx))*w_idx])
    except ValueError as e:
        print(f"ch_idx = {ch_idx}, w_idx = {w_idx}")
        raise e
    df_total = df_total.reindex(columns=mi)

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
    # Note: dependent on df_cols def above
    for c in [2,5,8,11,14,17,20,23]:
        ch_idx += len(wavelengths) * df_cols[c:(c+3)]
    try:
        mi = pd.MultiIndex.from_arrays([ch_idx, int(len(ch_idx)/len(w_idx))*w_idx])
    except ValueError as e:
        print(f"ch_idx = {ch_idx}, w_idx = {w_idx}")
        raise e
    df_total = df_total.reindex(columns=mi)
    return df_total

def crosstalk_correct(data, X, numCycles, spotlist=None, exclusions=None, factor_method = "nnls", measure="mean"):
    '''
    Takes in dataframe, Kx4 "crosstalk" matrix X (which is actually just the color basis vectors), and number of cycles.
    Spotlist/exclusions is a way to exclude spots or assign names to rois/spots
    Outputs coefficients which represent how much of each base are in each spot, also outputs stds if necessary
    '''
    if exclusions is None:
        exclusions = []

    if spotlist is None:
        spotlist = list(set(data.index.get_level_values('roi').to_list()))

    meas_cols = [measure+"_"+ch for ch in ["R","G","B"]]
    # ~ std_cols = ["std_"+ch for ch in ["R","G","B"]]
    # ~ std_index = [("std"+i[0][-2:], i[1]) for i in X.index]
    #print(std_cols)
    
    pinv = np.linalg.pinv(X.T)
    
    coeffs_df = pd.DataFrame(index = data.index, columns = [("Signal",base) for base in BASES])
    # ~ print(coeffs_df)
    coeffs = np.zeros(shape=(len(spotlist), numCycles, 4))
    #coeffs_norm = np.zeros(shape=(len(spotlist), numCycles, 4))
    # ~ stds_out = np.zeros(shape=(len(spotlist), numCycles, 4))
    
    for s_idx, spot in enumerate(spotlist):
        if spot not in exclusions:
            
            #TODO: columns getting re-ordered here
            #x_vec = data[meas_cols].loc[spot].values
            x = data[meas_cols].loc[spot]
            # ~ stds_in = data[std_cols].loc[spot]
            
            #print(X.index)
            # ~ stds_in_vec = stds_in[std_index].values
            # ~ stds_out[s_idx, :, :] = np.matmul(stds_in_vec, pinv)
            
            x_vec = x[meas_cols].values
            if factor_method == "pinv":
                coeffs[s_idx,:,:] = np.matmul(x_vec, pinv)
            elif factor_method == "nnls":                
                for cycle in range(numCycles):
                    coeffs[s_idx, cycle, :], _ = nnls(X, x_vec[cycle,:])
            # ~ print(f"coeffs[s_idx, cycle,:] shape = {coeffs[s_idx, cycle, :].shape}")
            # ~ print(f"coeffs_df.loc[(spot, cycle+1)] shape = {coeffs_df.loc[(spot, cycle+1)].shape}")
            for cycle in range(numCycles):
                coeffs_df.loc[(spot, cycle+1)] = coeffs[s_idx, cycle, :]
            #coeffs_norm[s_idx,:,:] = np.transpose( coeffs[s_idx,:,:].T / np.sum(coeffs[s_idx,:,:], axis=1) )
            #basecalls[s_idx,:] = np.argmax(scores_norm, axis=1)
    return coeffs, spotlist, pd.concat([data, coeffs_df], axis=1)

def add_basecall_result_to_dataframe(data, df):
    spotlist = list(set(df.index.get_level_values('roi').to_list()))
    coeffs_pd = pd.DataFrame(index=df.index, columns = [("Signal", base) for base in BASES])
    numCycles = data.shape[1]
    for s_idx, spot in enumerate(spotlist):
        for cycle in range(numCycles):
            coeffs_pd.loc[(spot, cycle+1)] = data[s_idx, cycle, :]
    return pd.concat([df, coeffs_pd], axis=1)

def base_call(data, p:float=0.0, q:float=0.0, base_key:list=["A", "C", "G" "T"]):
    ''' This takes the 4 coefficients found from crosstalk correction and 
        does phase correction. Right now using simple model until we get more data.
    '''
    # data is numpy array of shape (K,L,4) but needs to be (K,4,L):
    data = np.transpose(data, axes=(0,2,1))
    
    # data is numpy array of shape (K,4,L)
    numSpots, numBases, numCycles = data.shape
    if not numBases == 4:
        raise ValueError("Data array is not the correct shape!")

    # p is probability that no new base is synthesized
    # q is probability that 2 new bases are synthesized
    # 1-p-q is probability that 1 new base is synthesized
        
    #TODO: do we need more p's & q's for N+2?
    
    #Transition matrix is numCycles+1 x numCycles+1
    P  = np.diag((numCycles+1)*[p])
    P += np.diag((numCycles)*[1-p-q], k=1)
    P += np.diag((numCycles-1)*[q], k=2)
    
    Q = np.zeros(shape=(numCycles,numCycles))
    for t in range(numCycles):
        Q[:,t] = np.linalg.matrix_power(P,t+1)[0,1:]
    Qinv = np.linalg.inv(Q)
    
    z_qinv = data @ Qinv
    bases = np.argmax(z_qinv, axis=1)
    
    z_qinv = np.transpose(z_qinv, axes=(0,2,1))
    
    return z_qinv, bases

def create_phase_correct_matrix(p,q,numCycles,r=0):
    P  = np.diag((numCycles+1)*[p])
    P += np.diag((numCycles)*[1-p-q], k=1)
    P += np.diag((numCycles-1)*[q], k=2)

    Q = np.zeros(shape=(numCycles,numCycles))
    for t in range(numCycles):
        Q[:,t] = np.linalg.matrix_power(P,t+1)[0,1:]
    Qinv = np.linalg.inv(Q)
    return Qinv

def display_signals(coeffs, spotlist, numCycles, numRows=1, numPages=1, exclusions=None, prefix=None, noSignal=False, labels=True, stds=None):

    base_colors = {"A": "orange", "C": "green", "G":"blue", "T":"red"} #TODO yellow?

    if exclusions is None:
        exclusions = []

    numSpots = len(spotlist)

    width = len(spotlist)/ (numRows*numPages)
    numCols = int(width)

    fig1 = []
    ax1 = []
    fig2 = []
    ax2 = []
    for _ in range(numPages):
        fig, ax = plt.subplots(numRows,numCols)
        fig1.append(fig)
        ax1.append(ax)
        if not noSignal:
            fig, ax = plt.subplots(numRows,numCols)
            fig2.append(fig)
            ax2.append(ax)

    for s_idx_orig, spot in enumerate(spotlist):
        page, s_idx = divmod(s_idx_orig, numSpots//numPages)
        # ~ print(f"s_idx_org={s_idx_orig}, page={page}, s_idx={s_idx}")
        if spot not in exclusions:
            scores_norm = np.transpose( coeffs[s_idx_orig,:numCycles,:].T / np.sum(coeffs[s_idx_orig,:numCycles,:], axis=1) )
            if stds is not None:
                stds_norm = np.transpose( stds[s_idx_orig,:numCycles,:].T / np.sum(coeffs[s_idx_orig,:numCycles,:], axis=1) )
            kinetic_total = np.sum(coeffs[s_idx_orig,0,:])
            for base in range(4):
                 if s_idx == 0:
                     if stds is not None:
                         ax1[page].flat[s_idx].bar( np.arange(1,numCycles+1)+(base-2)/6, scores_norm[:,base], 1/6, align="edge", color = base_colors[BASES[base]], label = BASES[base], yerr=stds_norm[:,base])
                     else:
                         ax1[page].flat[s_idx].bar( np.arange(1,numCycles+1)+(base-2)/6, scores_norm[:,base], 1/6, align="edge", color = base_colors[BASES[base]], label = BASES[base])
                     if not noSignal:
                         ax2[page].flat[s_idx].plot(np.arange(1, numCycles+1), coeffs[s_idx_orig,:,base]/kinetic_total, color = base_colors[BASES[base]], label = BASES[base])
                 else:
                     if stds is not None:
                         ax1[page].flat[s_idx].bar( np.arange(1,numCycles+1)+(base-2)/6, scores_norm[:,base], 1/6, align="edge", color = base_colors[BASES[base]], yerr=stds_norm[:,base])
                     else:
                         ax1[page].flat[s_idx].bar( np.arange(1,numCycles+1)+(base-2)/6, scores_norm[:,base], 1/6, align="edge", color = base_colors[BASES[base]])
                     if not noSignal:
                         ax2[page].flat[s_idx].plot(np.arange(1, numCycles+1), coeffs[s_idx_orig,:,base]/kinetic_total, color = base_colors[BASES[base]])
            purity = np.max(scores_norm, axis=-1)
            called_base_idx = np.argmax(scores_norm, axis=-1)
            for cycle in range(numCycles):
                #chastity is defined as the ratio of the brightest base intensity divided by the sum of the brightest and second brightest base intensities
                SecondPlace = np.sort(scores_norm[cycle,:])[-2]
                chastity = purity[cycle] / (purity[cycle] + SecondPlace)
                if labels:
                    ax1[page].flat[s_idx].text(cycle+1+(called_base_idx[cycle]-1.5)/6, purity[cycle]+0.01, f"{100*purity[cycle]:.1f}", color='black', fontsize=7, horizontalalignment='center')
                    #ax1[page].flat[s_idx].text(cycle+1+(called_base_idx[cycle]-1.5)/6, purity[cycle]+0.01, f"{chastity:.2f}", color='black', fontsize=7, horizontalalignment='center')
            ax1[page].flat[s_idx].set_ylim([-0.1,1.1])

            if not noSignal:
                ax2[page].flat[s_idx].set_xticks(np.arange(1,numCycles+1))
                
                if s_idx == 0:
                    ax2[page].flat[s_idx].plot(np.arange(1, numCycles+1), np.sum(coeffs[s_idx_orig,:,:]/kinetic_total, axis=-1), color = 'black', label = 'Total')
                else:
                    ax2[page].flat[s_idx].plot(np.arange(1, numCycles+1), np.sum(coeffs[s_idx_orig,:,:]/kinetic_total, axis=-1), color = 'black')
                # ax1.flat[s_idx].set_title(''.join(f"{matrix_key[basecalls[s_idx_orig,cycle]]}" for cycle in range(numCycles))+f" ({gt_data[s_idx_orig]})")
                ax2[page].flat[s_idx].set_title(spot, fontsize=10)
            ax1[page].flat[s_idx].set_title(spot, fontsize=10)

    if prefix:
        prefix += " "
    else:
        prefix = ""

    for page in range(numPages):
        fig1[page].legend(loc='upper right', ncol=1)
        fig1[page].suptitle('Purity (Pre-Phase-Corrected)')
        fig1[page].subplots_adjust(hspace=0.5, wspace=0.2)
        if not noSignal:
            fig2[page].legend(loc='upper right', ncol=1)
            fig2[page].subplots_adjust(hspace=0.5, wspace=0.2)
            fig2[page].suptitle('Signal')
    return fig1, fig2
