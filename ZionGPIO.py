import glob
import time
import multiprocessing
import itertools
from queue import Empty
from functools import partial
from typing import List, Dict

import pigpio
from ZionEvents import ZionEvent
from ZionLED import ZionLEDs, ZionLEDColor

# multiprocessing.set_start_method('spawn')

# Gpio Pin Lookup Table. Index is GPIO #, format is (pin #, enabled, alternate function)
# (can remove/trim if memory is an issue)
GpioPins = (
    (None, None,  None  ), #No GPIO 0
    (None, None,  None  ), #No GPIO 1
    (3,    False, 'I2C' ),
    (5,    False, 'I2C' ),
    (7,    True,  None  ), #Default pin for 1-wire interface
    (29,   True,  '1W'  ), #Using this pin for 1-wire instead (GPIO5 referenced in boot config)
    (31,   True,  None  ),
    (26,   False, 'SPI' ), #used for TFT
    (24,   False, 'SPI' ), #used for TFT
    (21,   False, 'SPI' ), #used for TFT
    (19,   False, 'SPI' ), #used for TFT
    (23,   False, 'SPI' ), #used for TFT
    (32,   True,  None  ),
    (33,   True,  None  ),
    (8,    False, 'UART'),
    (10,   False, 'UART'),
    (36,   True,  None  ),
    (11,   True,  None  ),
    (12,   True,  'PCM' ),
    (35,   True,  'PCM' ),
    (38,   True,  'PCM' ),
    (40,   True,  'PCM' ),
    (15,   True,  None  ),
    (16,   True,  None  ),
    (18,   True,  None  ),
    (22,   True,  None  ),
    (37,   True,  None  ))

# Now define GPIO uses for Zion:

# 2 GPIOs for each LED:
LED_GPIOS = {
    ZionLEDColor.UV: [12], #pin 32
    ZionLEDColor.BLUE: [16], #pins 36
    ZionLEDColor.ORANGE: [20], #pin 38
}

# 1 GPIO for camera capture timing testing:
CAMERA_TRIGGER = 21 #pin 40

#1 GPIO for heat control:
TEMP_OUTPUT = 13 #pin 33

# 1 GPIOs for temp sensing (to use 1-wire):
TEMP_INPUT_1W = 5 #pin 29

#1 GPIO for UV safety switch:
#TODO

#2 GPIOs for testing camera sync signals:
FSTROBE = 23 #pin 16
XVS = 24 #pin 18

