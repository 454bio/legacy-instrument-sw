from collections import UserDict, UserString
import math
import numpy as np
import pandas as pd
from skimage.color import rgb2hsv
from scipy.optimize import nnls
from matplotlib import pyplot as plt

from ImageProcessing.ZionData import BASES, extract_spot_data, csv_to_data, add_basecall_result_to_dataframe
from ImageProcessing.ZionReport import ZionReport

'''
    This file contains code for basecalling and kinetics analysis.
    Also has code to map RGB/HSV data (X space) to base-amounts space (Z space)
'''

# TODO: use instead of str
# class ZionBase(UserString):

    # Names = ('A', 'C', 'G', 'T', '!')
    # # TODO change color based on dye colors?
    # Colors = ("orange", "green", "blue", "red")

    # def __init__(self, char):
        # if not isinstance(char, str):
            # raise TypeError("Base must be a character!")
        # elif len(char) != 1:
            # raise ValueError("Base must be a one-character string!")
        # elif char not in ZionBase.Names:
            # raise ValueError(f"Base must be valid character (not '{char}')!")
        # else:
            # super().__init__(char)

def project_color(data, M, factor_method="nnls"):

    '''
    Takes in data as array (N, L, K) or (L,K) and matrix of basis vectors M (Kx4)
    factor_method can be either:
        "pinv" which uses the Moore-Penrose pseudo-inverse method
        "nnls" is non negative least squares (we assume each color is some non-negative amount of each base)
    '''

    if data.dim == 2:
        numCycles, numChannels = data.shape
    elif data.dim == 3:
        numSpots, numCycles, numChannels = data.shape
    else:
        raise ValueError(f"data dimentions {data.shape} are not valid")

    if factor_method == "pinv":
        data = data.T # KxL or (K,L,N)
        m_pinv = np.linalg.pinv(M) # 4xK
        ret = m_pinv @ data # (4,L,N)
        ret = ret.T #(N, L, 4)

    elif factor_method == "nnls":
        ret = np.zeros(shape=(numSpots, numCycles, 4))
        for s in range(numSpots):
            for t in range(numCycles):
                ret[s,t,:] = nnls(M, data[s,t,:])

    else:
        raise ValueError(f"Invalid factoring method {factor_method}")

    return ret

def crosstalk_correct(data, X, numCycles, spotlist=None, exclusions=None, factor_method = "nnls", measure="mean"):

    '''
    Takes in dataframe, Kx4 "crosstalk" matrix X (which is actually just the color basis vectors), and number of cycles.
    Spotlist/exclusions is a way to exclude spots or assign names to rois/spots
    Outputs coefficients which represent how much of each base are in each spot
    '''

    if exclusions is None:
        exclusions = []

    if spotlist is None:
        spotlist = list(set(data.index.get_level_values('roi').to_list()))

    meas_cols = [measure+"_"+ch for ch in ["R","G","B"]]
    # include standard deviation? for confidence and/or quality?
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

def create_phase_correct_matrix(p, q, numCycles, r=0):

    P  = np.diag((numCycles+1)*[p])
    P += np.diag((numCycles)*[1-p-q-r], k=1)
    P += np.diag((numCycles-1)*[q], k=2)

    #TODO test w/ nonzero values of r
    P += np.diag((numCycles-2)*[r], k=3)

    Q = np.zeros(shape=(numCycles,numCycles))
    for t in range(numCycles):
        Q[:,t] = np.linalg.matrix_power(P,t+1)[0,1:]
    Qinv = np.linalg.inv(Q)
    return Qinv

def base_call(data, p:float=0.0, q:float=0.0, r:float=0.0):

    ''' Data is assumed to be numpy.ndarray of shape (N, L, 4) [spot index, cycle index, base index]
        p is probability that no new base is synthesized (t-1 error)
        q is probability that 2 new bases are synthesized (t+1 error)
        r is probability that 3 new bases are synthesized (t+2 error)
        
        Returns z_qinv, which are the estimated "amounts" of each base as array same shape as input data
        Returns bases, which are the bases called (by index eg 0,1,2,3 --> A,C,G,T)
    '''
    
    # If there is only one spot, data will be Lx4, needs to be 4xL
    if data.ndim == 2:
        data = data.T #now 4xL
        numSpots = 1
        numBases, numCycles = data.shape
    elif data.ndim == 3:
        # data is numpy array of shape (N,L,4) but needs to be (N,4,L) for later matrix multiplication
        data = np.transpose(data, axes=(0,2,1))
        # now data is numpy array of shape (N,4,L)
        numSpots, numBases, numCycles = data.shape
    else:
        raise ValueError(f"data dimentions {data.shape} are not valid")

    if not numBases == 4:
        #Print out assumed dimensions:
        print(f"Data to be base-called has {numSpots} spots and {numCycles} cycles") 
        raise ValueError("Data array is not the correct shape!")

    Qinv = create_phase_correct_matrix(p, q, numCycles, r=r)

    z_qinv = data @ Qinv
    bases = np.argmax(z_qinv, axis=1)

    # now reshape back to size (N,L,4)
    if data.ndim == 2:
        z_qinv = z_qinv.T
    else: #data.ndim == 3:
        z_qinv = np.transpose(z_qinv, axes=(0,2,1))

    return z_qinv, bases

def display_signals(coeffs, spotlist, numCycles, numRows=1, numPages=1, exclusions=None, prefix=None, noSignal=False, labels=True, stds=None, preOrPost="pre"):

    base_colors = {"A": "orange", "C": "green", "G":"blue", "T":"red"} #TODO yellow?

    if exclusions is None:
        exclusions = []

    numSpots = len(spotlist)

    width = len(spotlist) / (numRows*numPages)
    numCols = math.ceil(width)

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
            
    #TODO account for when there is only one spot (no need for any subplots)

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
        if preOrPost == "pre":
            suptitle = 'Purity (Pre-Phase-Corrected)'
        elif preOrPost == "post":
            suptitle = 'Purity (Phase-Corrected)'
        else:
            suptitle = 'Purity'
        fig1[page].suptitle(suptitle)
        fig1[page].subplots_adjust(hspace=0.5, wspace=0.2)
        if not noSignal:
            fig2[page].legend(loc='upper right', ncol=1)
            fig2[page].subplots_adjust(hspace=0.5, wspace=0.2)
            fig2[page].suptitle('Signal')
    return fig1, fig2
