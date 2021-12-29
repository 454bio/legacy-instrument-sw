#!/usr/bin/env python3

# This is a spoof function that simply generates a fake result file after a specific amount of time...

import sys
import time
import argparse

def main(parameter_file, protocol_file, timeout=20):
    ret = False
    try:
        time.sleep(timeout)
        with open('ZionReport_spoofed.txt', 'w') as file:
            file.writelines(['This is a Zion Report!',
                             'Parameters from: '+parameter_file,
                             'Protocol from: '+protocol_file])
        ret = True
    return ret

if __name__=='__main__':
#todo use argparse here
    params = 'default.param'
    proto = 'default.proto'
    return main(params, proto)