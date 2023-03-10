#!/usr/bin/env python
# -*- coding: utf-8 -*-
from fractions import Fraction

from ZionSession import ZionSession
from ZionCamera import ZionCameraParameters
from GUI.ZionGtk import check_for_valid_filename

########################################################################
######################### User-Level Settings ##########################
########################################################################

# Session Name: This will be the name of the folder (prefixed with datetime info and suffixed with index).
# NOTE: No underscores allowed in session name!
Session_Name = 'TS'
if not check_for_valid_filename(Session_Name):
    raise Exception("Invalid character (or whitespace) found in session name!")

# Camera Properties:
    # These can't change while camera is open:
Binning = False
    # w/  binning: 0.1 < framerate < 42
    # w/o binning: 0.05 < framerate < 10 fps

#Default Values:
Initial_Values = ZionCameraParameters(
    brightness=    50,
    contrast=      -2,
    saturation=    0,
    sharpness=     0,
    awb_mode=      'off',
    red_gain=      Fraction(2,1),
    blue_gain=     Fraction(2,1),
    exposure_mode= 'off',
    shutter_speed= 250000,
    analog_gain=   Fraction(8,1),
    digital_gain=  Fraction(1,1),
    framerate=     1,
    vflip=         True,
)

PID_Params = {
'Target_Temperature': 58,
'PWM_Frequency': 10,
'P': 500,
'I': 25,
'delta_t': 1, #makes no difference as of now (TODO: speed up)
'bias': 0,
}

########################################################################
############################# Main Script ##############################
########################################################################

# Initialization Block:
mySession = ZionSession(Session_Name, Binning, Initial_Values, PID_Params)

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
