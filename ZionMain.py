#!/usr/bin/env python
# -*- coding: utf-8 -*-

from time import sleep
from ZionGPIO import ZionGPIO
from ZionCamera import ZionCamera
from ZionEvents import check_led_timings, create_event_list, initializeSession, performEventList

########################################################################
######################### User-Level Settings ##########################
######################################################################## 

# Camera Properties:

# These can't change while camera is open:
Spatial_Res = (2028, 1520)
Frame_Rate = 20

# Shutter Speed = Exposure Time (in microseconds)
# ~ Shutter_Speed = round(1000./Frame_Rate)  #(0 is automatic) 
Shutter_Speed = round(1000000./Frame_Rate)
Shutter_Speed_Stepsize = 2000
Shutter_Speed_Max = 200000000
# Minimum is 1/Frame_Rate
# TODO: right now manual shutter speed can't be changed from 1/FR

# LED Timing:
Blue_Timing = [ (120000, 126000) ]
Orange_Timing = [ (120000, 122000), (124000,130000) ]
UV_Timing = [ (1, 122000) ]
# ~ UV_Timing =  [ (3000, 4000), (6000, 7000), (9000, 10000) ]

# Camera Capture Timing:jikozasxxsssddccfffvvvvvulloiuojkiujkiuujkiujkolkiujkoloiuliuolkjlujikolikujolikoluji...//;';';[[]////////////////////////////''';............;;\\
Camera_Captures = [
(121000, None),
(123000, None),
(125000, None),
(127000, None)
]
#all 3 > blue > blue + orange > orange

# Repeat whole process N number of times
Repeat_N = 2

########################################################################
############################# Main Script ##############################
########################################################################

# Initialization Block:
# TODO: once we use real UV LEDs, remove UV_duty_cycle argument to default it to 3.0
check_led_timings(Blue_Timing, Orange_Timing, UV_Timing)
myGPIO = ZionGPIO()
myCamera = ZionCamera(Spatial_Res, Frame_Rate, Shutter_Speed, Shutter_Speed_Stepsize, Shutter_Speed_Max, gpio_ctrl=myGPIO)

# Do what you want here:
baseFilename = 'UV_long_run'

#Next two lines perform events defined
myEventList = create_event_list(Blue_Timing, Orange_Timing, UV_Timing, Camera_Captures, Repeat_N)
performEventList(myEventList, myCamera, myGPIO, Repeat_N, baseFilename)

# ~ myGPIO.turn_off_led('all')
myCamera.interactive_preview(baseFilename, window=(30, 60, 854, 640))

#Turn LEDs off and turns off camera
myGPIO.turn_off_led('all')
myCamera.quit()
