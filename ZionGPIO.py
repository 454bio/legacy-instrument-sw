import glob
import multiprocessing
import multiprocessing.synchronize
from operator import methodcaller, attrgetter
import threading
import itertools
import traceback
from collections.abc import Iterable
from multiprocessing.managers import Namespace
from queue import Empty, Full
from typing import Optional, Iterable, Dict

from ZionErrors import ZionInvalidLEDColor, ZionInvalidLEDPulsetime

import pigpio
from ZionEvents import ZionEvent
from ZionLED import ZionLEDs, ZionLEDColor

# multiprocessing.set_start_method('spawn')

# Gpio Pin Lookup Table. Index is GPIO #, format is (pin #, enabled, alternate function)
GpioPins = (
    (None, None,  None  ), #No GPIO 0
    (None, None,  None  ), #No GPIO 1
    (3,    False, 'I2C' ),
    (5,    False, 'I2C' ),
    (7,    True,  '1W'  ), #Pin for 1-wire interface, used for TEMP1W (setup in boot config)
    (29,   True,  None  ),
    (31,   True,  None  ),
    (26,   False, None  ), #was SPI, used for bluetooth button now
    (24,   False, None  ), #was SPI, used for fan now
    (21,   False, None  ), #was SPI, used for fan now
    (19,   False, 'SPI' ), #used for case leds
    (23,   False, 'SPI' ), #used for case leds
    (32,   True,  None  ),
    (33,   True,  None  ),
    (8,    True, None  ), #also used for UART TX
    (10,   True, None  ), #also used for UART RX
    (36,   True,  None  ),
    (11,   True,  None  ),
    (12,   True,  None  ),
    (35,   True,  None  ),
    (38,   True,  None  ),
    (40,   True,  None  ),
    (15,   True,  None  ),
    (16,   True,  None  ),
    (18,   True,  None  ),
    (22,   True,  None  ),
    (37,   True,  None  ),
    (13,   True,  None  ))

# Now define GPIO uses for Zion:

# 2 GPIOs for each LED:
LED_GPIOS = {
    # TODO: Need to add assert that the keys of LED_GPIOS are ZionLEDColor
    ZionLEDColor.UV: [16,17,20,21], #LED_ENs 0,1,4,5 hw pins 36,11,38,40
    ZionLEDColor.BLUE: [22,23], #LED_ENs 6,7 hw pins 15,16
    ZionLEDColor.ORANGE: [18,19], #LED_ENs 2,3 hw pins 12,35
    # TODO: update color names here and/or assign multiple GPIOs to colors
    ZionLEDColor.COLOR3: [],
    ZionLEDColor.COLOR4: [],
    ZionLEDColor.COLOR5: [],
    ZionLEDColor.COLOR6: [],
    ZionLEDColor.COLOR7: [],
}

#2 GPIOs for testing camera sync signals:
FSTROBE = 5 #pin 29
XVS = 6 #pin 31

# 2 GPIOs for camera capture timing testing & debugging:
# TODO if we ever use UART, re-assign these
CAMERA_TRIGGER = 14 #pin 8 (TX)
DEBUG_TRIGGER = 15 # pin 10 (RX)

#1 GPIO for heat control:
TEMP_OUTPUT = 13 #pin 33
#1 GPIOs for temp sensing (to use 1-wire):
TEMP_INPUT_1W = 4 #pin 7 (configured in boot config file)

#1 GPIO for bluetooth pairing button:
# TODO double check where this is set up (eg rc local?)
BT_BUTTON = 7 #pin 26 (configured in OS)
#SPI clk and mosi for case LEDS (configued in OS):
CASE_LEDS_MOSI = 10 #pin 19 
CASE_LEDS_CLK = 11 #pin 23

#HW ID pins (MSb first):
# TODO should this be LSb first?
HW_ID = (27, 26, 25, 24) #pins (13, 37, 22, 18)

#Fan stuff:
FAN_ON = 8 #pin 24
FAN_PWM = 12 #pin 32
FAN_TACH = 9 #pin 21

