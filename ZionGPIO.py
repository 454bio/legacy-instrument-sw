import glob
import time
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
from ZionLED import ZionLEDs, ZionLEDColor, ZionLEDTimings

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
    ZionLEDColor.UV: [18,19,22,23], #LED_ENs 2,3,6,7 gpio hw pins 12,35,15,16
    ZionLEDColor.BLUE: [16,17], #LED_ENs 0,1 gpio hw pins 36,11
    ZionLEDColor.ORANGE: [20,21], #LED_ENs 4,5 gpio hw pins 38,40
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
                camera_trigger_gpio=CAMERA_TRIGGER, debug_trigger_gpio=DEBUG_TRIGGER,
                PID_Params=None):
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


        self.Temp_1W_device = None
        # ~ P=10, I=2, D=0, delta_t=1, ramp_threshold=10, target_temp=25
        self.mp_namespace.temperature = None
        
        self.mp_namespace.pid_reset = True
        self.mp_namespace.pid_enable = False
        if PID_Params is not None:
            self.mp_namespace.target_temp = PID_Params['Target_Temperature']
            self.pid_bias = PID_Params['bias']
            self.mp_namespace.P = PID_Params['P']
            self.mp_namespace.I = PID_Params['I']
            # ~ self.mp_namespace.D = PID_Params['D']
            self.mp_namespace.pid_delta_t = 1 #PID_Params['delta_t']
            self.pid_freq = PID_Params['PWM_Frequency']
        self.pid_ramp_threshold = None

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
                
        #No check for Temperature Input GPIO pin, this is done in boot config file (including GPIO choice)
        print('checking for 1-wire interface')
        base_dir = '/sys/bus/w1/devices/'
        try:
            self.Temp_1W_device = glob.glob(base_dir + '28*')[0]
            print('1-wire interface found at '+ self.Temp_1W_device)
        except IndexError:
            print('Warning: 1-Wire interface not connected.')
            self.Temp_1W_device = None

        # Add the callbacks
        self._fstrobe_cb_handle = self.pi.callback(FSTROBE, pigpio.RISING_EDGE, self.fstrobe_cb)
        self._xvs_cb_handle = self.pi.callback(XVS, pigpio.RISING_EDGE, self.xvs_cb)
        
        #print(self.Temp_1W_device)
        #if self.Temp_1W_device is not None:
        #    self.PID = ZionPID(self, self.temp_out_gpio)
        #else:
        #    print('no 1W device, not creating PID')


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
        
        self._pid_loop = threading.Thread(
			target=self._pid_control_thread,
			args = (self.mp_namespace, self.pid_freq, self.pid_bias, self.pid_ramp_threshold, self.temp_out_gpio, self.pi)
		)
        self._pid_loop.daemon = True
        self._pid_loop.start()

    def _cleanup(self):
        """ Cleanup pigpio and signal the child threads to quit """
        self.camera_trigger_event.set()
        self.toggle_led_queue.put((None, None, None, None))
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
        
        #TODO: necessary? it'll always be still alive
        self.mp_namespace.pid_enable = False
        self.pi.set_PWM_dutycycle(self.temp_out_gpio,0)
        # ~ self._pid_loop.join(1.0)
        # ~ if self._pid_loop.is_alive():
            # ~ print("_pid_control_thread is still alive!")

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

    def enable_toggle_led(self, color : ZionLEDColor, amt : int, timings : list=None, levels : list=None):
        """ Will send the color/pulse_width to _toggle_led_thread so it can add it to pigpio. """
        self.toggle_led_queue.put((color, amt, timings, levels))
        
    def enable_PID(self, bEnable):
        if bEnable:
            self.mp_namespace.pid_reset = True
            self.mp_namespace.pid_enable = True
        else:
            self.mp_namespace.pid_enable = False

    def _pid_control_thread(self, mp_namespace : Namespace, freq, bias, pid_ramp_threshold : int,  gpio, pi : pigpio.pi):
        #First initialize/configure loop:
        pi.set_PWM_frequency(gpio, freq)
        pi.set_PWM_range(gpio, 1000)
        mp_namespace.temperature = self._read_temperature()
        error = 0
        interror = 0
        roundoff = 0
        
        #Now turn on ramp 100% if we're far away
        # ~ if mp_namespace.pid_enable and pid_ramp_threshold is not None:
            # ~ if mp_namespace.target_temp - mp_namespace.temperature > pid_ramp_threshold:
                # ~ pi.set_PWM_dutycycle(gpio, 100)
                # ~ print('starting initial ramp, temp = '+str(mp_namespace.temperature ))
                # ~ while mp_namespace.target_temp - mp_namespace.temperature > pid_ramp_threshold:
                    # ~ mp_namespace.temperature = self._read_temperature()
                    # ~ time.sleep(mp_namespace.pid_delta_t)
                    
        while True:
            t0 = time.perf_counter()
            mp_namespace.temperature = self._read_temperature()
            if mp_namespace.pid_enable:
                if mp_namespace.pid_reset:
                    print('control loop started')
                    timer_time = int(0)
                    prev_time = time.time()
                    roundoff = 0
                    #dc_cnt = 1
                    #dc_tot = 0
                    mp_namespace.pid_reset = False

                curr_time = time.time()
                delta_t = curr_time-prev_time
                timer_time += int(1000*delta_t)
                error = mp_namespace.target_temp-mp_namespace.temperature
                interror += mp_namespace.I*error*delta_t
                pid_value = bias + (mp_namespace.P*error + interror) #todo add D term?
                
                #print(f'temp={mp_namespace.temperature}, target={mp_namespace.target_temp},\nP={mp_namespace.P}, I={mp_namespace.I},\nerr={error}, ierr={interror},\ndc={mp_namespace.P}*{error}+{mp_namespace.I}*{interror} ~= {max(min( int(new_dc_value), 100 ),0)}')
                #if new_dc_value>0:
                #    dc_tot += new_dc_value
                #dc_avg = dc_tot/dc_cnt
                #dc_cnt += 1
                # ~ print('pwr_avg = '+str(pwr_avg))
                
                new_dc_value = int(pid_value + roundoff)
                if 0 <= new_dc_value <= 1000:
                    pi.set_PWM_dutycycle(gpio, new_dc_value)
                    roundoff = pid_value - new_dc_value
                elif new_dc_value < 0:
                    roundoff = 0
                    pi.set_PWM_dutycycle(gpio, 0)
                    new_dc_value = 0
                else: #new_dc_value > 1000
                    roundoff = 0
                    pi.set_PWM_dutycycle(gpio, 1000)
                    new_dc_value = 1000
                print(f'{timer_time:010}, {mp_namespace.P:6.2f}, {mp_namespace.I:5.2f}, {mp_namespace.target_temp:3}, {mp_namespace.temperature:6.2f}, {pid_value:9.3f}, {0.1*new_dc_value:5.1f}')
                prev_time = curr_time
                
            else:
                pi.set_PWM_dutycycle(gpio, 0)
            t = time.perf_counter()-t0
            time.sleep( max([mp_namespace.pid_delta_t - t,0]) )


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
                    print(f"Appending pulse -- bits: {hex(gpio_bits)}  color: {color.name}  pw: {pw} (ms)  delay: {delay} (us)")
                    led_wf.append(pigpio.pulse(0, 0, delay))
                else:
                    print(f"Appending pulse -- bits: {hex(gpio_bits)}  color: {color.name}  pw: {pw} (ms)")

                led_wf.append(pigpio.pulse(gpio_bits, 0, pw * 1000))
                led_wf.append(pigpio.pulse(0, gpio_bits, 0))
                pi.wave_add_generic(led_wf)
                added_wf = True

        return added_wf
        
    @staticmethod
    def _add_complex_led_waveform(led : ZionLEDs, pi : pigpio.pi, delay : int = 0) -> bool:
        """ Adds COMPLEX waveforms for the pulsewidths/colors in led. Returns True if a wave was added.
            timings is a tuple of time amounts in microseconds, levels is a tuple of corresopnding high/low values."""

        added_wf = False

        for color, pw_timings_tpl in led.items():
            if pw_timings_tpl is not None:
                led_wf = []
                gpio_bits = 0
                for led_pin in LED_GPIOS[color]:
                    gpio_bits |= 1<<led_pin
                    
                print_wf_info = any(pw_timings_tpl[1])
                for timing, level in zip(*pw_timings_tpl):
                    if print_wf_info:
                        print(f"Appending pulse -- bits: {hex(gpio_bits)}  color: {color.name}  level: {int(level)}  timing: {int(timing/1000)}")
                    if level: # actually send pulse
                        led_wf.append(pigpio.pulse(gpio_bits, 0, int(timing)))
                    else: #actually send delay
                        led_wf.append(pigpio.pulse(0, gpio_bits, int(timing)))

                # ~ #led_wf.append(pigpio.pulse(0, gpio_bits, 0))
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
        toggle_leds_pw = ZionLEDTimings()
        xvs_delay = mp_namespace.xvs_delay

        while True:
            led, pulse_width, timings, levels = toggle_led_queue.get()
            if led is None:
                print("toggle_led_thread -- received stop signal!")
                break

            print(f"toggle_led_thread -- Received command -- led: {led}  pulse_width: {pulse_width}")
            
            ##TODO: update the checking necessary...
            try:
                #toggle_leds_pw[led] = pulse_width
                toggle_leds_pw.set_pulsetimings(led, (timings, levels))
            except ZionInvalidLEDColor:
                print(f"ERROR: {led} is not a valid LED color!")
                continue
            except ZionInvalidLEDPulsetime:
                print(f"ERROR: {pulse_width} is not a valid pulse width. Valid range is 0-{toggle_leds_pw.max_pulsetime}!")
                continue

            added_wf = self._add_complex_led_waveform(led=toggle_leds_pw, pi=pi) #delays are now embedded in toggle_leds_pw
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
        
    def _read_temperature(self):
        if self.Temp_1W_device is not None:
            f = open(self.Temp_1W_device+'/w1_slave', 'r')
            lines = f.readlines()
            f.close()
            if not lines[0][-4:-1]=='YES':
                print('Serial communications issue!')
            else:
                equals_pos = lines[1].find('t=')
                temp_c = float(lines[1][equals_pos+2:])/1000.
                #print('\nTemperature = '+str(temp_c)+' C')
            return temp_c
        else:
            return None

