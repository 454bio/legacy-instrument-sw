import os
import numpy as np
from tifffile import imread, imwrite

offset_from_end = 0x11D81FF #hexidecimal
hdr_size = 32768 #decimal
bytes_per_line = 6112
used_bytes_per_line = 6084
img_W = 4056//2
img_H = 3040//2

#TODO: make all this faster? use C/C++?

def unpack_12_8_raw(line):
#  byte 0   byte 1   byte 2 
# AAAAAAAA BBBBBBBB BBBBAAAA
    color1 = []
    color2 = []
    for i in range(0,len(line),3):
        byte1 = line[i]<<4 | (line[i+2]&0X0F)
        byte2 = line[i+1]<<4 | ((line[i+2]>>4)&0X0F)
        color1.append(byte1)
        color2.append(byte2)
    return np.array(color1), np.array(color2)

def jpg_to_raw(filepath, target_path, compression=None):
    
    # grab raw data from end of file:
    with open(filepath, "rb") as f:
        raw_data = f.read()
    raw_data = raw_data[-offset_from_end-1:]
    if not raw_data[:4] == b'BRCM':
        raise("Invalid JPG+RAW file! RAW data header not found.")
    raw_data = raw_data[hdr_size:]

    #initialize 16-bit rgb images, will reshape later
    red_image = np.zeros(dtype=np.uint16, shape=(img_W*img_H,))
    green_image = np.zeros(dtype=np.uint16, shape=(img_W*img_H,))
    blue_image = np.zeros(dtype=np.uint16, shape=(img_W*img_H,))

    for line in range(0,img_H):
        # Create references to data in both raw and img domains:
        raw_idx_bg = slice(bytes_per_line*(2*line), bytes_per_line*(2*line)+used_bytes_per_line)
        #print('bg row = ' + str(raw_idx_bg))
        raw_idx_gr = slice(bytes_per_line*(2*line+1), bytes_per_line*(2*line+1)+used_bytes_per_line)
        #print('gr row = ' + str(raw_idx_gr))
        img_idx = slice(line*img_W, (line+1)*img_W)

        # Process colors and unpack:
        green1, red = unpack_12_8_raw(raw_data[raw_idx_bg])
        blue, green2 = unpack_12_8_raw(raw_data[raw_idx_gr])

        red_image[img_idx] = red<<4 #12 bit to 16 bit
        blue_image[img_idx] = blue<<4 #12 bit to 16 bit
        green_image[img_idx] = (green1<<3) + (green2<<3) #combined averaging and 12 bit to 16 bit

    # Now reshape images and write to 16-bit color tiff:
    filename =  os.path.splitext(target_path)[0]
    color_image = np.stack([red_image, green_image, blue_image], axis=-1).reshape((img_H, img_W, 3))
    imwrite(filename+".tif", color_image, photometric='rgb', compression=compression)
    print("Wrote file "+filename+".tif")

    #images available to return if desired:
    return red_image, green_image, blue_image