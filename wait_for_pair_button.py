#!/usr/bin/env python3

import pigpio
import os
import time

pi = pigpio.pi()
pair_button_state = True
state = 0

while True:
    if state==0: #waiting for initial button press
        pair_button_state = pi.read(6)
        if not pair_button_state:
            state = 1
            timer_start = time.time()
            time_now = time.time()
    elif state==1: #button pressed, now wait for button held for 3 sec
        if time_now < timer_start+3.:
            if not pair_button_state:
                pair_button_state = pi.read(6)
                time_now = time.time()
            else:
                state=0
        else:
            state=2
    elif state==2:
        os.system('/home/pi/Desktop/canyonlands/status_leds_pulse_color.py blue &')
        #todo turn BT pairing on...
        state = 3
        #todo remove, following only necessary for spoofing connecting after 5 seconds
        timer_start = time.time()
        time_now = time.time()
    elif state==3:
        #todo flesh out bluetooth connection check, right now spoof        
        if time_now>timer_start+5:
            os.system('/home/pi/Desktop/canyonlands/status_leds_set_color.py blue')
            state = 0
        else:
            time_now = time.time()