class ZionGPIO():
    def __init__(
        self, led_gpios=LED_GPIOS, temp_out_gpio=TEMP_OUTPUT, temp_in_gpio=TEMP_INPUT_1W, 
        camera_trigger_gpio=CAMERA_TRIGGER, PID_Params=None, parent : Optional['ZionSession'] = None
    ):
        self.parent=parent

        print(f"ZionGPIO -- get_start_method: {multiprocessing.get_start_method()}")
        if parent:
            xvs_delay = parent.Camera.readout_ms
        else:
            xvs_delay = 86.8422816

        self.pigpio_process = ZionPigpioProcess(led_gpios=led_gpios,
                                                temp_out_gpio=temp_out_gpio, temp_in_gpio=temp_in_gpio,
                                                camera_trigger_gpio=camera_trigger_gpio, xvs_delay_ms=(1000/self.parent.Camera.framerate)+xvs_delay-(self.parent.Camera.exposure_speed/1000),
                                                PID_Params=PID_Params)
        self.pigpio_process.start()

    def camera_trigger(self):
        self.pigpio_process.send_camera_trigger()

    def debug_trigger(self):
        self.pigpio_process.send_debug_trigger()



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

    def enable_toggle_led(self, color : ZionLEDColor, pulse_width : int, verbose : bool = False):
        print(f"\nSetting {color.name} to {pulse_width}")
        #pulse width is in milliseconds

        exp_time_us = self.parent.Camera.exposure_speed
        pw_us = 1000*pulse_width
        readout_us = 1000*self.parent.Camera.readout_ms
        fp_us = int(1000000/self.parent.Camera.framerate)
        xvs_delay_us = fp_us + readout_us - exp_time_us

        if exp_time_us > readout_us:
            if 0 < pw_us and pw_us < exp_time_us-readout_us:
                #off for xvs_delay, on for pw, off for fp-(pw+xvs_delay)
                timings = [xvs_delay_us, pw_us, exp_time_us - readout_us - pw_us]
                levels = [False, True, False]

            elif exp_time_us-readout_us <= pw_us and pw_us < fp_us:
                #on until pw+xvs_delay-fp, off for fp-pw, on for fp-xvs_delay
                timings = [pw_us + readout_us - exp_time_us, fp_us - pw_us, exp_time_us - readout_us]
                levels = [True, False, True]

            elif pw_us >= fp_us:
                timings = [fp_us]
                levels = [True]

            else: # 0 <= pw_us
                timings = [fp_us]
                levels = [False]

        else: #TODO: what about when exposure time is less than readout time?
            timings = [fp_us]
            levels = [False]

        self.pigpio_process.enable_toggle_led(color, pulse_width, timings, levels)
        if verbose:
            self.parent.gui.printToLog(f"{color.name} set to {pulse_width}")

    def disable_toggle_led(self, color : ZionLEDColor, verbose : bool = False):
        print(f"\nSetting {color.name} to 0")
        self.pigpio_process.enable_toggle_led(color, 0, [int(1000000/self.parent.Camera.framerate)], [False])
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
    
    def read_temperature(self):
        return self.pigpio_process._read_temperature()
    
    def set_target_temperature(self, temp):
        self.pigpio_process.mp_namespace.pid_reset = True
        self.pigpio_process.mp_namespace.target_temp = temp

    def enable_PID(self, bEnable):
        self.pigpio_process.enable_PID(bEnable)

