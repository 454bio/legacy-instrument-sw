import dbus

from BTAdvertisement import Advertisement
from BTService import Application, Service, Characteristic, Descriptor

from gpiozero import CPUTemperature

GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
NOTIFY_TIMEOUT = 5000

class ZionAdvertisement(Advertisement):
    def __init__(self, index):
        super(ZionAdvertisement, self).__init__(index, "peripheral")
        self.add_local_name("Zion")
        self.include_tx_power = True

class ZionService(Service):
    SVC_UUID = "00000001-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, index):
        super(ZionService, self).__init__(index, self.SVC_UUID, True)

        self.add_characteristic(ReportCharacteristic(self))
        self.add_characteristic(ParameterCharacteristic(self))
        self.add_characteristic(ProtocolCharacteristic(self))

        self.ParameterFile = 'default_parameter_file.txt'
        self.ProtocolFile = 'default_protocol_file.txt'

    def get_parameter_file(self):
        return self.ParameterFile

    def get_protocol_file(self):
        return self.ProtocolFile

    def set_parameter_file(self, filename):
        self.ParameterFile = filename

    def set_protocol_file(self, filename):
        self.ProtocolFile = filename


class ReportCharacteristic(Characteristic):
    UUID = "00000002-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, service):
        self.notifying = False

        super(ReportCharacteristic, self).__init__(
                self.UUID,
                ["notify", "read"], service)
        self.add_descriptor(ReportDescriptor(self))

    def get_temperature(self):
        value = []

        cpu = CPUTemperature()
        temp = cpu.temperature

        strtemp = str(round(temp, 1)) + " " + unit
        for c in strtemp:
            value.append(dbus.Byte(c.encode()))
        return value

    def set_temperature_callback(self):
        if self.notifying:
            value = self.get_temperature()
            self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])

        return self.notifying

    def StartNotify(self):
        if self.notifying:
            return

        self.notifying = True

        value = self.get_temperature()
        self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": value}, [])
        self.add_timeout(NOTIFY_TIMEOUT, self.set_temperature_callback)

    def StopNotify(self):
        self.notifying = False

    def ReadValue(self, options):
        value = self.get_temperature()

        return value

class ReportDescriptor(Descriptor):
    UUID = "2901"
    DESCRIPTOR_VALUE = "Zion Report"

    def __init__(self, characteristic):
        super(ReportDescriptor, self).__init__(
                self.UUID,
                ["read"],
                characteristic)

    def ReadValue(self, options):
        value = []
        desc = self.DESCRIPTOR_VALUE

        for c in desc:
            value.append(dbus.Byte(c.encode()))
        return value

class ParameterCharacteristic(Characteristic):
    UUID = "00000003-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, service):
        super(ParameterCharacteristic, self).__init__(
                self.UUID,
                ["read", "write"], service)
        self.add_descriptor(ParameterDescriptor(self))

    def WriteValue(self, value, options):
#        val = str(value[0]).upper()
         val = value
         self.service.set_parameter_file(val)

    def ReadValue(self, options):
        value = []
        val = self.service.get_parameter_file()
        for c in val:
            value.append(dbus.Byte(c.encode()))
        return value


class ParameterDescriptor(Descriptor):
    UUID = "2901"
    DESCRIPTOR_VALUE = "Parameter File"

    def __init__(self, characteristic):
        super(ParameterDescriptor, self).__init__(
                self.UUID,
                ["read"],
                characteristic)

    def ReadValue(self, options):
        value = []
        desc = self.DESCRIPTOR_VALUE
        for c in desc:
            value.append(dbus.Byte(c.encode()))
        return value

class ProtocolCharacteristic(Characteristic):
    UUID = "00000004-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, service):
        super(ProtocolCharacteristic, self).__init__(
                self.UUID,
                ["read", "write"], service)
        self.add_descriptor(ProtocolDescriptor(self))

    def WriteValue(self, value, options):
#        val = str(value[0]).upper()
         val = value
         self.service.set_protocol_file(val)

    def ReadValue(self, options):
        value = []
        val = self.service.get_protocol_file()
        for c in val:
            value.append(dbus.Byte(c.encode()))
        return value


class ProtocolDescriptor(Descriptor):
    UUID = "2902"
    DESCRIPTOR_VALUE = "Protocol File"

    def __init__(self, characteristic):
        super(ProtocolDescriptor, self).__init__(
                self.UUID,
                ["read"],
                characteristic)

    def ReadValue(self, options):
        value = []
        desc = self.DESCRIPTOR_VALUE
        for c in desc:
            value.append(dbus.Byte(c.encode()))
        return value


app = Application()
app.add_service(ThermometerService(0))
app.register()

adv = ThermometerAdvertisement(0)
adv.register()

try:
    app.run()
except KeyboardInterrupt:
    app.quit()