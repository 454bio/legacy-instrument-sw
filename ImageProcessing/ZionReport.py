import os
import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
from fpdf import FPDF

class ZionReportText:
    pass

class ZionReport(FPDF):
    # TODO flesh out to create pdf report
    pass


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