# ~ class ZionPID():
	# ~ def __init__(self, parent, gpio, frequency=10, P=10, I=2, D=0, delta_t=1, ramp_threshold=10, target_temp=25):
		# ~ self.parent = parent
		# ~ self.gpio = gpio
		# ~ if GpioPins[gpio][1]:
			# ~ self.parent.pi.set_mode(gpio, pigpio.PUD_DOWN)
			# ~ self.parent.pi.set_PWM_range(gpio, 100)
			# ~ self.parent.pi.set_PWM_frequency(gpio,frequency)
		# ~ else:
			# ~ raise ValueError('Chosen GPIO is not enabled!')
		
		# ~ self.P = P
		# ~ self.I = I
		# ~ self.D = D
		
		# ~ self.delta_t = delta_t
		# ~ self.ramp_threshold = ramp_threshold
		# ~ self.target_temp = target_temp
		
		# ~ self.init_vars()
		# ~ self.set_dc(0)
		# ~ self.update_temp()
		
		# ~ self.Enable = False
		
	# ~ def enable_PID(self, bEnable):
		# ~ self.Enable = bEnable
		
	# ~ def init_vars(self):
		# ~ self.error = 0
		# ~ self.interror = 0
		# ~ self.dc_cnt = 1
		# ~ self.dc_tot = 0
	
	# ~ def set_P(self, p):
		# ~ self.P = p
	
	# ~ def set_I(self, i):
		# ~ self.I = i
	
	# ~ def set_D(self, d):
		# ~ self.D = d
		
	# ~ def set_target_temp(self, temp):
		# ~ self.target_temp = temp
		
	# ~ def set_frequency(self, freq):
		# ~ self.parent.pi.set_PWM_frequency(self.gpio,frequency)
		
	# ~ def set_dc(self, dc):
		# ~ self.parent.pi.set_PWM_dutycycle(self.gpio,dc)
		# ~ self.dc = dc
	
	# ~ def update_temp(self):
		# ~ self.temperature = self.parent._read_temperature()
		
	# ~ def pid_control_loop(self, bias=0):
		# ~ if self.Enable:
			# ~ self.update_temp()
			# ~ print('starting initial ramp, temp = '+str(self.temperature))
			# ~ self.set_dc(100)
			# ~ while self.target_temp - self.temperature > self.ramp_threshold:
				# ~ update_temp()
				# ~ time.sleep(self.delta_t)

			# ~ print('control loop started')
			# ~ prev_time = time.time()
			# ~ self.init_vars()
			# ~ while True:
				# ~ self.update_temp()
				# ~ curr_time = time.time()
				# ~ self.error = self.target_temp-self.temperature
				# ~ self.interror += error*(curr_time-prev_time)
				# ~ new_dc_value = bias + (self.P*self.error + self.I*self.interror) #todo add D term?
				# ~ print(str(curr_temp)+ ', power = '+str(power)+', error = '+str(error)+', interror = '+str(interror))
				# ~ if new_dc_value>0:
					# ~ self.dc_tot += new_dc_value
				# ~ self.dc_avg = self.dc_tot/self.dc_cnt
				# ~ self.dc_cnt += 1
				# ~ print('pwr_avg = '+str(pwr_avg))
				# ~ self.parent.pi.set_dc(max(min( int(new_dc_value), 100 ),0))
				# ~ prev_time = curr_time
				# ~ time.sleep(self.delta_t)
