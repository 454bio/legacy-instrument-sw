#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ZionSession import ZionSession

########################################################################
######################### User-Level Settings ##########################
######################################################################## 

# Session Name: This will be the name of the folder.
Session_Name = 'Session_1'

# Camera Properties:
    # These can't change while camera is open:
Spatial_Res = (2028, 1520)
Binning = True
    # w/  binning: 0.1 < framerate < 42
    # w/o binning: 0.05 < framerate < 10 fps
# Frame Rate now given in range 0.1-10

#Default Values:
Initial_Values = {
    'brightness':    50,      # between 0 and 100
    'contrast':      50,      # between -100 and 100
    'saturation':    0,       # between -100 and 100
    'sharpness':     0,       # between -100 and 100
    'awb':           'off',   # 'off' or 'auto'
    'red_gain':      1.9,     # 0.0 to 8.0
    'blue_gain':     1.9,     # 0.0 to 8.0
    'exposure_mode': 'fireworks', # 'auto', 'night', 'verylong', etc. (***'off')
    'exposure_time': 0,       # 0 is auto
    }

# LED Timing:
Blue_Timing = [ (120000, 126000) ]
Orange_Timing = [ (120000, 122000), (124000,130000) ]
UV_Timing = [ (1, 122000) ]

# Camera Capture Timing:
Camera_Captures = [
(4000, None, 1),
(4500, None, 1),
(6000, None, 2),
(7500, None, 2),
(8000, None, 3)
]
#all 3 > blue > blue + orange > orange

# Repeat whole process N number of (additional) times
Repeat_N = 2

########################################################################
############################# Main Script ##############################
########################################################################

# Initialization Block:
mySession = ZionSession(Session_Name, Spatial_Res, 10, Binning, Initial_Values, Blue_Timing, Orange_Timing, UV_Timing, Camera_Captures, Repeat_N)

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