class ZionPigpioProcess(multiprocessing.Process):
    def __init__(self, xvs_delay_ms: float = 0.0, led_gpios=LED_GPIOS,
                temp_out_gpio=TEMP_OUTPUT, temp_in_gpio=TEMP_INPUT_1W,
                camera_trigger_gpio=CAMERA_TRIGGER, debug_trigger_gpio=DEBUG_TRIGGER):
        super().__init__()
        self.led_gpios = led_gpios
        self.temp_out_gpio = temp_out_gpio
        self.temp_in_gpio = temp_in_gpio
        self.camera_trigger_gpio = camera_trigger_gpio
        self.debug_trigger_gpio = debug_trigger_gpio

        self._mp_manager = multiprocessing.Manager()
        self.mp_namespace = self._mp_manager.Namespace()
        self.mp_namespace.toggle_led_wave_id = -1
        self.mp_namespace.xvs_delay = int(xvs_delay_ms * 1000) # Delay between XVS and FSTROBE
        self.fstrobe_wave_id_queue = self._mp_manager.Queue()
        self.event_led_wave_id_queue = self._mp_manager.Queue()
        self.toggle_led_queue = self._mp_manager.Queue()
        self.camera_trigger_event = self._mp_manager.Event()
        self.debug_trigger_event = self._mp_manager.Event()
        self.stop_event = self._mp_manager.Event()
        self.capture_busy = self._mp_manager.Event()
        self.fstrobe_sent = self._mp_manager.Event()
        self.event_led_wave_id_done_event = self._mp_manager.Event()
        self.event_led_wave_ids = self._mp_manager.dict()
        self.mp_namespace.num_event_frames = 0
        self.mp_namespace.num_fstrobes = 0

    def run(self):
        self._init_pigpio()
        self._start_child_threads()

        print("Waiting for stop signal...")
        self.stop_event.wait()
        print("Received stop signal!")

        self._cleanup()

    def _init_pigpio(self):
        """ Initialize pigpio and configure the GPIO pins """
        self.pi = pigpio.pi()
        if not self.pi.connected:
            print("pigopio not connected!")
            raise RuntimeError("Could not start pigpio!")

        self.pi.wave_clear()

        # Check that GPIO settings are valid:
        #TODO: may need adjustment for temperature output (eg if it takes more than one pin)
        for g in itertools.chain(*self.led_gpios.values(), [self.temp_out_gpio, self.camera_trigger_gpio, self.debug_trigger_gpio]):
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

        # Add the callbacks
        self._fstrobe_cb_handle = self.pi.callback(FSTROBE, pigpio.RISING_EDGE, self.fstrobe_cb)
        self._xvs_cb_handle = self.pi.callback(XVS, pigpio.RISING_EDGE, self.xvs_cb)

    def _start_child_threads(self):
        self._toggle_led_handle = threading.Thread(
            target=self._toggle_led_thread,
            args=(self.mp_namespace, self.toggle_led_queue, self.pi)
        )
        self._toggle_led_handle.daemon = True
        self._toggle_led_handle.start()

        self._event_led_handle = threading.Thread(
            target=self._event_led_thread,
            args=(self.event_led_wave_ids, self.event_led_wave_id_queue, self.event_led_wave_id_done_event, self.pi)
        )
        self._event_led_handle.daemon = True
        self._event_led_handle.start()

        self._camera_trigger_handle = threading.Thread(
            target=self._camera_trigger_thread,
            args=(self.camera_trigger_event, self.stop_event, self.pi)
        )
        self._camera_trigger_handle.daemon = True
        self._camera_trigger_handle.start()

        self._debug_trigger_handle = threading.Thread(
            target=self._debug_trigger_thread,
            args=(self.debug_trigger_event, self.stop_event, self.pi)
        )
        self._debug_trigger_handle.daemon = True
        self._debug_trigger_handle.start()

    def _cleanup(self):
        """ Cleanup pigpio and signal the child threads to quit """
        self.camera_trigger_event.set()
        self.toggle_led_queue.put((None, None))
        self.event_led_wave_id_queue.put(None)
        self._fstrobe_cb_handle.cancel()
        self._xvs_cb_handle.cancel()

        self._toggle_led_handle.join(1.0)
        if self._toggle_led_handle.is_alive():
            print("_toggle_led_thread is still alive!")

        self._event_led_handle.join(1.0)
        if self._event_led_handle.is_alive():
            print("_event_led_thread is still alive!")

        self._camera_trigger_handle.join(1.0)
        if self._camera_trigger_handle.is_alive():
            print("_camera_trigger_thread is still alive!")

        self._debug_trigger_handle.join(1.0)
        if self._debug_trigger_handle.is_alive():
            print("_debug_trigger_thread is still alive!")

        self.pi.wave_tx_stop()
        self.pi.wave_clear()
        self.pi.stop()
        print("ZionPigpioProcess done!")

    def stop(self):
        print("Setting stop signal...")
        self.stop_event.set()

    def get_num_fstrobes(self):
        return self.mp_namespace.num_fstrobes

    def get_capture_busy_event(self) -> multiprocessing.Event:
        return self.capture_busy

    def fstrobe_cb(self, gpio, level, ticks):

        if self.capture_busy.is_set():
            print(f"fstrobe_cb -- capture is busy...")
            return

        try:
            wave_id = self.fstrobe_wave_id_queue.get_nowait()
        except Empty:
            pass
        else:
            if wave_id < 0:
                print(f"fstrobe_cb -- No LED this image...")
            else:
                ret = self.pi.wave_send_once(wave_id)
                print(f"fstrobe_cb -- Sent wave_id: {wave_id}  num_frames: {self.mp_namespace.num_frames}")

            self.mp_namespace.num_frames += 1
        finally:
            self.mp_namespace.num_fstrobes += 1
            print(f"# fstrobes: {self.mp_namespace.num_fstrobes}")

    def xvs_cb(self, gpio, level, ticks):
        """ Triggers on XVS Rising Edge. If self.mp_namespace.toggle_led_wave_id is set then it will send it. """
        if self.mp_namespace.toggle_led_wave_id > -1:
            self.pi.wave_send_once(self.mp_namespace.toggle_led_wave_id)

    def enable_toggle_led(self, color : ZionLEDColor, pulse_width : int):
        """ Will send the color/pulse_width to _toggle_led_thread so it can add it to pigpio. """
        self.toggle_led_queue.put((color, pulse_width))

    @staticmethod
    def _add_led_waveform(led : ZionLEDs, pi : pigpio.pi, delay : int = 0) -> bool:
        """ Adds waveforms for the pulsewidths/colors in led. Returns True if a wave was added """
        added_wf = False
        for color, pw in led.items():
            if pw > 0:
                led_wf = []
                gpio_bits = 0
                for led_pin in LED_GPIOS[color]:
                    gpio_bits |= 1<<led_pin

                if delay:
                    print(f"Appending pulse -- bits: {hex(gpio_bits)}  color: {color.name}  pw: {pw}  delay: {delay}")
                    led_wf.append(pigpio.pulse(0, 0, delay))
                else:
                    print(f"Appending pulse -- bits: {hex(gpio_bits)}  color: {color.name}  pw: {pw}")

                led_wf.append(pigpio.pulse(gpio_bits, 0, pw * 1000))
                led_wf.append(pigpio.pulse(0, gpio_bits, 0))
                pi.wave_add_generic(led_wf)
                added_wf = True

        return added_wf

    def _camera_trigger_thread(self, camera_trigger_event : multiprocessing.Event, stop_event : multiprocessing.Event, pi : pigpio.pi):
        """ Send a pulse on the DEBUG pin. """
        while True:
            camera_trigger_event.wait()
            if stop_event.is_set():
                print("_camera_trigger_thread -- received stop signal!")
                camera_trigger_event.clear()
                break
            pi.gpio_trigger(self.camera_trigger_gpio, 100, 1)
            camera_trigger_event.clear()

    def _debug_trigger_thread(self, debug_trigger_event : multiprocessing.Event, stop_event : multiprocessing.Event, pi : pigpio.pi):
        """ Send a pulse on the DEBUG pin. """
        while True:
            debug_trigger_event.wait()
            if stop_event.is_set():
                print("_debug_trigger_thread -- received stop signal!")
                debug_trigger_event.clear()
                break
            pi.gpio_trigger(self.debug_trigger_gpio, 100, 1)
            debug_trigger_event.clear()

    def _toggle_led_thread(self, mp_namespace : Namespace, toggle_led_queue : multiprocessing.Queue, pi : pigpio.pi):
        """ Add a wave_id for the given color and pulsewidth. """
        toggle_leds_pw = ZionLEDs()
        xvs_delay = mp_namespace.xvs_delay

        while True:
            led, pulse_width = toggle_led_queue.get()
            if led is None:
                print("toggle_led_thread -- received stop signal!")
                break

            print(f"toggle_led_thread -- Received command -- led: {led}  pulse_width: {pulse_width}")

            try:
                toggle_leds_pw[led] = pulse_width
            except ZionInvalidLEDColor:
                print(f"ERROR: {led} is not a valid LED color!")
                continue
            except ZionInvalidLEDPulsetime:
                print(f"ERROR: {pulse_width} is not a valid pulse width. Valid range is 0-{toggle_leds_pw.max_pulsetime}!")
                continue

            added_wf = self._add_led_waveform(led=toggle_leds_pw, pi=pi, delay=xvs_delay)

            old_wave_id = mp_namespace.toggle_led_wave_id

            if added_wf:
                new_wave_id = pi.wave_create()
                print(f"New toggle wave_id: {new_wave_id}")
                mp_namespace.toggle_led_wave_id = new_wave_id
            else:
                # We didn't add any waveforms
                print(f"No active leds")
                mp_namespace.toggle_led_wave_id = -1

            if old_wave_id > -1:
                pi.wave_delete(old_wave_id)

    def _event_led_thread(self, event_led_wave_ids : Dict[ZionLEDs, int], event_led_queue : multiprocessing.Queue, done_event : multiprocessing.Event, pi : pigpio.pi):
        """ Adds wave_ids to the shared event_led_wave_ids Dictionary. Will only add a new ID if it's unique. """
        while True:
            leds = event_led_queue.get()
            if leds is None:
                print("event_led_thread -- received stop signal!")
                break

            print(f"event_led_thread -- Received command -- leds: {leds}")

            # Delete the old event LEDs
            for led, wave_id in event_led_wave_ids.items():
                try:
                    if wave_id > -1:
                        pi.wave_delete(wave_id)
                except pigpio.error as e:
                    print(f"could not delete wave_id {wave_id} -- {e}")
                except Exception as e:
                    tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                    print(f"_event_led_thread -- Error deleting previous waveform id {wave_id} for led: {led}!! -- {tb}")
                    continue

            # Add new leds
            for led in leds:
                added_wf = self._add_led_waveform(led=led, pi=pi)

                if added_wf:
                    wave_id = pi.wave_create()
                    print(f"_event_led_thread -- New event wave_id: {wave_id}")
                else:
                    # We didn't add any waveforms
                    wave_id = -1
                    print(f"_event_led_thread -- No active leds for event!")

                event_led_wave_ids[led] = wave_id

            try:
                done_event.set()
            except Exception as e:
                tb = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                print(f"_event_led_thread -- Problem setting done_event! -- {tb}")
                continue

    def create_event_led_wave_ids(self, leds : Iterable[ZionLEDs], blocking : bool = True, done_event : Optional[multiprocessing.Event] = None):
        """
        Create corresponding wave ids for the passed in list of ZionLEDs.
        Will only create a wave_id if the requested combination of colors and pulse widths.
        Optionally, you can set `blocking=True` to have this function wait until the LEDs have been processed before returning.
        You can also pass in an Multiprocessing.Event() to signal when the processing is done.
        """
        if not isinstance(done_event, (type(None), multiprocessing.synchronize.Event)):
            raise RuntimeError("done_event must be either None or a multiprocessing.Event type!")

        print("Cleared self.event_led_wave_id_done_event")
        self.event_led_wave_id_done_event.clear()

        if not isinstance(leds, Iterable) or not all(isinstance(x, ZionLEDs) for x in leds):
            print(f"isinstance(leds, Iterable): {isinstance(leds, Iterable)}")
            print(f"all(isinstance(x, ZionLEDs) for x in leds): {all(isinstance(x, ZionLEDs) for x in leds)}")
            print(f"leds: {leds}")
            raise RuntimeError(f"Must pass in an iterable of `ZionLEDs`!  Passed in: {type(leds)}")

        print(f"Calling self.event_led_wave_id_queue.put({leds})")
        self.event_led_wave_id_queue.put(leds)

        if blocking:
            print("Waiting for done event...")
            if not self.event_led_wave_id_done_event.wait(10.0):
                print("ERROR: Timed out waiting for done_event to be set!")

        if done_event:
            done_event.set()

    def update_event_led_wave_ids(self, leds : Iterable[ZionLEDs]):
        """ This will update any ZionLEDs that have a wave_id that's been added by _event_led_thread """
        for led in leds:
            led.set_wave_id(self.event_led_wave_ids.get(led, -1))

    def start_events(self, wave_ids: Iterable[int]):
        """ This will run the passed in wave_ids for every frame """
        self.mp_namespace.num_frames = 0
        if not self.fstrobe_wave_id_queue.empty():
            print(f"WARNING! We were expecting the event queue for fstrobe to empty!!")

        num_events = 0
        try:
            for wave_id in wave_ids:
                self.fstrobe_wave_id_queue.put_nowait(wave_id)
                num_events += 1
        except Full:
            print(f"ERROR: Could not put event {num_events} on the queue!!")

        print(f"Num Events: {num_events}")

    def clear_events(self):
        """ Clears the fstrobe wave ids queue so it won't turn on LEDs """
        while True:
            try:
                _ = self.fstrobe_wave_id_queue.get_nowait()
            except Empty:
                break

    def send_camera_trigger(self):
        """ Send a pulse on the camera_trigger pin """
        self.camera_trigger_event.set()

    def send_debug_trigger(self):
        """ Send a pulse on the debug_trigger pin """
        self.debug_trigger_event.set()


