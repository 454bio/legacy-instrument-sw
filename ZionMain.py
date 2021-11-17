#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ZionSession import ZionSession

########################################################################
######################### User-Level Settings ##########################
######################################################################## 

# Session Name: This will be the name of the folder.
Session_Name = 'Test_Session'

# Camera Properties:
    # These can't change while camera is open:
Binning = False
    # w/  binning: 0.1 < framerate < 42
    # w/o binning: 0.05 < framerate < 10 fps
# Frame Rate
FrameRate = 2

# LED Properties
PWM_Frequency = 800 #{8000, 4000, 2000, 1600k, 1000, 800, 500, 400, 320, 250, 200, 160, 100, 80, 50, 40, 20, 10}

#Default Values:
Initial_Values = {
    'brightness':    61,      # between 0 and 100
    'contrast':      50,      # between -100 and 100
    'saturation':    60,       # between -100 and 100
    'sharpness':     0,       # between -100 and 100
    'awb':           'off',   # 'off' or 'auto'
    'red_gain':      1.9,     # 0.0 to 8.0
    'blue_gain':     1.52,     # 0.0 to 8.0
    'exposure_mode': 'off', # 'auto', 'night', 'verylong', etc. (***'off')
    'exposure_time': 750       # 0 is auto
    }


########################################################################
############################# Main Script ##############################
########################################################################

# Initialization Block:
mySession = ZionSession(Session_Name, FrameRate, Binning, Initial_Values, PWM_Frequency)

#Next line perform events defined above:
# ~ mySession.RunProgram()

# TODO: once we use high-power UVs, gonna want to turn them all off for safety:
# ~ myGPIO.turn_off_led('UV')

#Start preview:
mySession.InteractivePreview(window=(560,75,640,480))

########################################################################
######################### Shutdown Script ##############################
########################################################################

# Shut down Turn LEDs off and turns off camera
mySession.QuitSession()
