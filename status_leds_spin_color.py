#!/usr/bin/env python3

import os
import sys
import argparse
import spidev
import time
import math
import numpy as np
from collections import deque

#color defa:
ORANGE = (19,0xFF,0x45,0x00)
GREEN = (14, 0x12, 0xFF, 0x15)
BLUE = (20,0x00,0x48, 0xFF)
RED = (15, 0xFF,0x00,0x00)

#some useful defines here:
start_frame = [0x00,0x00,0x00,0x00]
color_off = [0xFF,0x00,0x00,0x00]

class ZionStatusLEDs():
    def __init__(self, numLEDs=45, spi_speed=1000000):
        self.N = numLEDs
        self.spi = spidev.SpiDev()
        self.spi.open(0,0)
        #clear buffer just in case:
        self.spi.close()
        #re-open:
        self.spi.open(0,0)
        #set-up spi:
        self.spi.no_cs = True
        self.spi.lsbfirst = False
        self.spi.mode = 0b11
        self.spi.max_speed_hz = spi_speed
        
        # make sure all leds are off:
        self.stop_frame = math.floor((self.N+15)/16)*[0xFF,]
        self.turn_off_all()
        
        self.running = False
        
        
    def turn_off_all(self):
        self.send_init()
        for n in range(self.N+5):
            self.spi.writebytes(color_off)
#             time.sleep(0.1)
#         self.spi.writebytes(self.stop_frame)
            
    def send_init(self):
        self.spi.writebytes(start_frame)
        
    def set_color(self, brightness, R, G, B):
        #brightness is 5 bit number!
        if brightness<0 or brightness>=32:
            raise ValueError('Brightness must be a 5 bit integer!')
        elif R<0 or R>=256:
            raise ValueError('Red must be a 8 bit integer!')
        elif B<0 or B>=256:
            raise ValueError('Blue must be a 8 bit integer!')
        elif G<0 or G>=256:
            raise ValueError('Green must be a 8 bit integer!')
        else:
            byte0 = 0xE0 | int(hex(brightness), 16)
            frame = [byte0, int(hex(B), 16), int(hex(G), 16), int(hex(R), 16)]
            self.send_init()
            for n in range(self.N):
                self.spi.writebytes(frame)
            self.spi.writebytes(self.stop_frame)
    
    def spin_color(self, brightness, R,G,B, rate=1.2, window_length=9):
        leading = True
        if not leading:
            ramp_down = np.linspace(start=brightness, stop=0, num=2+math.floor(window_length/2)).round().astype(int).tolist()[1:-1]
            ramp_up = np.linspace(start=0, stop=brightness, num=2+math.floor(window_length/2)).round().astype(int).tolist()[1:-1]
            brightnesses = deque(ramp_up+[brightness]+ramp_down+(self.N-len(ramp_up)-len(ramp_down)-1)*[0])
        else:
            ramp_up = np.linspace(start=0, stop=brightness, num=window_length+1).round().astype(int).tolist()
            brightnesses = deque(ramp_up+(self.N-len(ramp_up))*[0])
        while True:
            self.send_init()
            for n in range(self.N):
                byte0 = 0xE0 | int(hex(brightnesses[n]), 16)
                frame = [byte0, int(hex(B), 16), int(hex(G), 16), int(hex(R), 16)]
                self.spi.writebytes(frame)
            self.spi.writebytes(self.stop_frame)
            time.sleep(1./(rate*self.N))
            brightnesses.rotate(1)
            
if __name__=='__main__':
    
    os.system('pkill -9 -f status_leds_pulse_color')
    
    nArgs = len(sys.argv)
    if nArgs==1:
        leds = ZionStatusLEDs()
    elif nArgs==2:
        opt = sys.argv[1]
        if opt=='demo':
            leds = ZionStatusLEDs()
            while True:
                leds.set_color(*GREEN)
                time.sleep(1)
                leds.set_color(*ORANGE)
                time.sleep(1)
                leds.set_color(*RED)
                time.sleep(1)
                leds.set_color(*BLUE)
                time.sleep(1)
        elif opt=='green':
            leds = ZionStatusLEDs()
            while True:
                leds.spin_color(*GREEN)
        elif opt=='orange':
            leds = ZionStatusLEDs()
            while True:
                leds.spin_color(*ORANGE)
        elif opt=='blue':
            leds = ZionStatusLEDs()
            while True:
                leds.spin_color(*BLUE)
        elif opt=='red':
            leds = ZionStatusLEDs()
            while True:
                leds.spin_color(*RED)
        else:
            leds = ZionStatusLEDs()

