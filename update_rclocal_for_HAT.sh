#!/bin/bash

if [[ $EUID -ne 0 ]]; then
    echo "$0 is not running as root. Try using sudo."
    exit 2
fi

file=/etc/rc.local

echo -n "Updating $file..."

grep -q "^pigs modes" $file && sed -i.bak 's/^pigs modes.*/pigs modes 7 r/' $file || echo "pigs modes 7 r" >> $file

echo "Success!"
echo ""
echo "Please restart the system for the changes to take effect."
echo ""
