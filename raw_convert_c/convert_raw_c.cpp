
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include "tiffio.h"


#include "convert_raw_c.h"
using namespace std;



int jpg_to_raw(string in_filepath, string out_filepath)
{
	int ret = 0;
	const char key_literal[5] = {'B', 'R', 'C', 'M', '\0'};
	unsigned char key_buffer[5];
	const int buffer_length = OFFSET_FROM_END - HDR_SIZE + 1;

	FILE* f = fopen(in_filepath.c_str(), "rb");
	if (!f) {
		cout << "Unable to open image" << endl;
		ret++;
	}
	else {
		fseek(f, -1 * (OFFSET_FROM_END +1), SEEK_END);
		fread(key_buffer, 1, 4, f);
		key_buffer[4] = '\0';

		if (strcmp((char*)key_buffer, key_literal) == 0) {
			cout << "Valid key. Allocation input buffer." << endl;
			
			unsigned char * input_buffer = (unsigned char*)malloc(buffer_length);
			fseek(f, -1 * buffer_length, SEEK_END); //todo include -1?
			fread(input_buffer, 1, buffer_length, f);
			
			// Now we have all raw data in input_buffer

			TIFF* tif = TIFFOpen(out_filepath.c_str(), "w"); //opening file here

			TIFFSetField(tif, TIFFTAG_IMAGEWIDTH, IMG_W);
			TIFFSetField(tif, TIFFTAG_IMAGELENGTH, IMG_H);
			TIFFSetField(tif, TIFFTAG_BITSPERSAMPLE, 16);
			TIFFSetField(tif, TIFFTAG_SAMPLESPERPIXEL, 3);
			TIFFSetField(tif, TIFFTAG_PHOTOMETRIC, PHOTOMETRIC_RGB);
			TIFFSetField(tif, TIFFTAG_ORIENTATION, ORIENTATION_TOPLEFT);
			TIFFSetField(tif, TIFFTAG_PLANARCONFIG, PLANARCONFIG_CONTIG);
			
			unsigned char * dual_line_start;
			unsigned short * output_line_buffer = (unsigned short*)_TIFFmalloc(IMG_W*2);
			//~ unsigned short * image = new unsigned short[IMG_W*IMG_H*3];
			unsigned short currentPixel[3];
			unsigned short GreenPixel1;
			unsigned short GreenPixel2; 

			for (int l=0; l<IMG_H; l++) { //i is line index
				// we want to look at lines 2*l and 2*l+1, which is the following:
				//memcpy(dual_line_buffer, &input_buffer[2*l*BYTES_PER_LINE], BYTES_PER_LINE*2)
				//now dual_line_buffer is set up as follows:
				dual_line_start = &input_buffer[2*l*BYTES_PER_LINE];
				for (int i=0; i < USED_BYTES_PER_LINE; i=i+3) {
					currentPixel[2] = (unsigned short)( (*(i+dual_line_start) << 4) | (*(i+dual_line_start+2) & 0x0F) ); //blue
					GreenPixel1     = (unsigned short)( (*(i+dual_line_start+1) << 4) | ((*(i+dual_line_start+2) >> 4) & 0x0F) ); //green1
					GreenPixel2     = (unsigned short)( (*(i+dual_line_start+BYTES_PER_LINE) << 4) | (*(i+dual_line_start+2+BYTES_PER_LINE) & 0x0F) ); //green2
					currentPixel[0] = (unsigned short)( (*(i+dual_line_start+1+BYTES_PER_LINE) << 4) | ((*(i+dual_line_start+2+BYTES_PER_LINE) >> 4) & 0x0F) ); //red
					currentPixel[1] = (GreenPixel1 + GreenPixel2) > 2;
					memcpy(output_line_buffer+3*i, currentPixel, 6);
				}
				cout << l << endl;
				TIFFWriteScanline(tif, output_line_buffer, l, 0);
			}
			TIFFClose(tif); //closing file here
			if (output_line_buffer)
				_TIFFfree(output_line_buffer);
		}
		else {
			cout << "Incorrect key" << endl;
			ret++;
		}
	}
	fclose(f);
	cout << "closing f" << endl;
	return ret;
}

int main(int argc, char* argv[])
{
	int ret = -2;
	if (argc < 3) {
		cout << "Invalid number of arguments" << endl;
		return 1;
	}
	string filepath = argv[1];
	string target_path = argv[2];
	int out = jpg_to_raw(filepath, target_path);
	cout << out << endl;
	ret = 0;
	return ret;
}

