#!/usr/bin/env python
# -*- coding: utf-8 -*-

from time import sleep
from ZionGPIO import ZionGPIO
from ZionCamera import ZionCamera
from ZionEvents import check_led_timings, create_event_list, performEventList
from ZionSession import ZionSession

########################################################################
######################### User-Level Settings ##########################
######################################################################## 

Session_Name = 'session_name'

# Camera Properties:

# These can't change while camera is open:
Spatial_Res = (2028, 1520)
Frame_Rate = 20

# TODO: bring shutter speed back out to user
# (right now manual shutter speed can't be changed from 1/FR)
# Shutter Speed = Exposure Time (in microseconds)
# ~ Shutter_Speed = round(1000./Frame_Rate)  #(0 is automatic) 
# Shutter_Speed = round(1000000./Frame_Rate)
# Shutter_Speed_Stepsize = 2000
# Shutter_Speed_Max = 200000000
# Minimum is 1/Frame_Rate


# LED Timing:
# ~ Blue_Timing = [ (120000, 126000) ]
# ~ Orange_Timing = [ (120000, 122000), (124000,130000) ]
# ~ UV_Timing = [ (1, 122000) ]
Blue_Timing = [ (5000, 6000) ]
Orange_Timing = [ (5500, 6500) ]
UV_Timing = [ (7000, 8000) ]
# ~ UV_Timing =  [ (3000, 4000), (6000, 7000), (9000, 10000) ]

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

# TODO: Overwrite
# ~ overWrite=False

########################################################################
############################# Main Script ##############################
########################################################################

# Initialization Block:
mySession = ZionSession(Session_Name, Spatial_Res, Frame_Rate, Blue_Timing, Orange_Timing, UV_Timing, Camera_Captures, Repeat_N)

#Next line perform events defined above:
mySession.RunProgram()

# TODO: once we use high-power UVs, gonna want to turn them all off for safety:
# ~ myGPIO.turn_off_led('UV')

#Start preview:
mySession.InteractivePreview(window=(30,60,854,640))

########################################################################
######################### Shutdown Script ##############################
########################################################################

# Shut down Turn LEDs off and turns off camera
mySession.QuitSession()
