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
            
    def pulse_color(self, brightness, R, G, B, rate=0.55, sine=True):
        #first define ramp:
        brightnesses = list(range(1,brightness+1,1))+list(range(brightness-1,1,-1))
        print(brightnesses)
        #sine wave:
        brightnesses_wave = [1]+[round(brightness/2 - (brightness/2)*math.cos(b*2*math.pi/len(brightnesses))) for b in brightnesses[1:]]
        print(brightnesses_wave)
        while True:
            if sine:
                for b in brightnesses_wave:
                    self.set_color(b, R, G, B)
                    time.sleep(1./(rate*len(brightnesses_wave)))
            else:
                for b in brightnesses:
                    self.set_color(b, R, G, B)
                    time.sleep(1./(rate*len(brightnesses)))
            
if __name__=='__main__':
    
    os.system('pkill -9 -f status_leds_spin_color')
    
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
                leds.pulse_color(*GREEN)
        elif opt=='orange':
            leds = ZionStatusLEDs()
            while True:
                leds.pulse_color(*ORANGE)
        elif opt=='blue':
            leds = ZionStatusLEDs()
            while True:
                leds.pulse_color(*BLUE)
        elif opt=='red':
            leds = ZionStatusLEDs()
            while True:
                leds.pulse_color(*RED)
        else:
            leds = ZionStatusLEDs()
