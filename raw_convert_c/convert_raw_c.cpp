
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
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
			//~ cout << "Valid key. Allocation input buffer." << endl;
			
			uint8_t * input_buffer = (uint8_t*)malloc(buffer_length);
			fseek(f, -1 * buffer_length, SEEK_END);
			fread(input_buffer, 1, buffer_length, f);
			
			// Now we have all raw data in input_buffer

			TIFF* tif = TIFFOpen(out_filepath.c_str(), "w"); //opening file here

			TIFFSetField(tif, TIFFTAG_IMAGEWIDTH, (uint32_t)IMG_W);
			TIFFSetField(tif, TIFFTAG_IMAGELENGTH, (uint32_t)IMG_H);
			TIFFSetField(tif, TIFFTAG_BITSPERSAMPLE, (uint16_t)16);
			TIFFSetField(tif, TIFFTAG_SAMPLESPERPIXEL, (uint16_t)3);
			TIFFSetField(tif, TIFFTAG_PHOTOMETRIC, PHOTOMETRIC_RGB);
			TIFFSetField(tif, TIFFTAG_ORIENTATION, ORIENTATION_TOPLEFT);
			TIFFSetField(tif, TIFFTAG_PLANARCONFIG, PLANARCONFIG_CONTIG);
			//todo: change rows per strip? does it increase speed?
			TIFFSetField(tif, TIFFTAG_ROWSPERSTRIP, 1);

			
			uint8_t  * dual_line_start;
			uint16_t * output_line_buffer = (uint16_t*)malloc(6*IMG_W);
			uint16_t currentPixel[3];
			uint16_t GreenPixel1;
			uint16_t GreenPixel2;
			int res;

			for (int l=0; l<IMG_H; l++) { //l is line index
				// we want to look at lines 2*l and 2*l+1, which is the following:
				//memcpy(dual_line_buffer, &input_buffer[2*l*BYTES_PER_LINE], BYTES_PER_LINE*2)
				//now dual_line_buffer is set up as follows:
				dual_line_start = input_buffer + 2*l*BYTES_PER_LINE; //&input_buffer[2*l*BYTES_PER_LINE]; //
				for (int i=0; i < USED_BYTES_PER_LINE; i=i+3) {
					
					GreenPixel1     = (uint16_t)( (*(i+dual_line_start) << 4) | (*(i+dual_line_start+2) & 0x0F) ); //green1
					GreenPixel2     = (uint16_t)( (*(i+dual_line_start+1+BYTES_PER_LINE) << 4) | ((*(i+dual_line_start+2+BYTES_PER_LINE) >> 4) & 0x0F) ); //green2
					currentPixel[0] = (uint16_t)( (*(i+dual_line_start+1) << 4) | ((*(i+dual_line_start+2) >> 4) & 0x0F) ) << 4; //red
					currentPixel[2] = (uint16_t)( (*(i+dual_line_start+BYTES_PER_LINE) << 4) | (*(i+dual_line_start+2+BYTES_PER_LINE) & 0x0F) ) << 4; //blue
					
					currentPixel[1] = (GreenPixel1 << 3) + (GreenPixel2 << 3);
					
					memcpy(output_line_buffer+i, currentPixel, 6);
				}
				res = TIFFWriteScanline(tif, output_line_buffer, l, 0);
				if (res < 1){
					cout << "Error writing scanline" << endl;
					ret ++;
				}
			}
			//~ cout << "done writing lines, closing tiff file here" << endl;
			TIFFClose(tif); //closing file here
			if (output_line_buffer)
				_TIFFfree(output_line_buffer);
			free(input_buffer);
		}
		else {
			cout << "Incorrect key" << endl;
			ret++;
		}
	}
	fclose(f);
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
	clock_t start = clock();
	int out = jpg_to_raw(filepath, target_path);
	ret = 0;
	//~ clock_t end = clock();
	//~ double time_used = ((double)(end-start))/ CLOCKS_PER_SEC;
	//~ cout << time_used << endl;
	return ret;
}

