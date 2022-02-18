#!/bin/bash
set -Eeuo pipefail

sudo apt-get -y update
sudo apt-get -y install openjdk-8-jre
sudo update-alternatives --skip-auto --config java
wget https://wsr.imagej.net/distros/cross-platform/ij153.zip
unzip ij153.zip -d ~/
rm ij153.zip

sed -i "s/quick_exec=0/quick_exec=1/" ~/.config/libfm/libfm.conf
wget https://upload.wikimedia.org/wikipedia/commons/d/db/ImageJLogo.png -O ~/ImageJ/icon.png

cat << 'EOF' > ~/ImageJ/run
#!/bin/bash

script_dir=$(cd \"$(dirname "${BASH_SOURCE[0]}\")\" &>/dev/null && pwd -P)
java -Xmx512m -jar /${script_dir}/ij.jar
EOF

chmod +x ~/ImageJ/run

cat << 'EOF' > ~/Desktop/ImageJ.desktop
[Desktop Entry]
Name=ImageJ
Version=1.0
Comment=Launches ImageJ
Exec=/home/pi/Downloads/ImageJ/run
Icon=/home/pi/Downloads/ImageJ/icon.png
Terminal=false
Type=Application
Categories=Education
StartupNotify=true
EOF

chmod +x ~/Desktop/ImageJ.desktop