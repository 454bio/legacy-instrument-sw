#!/bin/bash

if [[ $EUID -ne 0 ]]; then
    echo "$0 is not running as root. Try using sudo."
    exit 2
fi

file=/boot/config.txt

echo -n "Updating $file..."

grep -q "^gpu_mem=" $file && sed -i.bak 's/^gpu_mem=.*/gpu_mem=256/' $file || echo "gpu_mem=256" >> $file
grep -q "^imx477_hv_sync_enable=" $file && sed -i.bak 's/^imx477_hv_sync_enable=.*/imx477_hv_sync_enable=1/' $file || echo "imx477_hv_sync_enable=1" >> $file
grep -q "^imx477_vsync_polarity=" $file && sed -i.bak 's/^imx477_vsync_polarity=.*/imx477_vsync_polarity=1/' $file || echo "imx477_vsync_polarity=1" >> $file
grep -q "^imx477_vsync_width=" $file && sed -i.bak 's/^imx477_vsync_width=.*/imx477_vsync_width=7/' $file || echo "imx477_vsync_width=7" >> $file
grep -q "^imx477_fstrobe_enable=" $file && sed -i.bak 's/^imx477_fstrobe_enable=.*/imx477_fstrobe_enable=1/' $file || echo "imx477_fstrobe_enable=1" >> $file
grep -q "^imx477_fstrobe_cont_trig=" $file && sed -i.bak 's/^imx477_fstrobe_cont_trig=.*/imx477_fstrobe_cont_trig=1/' $file || echo "imx477_fstrobe_cont_trig=1" >> $file
grep -q "^imx477_fstrobe_delay=" $file && sed -i.bak 's/^imx477_fstrobe_delay=.*/imx477_fstrobe_delay=3040/' $file || echo "imx477_fstrobe_delay=3040" >> $file
grep -q "^imx477_fstrobe_stills_only=" $file && sed -i.bak 's/^imx477_fstrobe_stills_only=.*/imx477_fstrobe_stills_only=1/' $file || echo "imx477_fstrobe_stills_only=1" >> $file
grep -q "^imx477_fstrobe_width=" $file && sed -i.bak 's/^imx477_fstrobe_width=.*/imx477_fstrobe_width=12000/' $file || echo "imx477_fstrobe_width=12000" >> $file

grep -q "^dtoverlay=w1-gpio" $file && sed -i.bak 's/^dtoverlay=w1-gpio.*/dtoverlay=w1-gpio/' $file || echo "dtoverlay=w1-gpio" >> $file

echo "Success!"
echo ""
echo "Please restart the system for the changes to take effect."
echo ""