class ZionGPIO():
    def __init__(
        self, led_gpios=LED_GPIOS, temp_out_gpio=TEMP_OUTPUT, temp_in_gpio=TEMP_INPUT_1W, 
        camera_trigger_gpio=CAMERA_TRIGGER, parent : Optional['ZionSession'] = None
    ):
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
        if parent:
            xvs_delay = parent.Camera.readout_ms
        else:
            xvs_delay = 86.8422816

        self.pigpio_process = ZionPigpioProcess(led_gpios=led_gpios, temp_out_gpio=temp_out_gpio, temp_in_gpio=temp_in_gpio, camera_trigger_gpio=camera_trigger_gpio, xvs_delay_ms=xvs_delay)
        self.pigpio_process.start()

    def camera_trigger(self):
        self.pigpio_process.send_camera_trigger()

    def debug_trigger(self):
        self.pigpio_process.send_debug_trigger()

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

    def get_num_fstrobes(self):
        return self.pigpio_process.get_num_fstrobes()

    def get_capture_busy_event(self) -> multiprocessing.Event:
        return self.pigpio_process.get_capture_busy_event()

    def quit(self):
        print("Stopping GPIO...")
        self.pigpio_process.stop()
        self.pigpio_process.join()
        print("GPIO.pigpio_process done!")


    # def enable_leds(self, leds : ZionLEDs, verbose=False):
    #     for color, pulsetime in leds.items():
    #         # Temporary until pulsewidth is fully implemented
    #         self.enable_led(color, pulsetime/100, verbose=verbose, update=False)
    #     self.update_pwm_settings()

    def disable_all_leds(self, verbose=False):
        for color in ZionLEDColor:
            # Temporary until pulsewidth is fully implemented
            self.disable_toggle_led(color, verbose=verbose)

    # def disable_leds(self, leds : ZionLEDs, verbose=False):
    #     for color, pulsetime in leds.items():
    #         # Temporary until pulsewidth is fully implemented
    #         self.enable_led(color, 0, verbose=verbose, update=False)
    #     self.update_pwm_settings()

    def enable_toggle_led(self, color : ZionLEDColor, amt : int, verbose : bool = False):
        print(f"\nSetting {color.name} to {amt}")

        self.pigpio_process.enable_toggle_led(color, amt)
        if verbose:
            self.parent.gui.printToLog(f"{color.name} set to {amt}")

    def disable_toggle_led(self, color : ZionLEDColor, verbose : bool = False):
        print(f"\nSetting {color.name} to 0")
        self.pigpio_process.enable_toggle_led(color, 0)
        if verbose:
            self.parent.gui.printToLog(f"{color.name} set to 0")

    def load_event_led_wave_ids(self, flat_events : Iterable['ZionEvent']):
        """ Load the LED information into pigpio for the passed in list of events """
        # Find just the unique LED configurations to create wave_ids for
        unique_leds = set(map(attrgetter('leds'), flat_events))
        print(f"   # unique leds: {len(unique_leds)}")

        # Create the wave_ids
        self.pigpio_process.create_event_led_wave_ids(unique_leds)

        # Update our representation of the LEDs with the waveform ID
        # also load up the fstrobe callback queue
        self.pigpio_process.update_event_led_wave_ids(map(attrgetter('leds'), flat_events))

        # Load up the fstrobe queue
        self.pigpio_process.start_events(map(methodcaller('get_wave_id'), map(attrgetter('leds'), flat_events)))

    def disable_event_leds(self):
        """ Clear the fstrobe queue of wave ids. Even if fstrobe fires it won't send an wave """
        self.pigpio_process.clear_events()

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