class ZionPigpioProcess(multiprocessing.Process):
    def __init__(self, led_gpios=LED_GPIOS, temp_out_gpio=TEMP_OUTPUT, temp_in_gpio=TEMP_INPUT_1W, camera_trigger_gpio=CAMERA_TRIGGER):
        super().__init__()
        self.led_gpios = led_gpios
        self.temp_out_gpio = temp_out_gpio
        self.temp_in_gpio = temp_in_gpio
        self.camera_trigger_gpio = camera_trigger_gpio
        self.fstrobe_wave_id_queue = multiprocessing.Queue()
        self.xvs_wave_id = multiprocessing.Value('i', -1)
        self.stop_event = multiprocessing.Event()

    def run(self):
        self.pi = pigpio.pi()
        if not self.pi.connected:
            print("pigopio not connected!")
            return

        # pi.set_mode(FSTROBE, pigpio.INPUT)
        # pi.set_mode(XVS, pigpio.INPUT)

        # _fstrobe_cb_handle = pi.callback(FSTROBE, pigpio.RISING_EDGE)
        # _xvs_cb_handle = pi.callback(XVS, pigpio.RISING_EDGE)
        # xvs_tally_prev = 0
        # fstrobe_tally_prev = 0

        # while not self.stop_event.wait(0.5):
        #     fstrobe_tally_new = _fstrobe_cb_handle.tally()
        #     if fstrobe_tally_new != fstrobe_tally_prev:
        #         print(f"New fstrobe tally: {fstrobe_tally_new}")
        #         fstrobe_tally_prev = fstrobe_tally_new
        #     xvs_tally_new = _xvs_cb_handle.tally()
        #     if xvs_tally_new != xvs_tally_prev:
        #         print(f"New xvs tally: {xvs_tally_new}")
        #         xvs_tally_prev = xvs_tally_new
        #     print(f"Hit timeout -- fstrobe_tally_new: {fstrobe_tally_new}  xvs_tally_new: {xvs_tally_new}")


        self.pi.wave_clear()

        # Check that GPIO settings are valid:
        #TODO: may need adjustment for temperature output (eg if it takes more than one pin)
        for g in itertools.chain(*self.led_gpios.values(), [self.temp_out_gpio, self.camera_trigger_gpio]):
            if GpioPins[g][1]:
                self.pi.set_pull_up_down(g, pigpio.PUD_DOWN)
                self.pi.set_mode(g, pigpio.OUTPUT)
                self.pi.write(g, 0)  # Ensure they're off
            else:
                raise ValueError('Chosen GPIO is not enabled!')

        # Now make camera sync signals inputs:
        for g in [FSTROBE, XVS]:
            if GpioPins[g][1]:
                self.pi.set_mode(g, pigpio.INPUT)
            else:
                print(f"GPIO Pin {g} not enabled!")

        self._fstrobe_cb_handle = self.pi.callback(FSTROBE, pigpio.RISING_EDGE, self.fstrobe_cb)
        self._xvs_cb_handle = self.pi.callback(XVS, pigpio.RISING_EDGE, self.xvs_cb)

        print("Waiting for stop signal...")
        self.stop_event.wait()

        print("Received stop signal!")
        self._fstrobe_cb_handle.cancel()
        self._xvs_cb_handle.cancel()
        self.pi.wave_tx_stop()
        self.pi.wave_clear()
        self.pi.stop()
        print("ZionPigpioProcess done!")

    def stop(self):
        print("Setting stop signal...")
        self.stop_event.set()

    def fstrobe_cb(self, gpio, level, ticks):
        try:
            wave_id = self.fstrobe_wave_id_queue.get_nowait()
        except Empty:
            print("fstrobe_cb -- no wave_id")
        else:
            print(f"fstrobe_cb -- Some info passed in: {wave_id} -- gpio: {gpio}  level: {level}  ticks: {ticks}")
            ret = self.pi.wave_send_once(wave_id)
            print(f"fstrobe_cb -- ret: {ret}")

    def xvs_cb(self, gpio, level, ticks):
        if self.xvs_wave_id.value < 0:
            print(f"xvs_cb -- no wave_id --  gpio: {gpio}  level: {level}  ticks: {ticks}")
        else:
            print(f"xvs_cb -- Some info passed in: {self.xvs_wave_id.value} -- gpio: {gpio}  level: {level}  ticks: {ticks}")
            ret = self.pi.wave_send_once(self.xvs_wave_id.value)
            print(f"ret: {ret}")


