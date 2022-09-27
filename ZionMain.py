#!/usr/bin/env python
# -*- coding: utf-8 -*-
from fractions import Fraction
from ZionSession import ZionSession
from ZionCamera import ZionCameraParameters
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

#Default Values:
Initial_Values = ZionCameraParameters()

########################################################################
############################# Main Script ##############################
########################################################################

# Initialization Block:
mySession = ZionSession(Session_Name, Binning, Initial_Values)

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
