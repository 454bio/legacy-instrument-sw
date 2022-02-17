#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ZionSession import ZionSession
from ZionGtk import check_for_valid_filename

########################################################################
######################### User-Level Settings ##########################
######################################################################## 

# Session Name: This will be the name of the folder (prefixed with datetime info and suffixed with index).
# NOTE: No underscores allowed in session name!
Session_Name = 'TS'
if not check_for_valid_filename(Session_Name):
    raise Exception("Invalid character (or whitespace) detected in session name!")
    
# Camera Properties:
    # These can't change while camera is open:
Binning = False
    # w/  binning: 0.1 < framerate < 42
    # w/o binning: 0.05 < framerate < 10 fps

# LED Properties
PWM_Frequency = 8000 #{8000, 4000, 2000, 1600, 1000, 800, 500, 400, 320, 250, 200, 160, 100, 80, 50, 40, 20, 10}

#Default Values:
Initial_Values = {
    'brightness':    50,      # between 0 and 100
    'contrast':      -1,      # between -100 and 100
    'saturation':    0,       # between -100 and 100
    'sharpness':     0,       # between -100 and 100
    'awb':           'off',   # 'off' or 'auto'
    'red_gain':      1.00,     # 0.0 to 8.0
    'blue_gain':     1.00,     # 0.0 to 8.0
    'exposure_mode': 'off', # 'auto', 'night', 'verylong', etc. (***'off')
    'exposure_time': 250,       # 0 is auto
    'a_gain':        8,        # max is 16
    'd_gain':        1,         #unity gain for avoiding quantization error
    'framerate':     4,         # min 0.1 max 42 if binning, else min 0.05 max 10
    }


########################################################################
############################# Main Script ##############################
########################################################################

# Initialization Block:
mySession = ZionSession(Session_Name, Binning, Initial_Values, PWM_Frequency)

#Next line perform events defined above:
# ~ mySession.RunProgram()

# TODO: once we use high-power UVs, gonna want to turn them all off for safety:
# ~ myGPIO.turn_off_led('UV')

#Start preview:
# ~ mySession.InteractivePreview(window=(560,75,640,480))
# mySession.InteractivePreview(window=(1172,75,720,540))
mySession.StartSession()

########################################################################
######################### Shutdown Script ##############################
########################################################################

# Shut down Turn LEDs off and turns off camera
mySession.QuitSession()