class ZionGPIO():
    def __init__(self, led_gpios=LED_GPIOS, temp_out_gpio=TEMP_OUTPUT, temp_in_gpio=TEMP_INPUT_1W, camera_trigger_gpio=CAMERA_TRIGGER, parent=None):
        self.parent=parent

        #TODO: implement heat control output
        #No check for Temperature Input GPIO pin, this is done in boot config file (including GPIO choice)
        base_dir = '/sys/bus/w1/devices/'
        try:
            self.Temp_1W_device = glob.glob(base_dir + '28*')[0]
        except IndexError:
            print('Warning: 1-Wire interface not connected.')
            self.Temp_1W_device = None

        print(f"ZionGPIO -- get_start_method: {multiprocessing.get_start_method()}")
        ctx = multiprocessing.get_context("fork")
        self.pigpio_process = ZionPigpioProcess(led_gpios=led_gpios, temp_out_gpio=temp_out_gpio, temp_in_gpio=temp_in_gpio, camera_trigger_gpio=camera_trigger_gpio)
        self.pigpio_process.start()

    def camera_trigger(self, bEnable):
        print("camera_trigger -- need to signal spawned process")
        pass
        # self.write(self.Camera_Trigger, bEnable)

    def read_temperature(self):
        if self.Temp_1W_device:
            f = open(self.Temp_1W_device+'/w1_slave', 'r')
            lines = f.readlines()
            f.close()
            if not lines[0][-4:-1]=='YES':
                print('Serial communications issue!')
            else:
                equals_pos = lines[1].find('t=')
                temp_c = float(lines[1][equals_pos+2:])/1000.
                # ~ print('\nTemperature = '+str(temp_c)+' C')
            return temp_c
        else:
            return None

    def quit(self):
        print("Stopping GPIO...")
        self.pigpio_process.stop()
        self.pigpio_process.join()
        print("GPIO.pigpio_process done!")

    # def update_pwm_settings(self):
    #     null_wave = True
    #     for color, gpios in self.led_to_gpio_pins.items():
    #         for g in gpios:
    #             null_wave = False
    #             on = int(self.pS[color] * self.micros)
    #             length = int(self.dc[color] * self.micros)
    #             micros = int(self.micros)
    #             if length <= 0:
    #                 self.wave_add_generic([pigpio.pulse(0, 1<<g, micros)])
    #             elif length >= micros:
    #                 self.wave_add_generic([pigpio.pulse(1<<g, 0, micros)])
    #             else:
    #                 off = (on + length) % micros
    #                 if on<off:
    #                     self.wave_add_generic([
    #                         pigpio.pulse(   0, 1<<g,           on),
    #                         pigpio.pulse(1<<g,    0,     off - on),
    #                         pigpio.pulse(   0, 1<<g, micros - off),
    #                     ])
    #                 else:
    #                     self.pi.wave_add_generic([
    #                         pigpio.pulse(1<<g,    0,         off),
    #                         pigpio.pulse(   0, 1<<g,    on - off),
    #                         pigpio.pulse(1<<g,    0, micros - on),
    #                     ])
    #     if not null_wave:
    #         if not self.stop_event.is_set():
    #             new_wid = self.wave_create()
    #             if self.old_wid is not None:
    #                 self.wave_send_using_mode(new_wid, pigpio.WAVE_MODE_REPEAT_SYNC)
    #                 while self.wave_tx_at() != new_wid:
    #                     pass
    #                 self.wave_delete(self.old_wid)
    #             else:
    #                 self.wave_send_repeat(new_wid)
    #             self.old_wid = new_wid


    # def enable_leds(self, leds : ZionLEDs, verbose=False):
    #     for color, pulsetime in leds.items():
    #         # Temporary until pulsewidth is fully implemented
    #         self.enable_led(color, pulsetime/100, verbose=verbose, update=False)
    #     self.update_pwm_settings()

    def disable_all_leds(self, verbose=False):
        print("disable_all_leds -- TODO")
        # for color in ZionLEDColor:
        #     # Temporary until pulsewidth is fully implemented
        #     self.disable_leds(color, 0, verbose=verbose, update=False)
        # self.update_pwm_settings()

    # def disable_leds(self, leds : ZionLEDs, verbose=False):
    #     for color, pulsetime in leds.items():
    #         # Temporary until pulsewidth is fully implemented
    #         self.enable_led(color, 0, verbose=verbose, update=False)
    #     self.update_pwm_settings()

    # def enable_led(self, color : ZionLEDColor, amt : float, verbose : bool = False, update: bool =True):
    #     self.set_duty_cycle(color, amt)
    #     print(f"\nSetting {color.name} to {amt}")
    #     if verbose:
    #         self.parent.gui.printToLog(f"{color.name} set to {amt}")

    #     if update:
    #         self.update_pwm_settings()

    # def turn_on_led(self, color : ZionLEDColor, verbose : bool = False):
    #     amt = self.LED_DC[color] / 100.
    #     self.set_duty_cycle(self.LED_IDX[color], amt)
    #     print(f"\nSetting {color.name} to {amt}")
    #     if verbose:
    #         self.parent.gui.printToLog(f"{color.name} set to {amt}")

    #     self.update_pwm_settings()

    # def send_uv_pulse(self, pulsetime : float, dc : int):
    #     self.enable_led(ZionLEDColor.UV, dc)
    #     time.sleep(pulsetime / 1000.)
    #     self.enable_led(ZionLEDColor.UV, 0)

    def enable_vsync_callback(self, event : ZionEvent):
        print("enable_vsync_callback -- TODO")
        pass
        # self.callback_for_uv_pulse = self.callback(
        #     XVS,
        #     pigpio.RISING_EDGE,
        #     partial(self.parent.pulse_on_trigger, event)
        # )
