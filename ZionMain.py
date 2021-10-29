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
    'exposure_mode': 'off', # 'auto', 'night', 'verylong', etc. (***'off')
    'exposure_time': 0,       # 0 is auto
    }

# LED Timing:
PWM_Frequency = 1000 #{8k, 4k, 2k, 1.6k, 1k, 800, 500, 400, 320, 250, 200, 160, 100, 80, 50, 40, 20, 10}
Blue_Timing = [ (2000, 3000) ]
Orange_Timing = [ (4000, 5000), (8000,9000) ]
UV_Timing = [ (6000, 7000) ]

# Camera Capture Timing:
Camera_Captures = [
(2500, None, 'Z'),
(4500, None, 'Z'),
(6000, None, 'W'),
(7500, None, 2),
(8500, None, 3)
]
#all 3 > blue > blue + orange > orange

# Repeat whole process N number of (additional) times
Repeat_N = 1

########################################################################
############################# Main Script ##############################
########################################################################

# Initialization Block:
mySession = ZionSession(Session_Name, 10, Binning, Initial_Values, PWM_Frequency, Blue_Timing, Orange_Timing, UV_Timing, Camera_Captures, Repeat_N)

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
