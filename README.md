# Stuff I had to install

### PYGObject
See https://pygobject.readthedocs.io/en/latest/getting_started.html#ubuntu-getting-started

Here's what I did
```
sudo apt install libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-3.0
```

### PiGPIO
See http://abyz.me.uk/rpi/pigpio/download.html

Here's what I did
```
git clone git@github.com:joan2937/pigpio.git
cd pigpio
make
sudo make install
```

### Bluetooth packages

```
sudo apt-get install bluetooth bluez libbluetooth-dev pi-bluetooth python-bluez
```
