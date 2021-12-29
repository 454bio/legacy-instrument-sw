#!/usr/bin/env python3

import dbus

from BTAdvertisement import Advertisement
from BTService import Application, Service, Characteristic, Descriptor

from ZionCelery import zion_report

GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
NOTIFY_TIMEOUT = 5000

STATUS_ERROR = 0 #failure
STATUS_PENDING = 1
STATUS_BUSY = 2 #started
STATUS_READY = 3 #success
STATUS_UNKNOWN = 4 #revoked? retry?

class ZionAdvertisement(Advertisement):
    def __init__(self, index):
        super(ZionAdvertisement, self).__init__(index, "peripheral")
        self.add_local_name("Zion")
        self.include_tx_power = True

class ZionService(Service):
    SVC_UUID = "00000001-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, index):
        super(ZionService, self).__init__(index, self.SVC_UUID, True)

        self._report_result = None

        self.add_characteristic(ParameterCharacteristic(self))
        self.add_characteristic(ProtocolCharacteristic(self))
        self.ParameterFile = 'default_parameter_file.txt'
        self.ProtocolFile = 'default_protocol_file.txt'

        self.add_characteristic(ReportStatusCharacteristic(self))
        self.ReportStatus = STATUS_INIT

        self.add_characteristic(ReportCharacteristic(self))
        self.add_characteristic(ReportFileCharacteristic(self))
        self.ReportFilename = 'default_report_filename.txt'
        

    def get_parameter_file(self):
        return self.ParameterFile

    def get_protocol_file(self):
        return self.ProtocolFile

    def get_report_filename(self):
        return self.ReportFilename

    def set_parameter_file(self, filename):
        self.ParameterFile = filename

    def set_protocol_file(self, filename):
        self.ProtocolFile = filename

    def get_report_filename(self, filename):
        self.ReportFilename = filename

    def update_status(self):
        if self._report_result is not None:
            status = self._report_result.status
            if status=='PENDING':
                self.ReportStatus = STATUS_INIT
            elif status=='STARTED':
                self.ReportStatus = STATUS_BUSY
            elif status=='SUCCESS':
                self.ReportStatus = STATUS_READY
            elif status=='FAILURE':
                self.ReportStatus = STATUS_ERROR
            else:
                self.ReportStatus = STATUS_UNKNOWN
        else:
            status = 'UNDEFINED'
        return status

    def generate_report(self):
        args = (self.ParameterFile,
                 self.ProtocolFile, 
                 self.ReportFilename)
        self._report_result = zion_report.apply_async(args, time_limit = 60)


class ReportStatusCharacteristic(Characteristic):
    UUID = "00000003-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, service):
        self.notifying = False

        super(ReportStatusCharacteristic, self).__init__(
                self.UUID,
                ["notify", "read"], service)
        self.add_descriptor(ReportStatusDescriptor(self))

    def get_status(self):
        value = []
        status = self.service.update_status()
        for c in status:
            value.append(dbus.Byte(c.encode()))
        return value

    def set_status_callback(self):
        if self.notifying:
            old_state = self.service.get_report_status()
            status = self.get_status()
            if not self.serivce.get_report_status() == old_state:
                self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": status}, [])
        return self.notifying

    def StartNotify(self):
        if self.notifying:
            return
        self.notifying = True
        old_state = self.service.get_report_status()
            status = self.get_status()
            if not self.serivce.get_report_status() == old_state:
                self.PropertiesChanged(GATT_CHRC_IFACE, {"Value": status}, [])
        self.add_timeout(NOTIFY_TIMEOUT, self.set_status_callback)

    def StopNotify(self):
        self.notifying = False

    def ReadValue(self, options):
        status = self.get_status()

        return status

class ReportStatusDescriptor(Descriptor):
    UUID = "2901"
    DESCRIPTOR_VALUE = "Report Status"

    def __init__(self, characteristic):
        super(ReportStatusDescriptor, self).__init__(
                self.UUID,
                ["read"],
                characteristic)

    def ReadValue(self, options):
        value = []
        desc = self.DESCRIPTOR_VALUE

        for c in desc:
            value.append(dbus.Byte(c.encode()))
        return value

class ReportCharacteristic(Characteristic):
    UUID = "00000002-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, service):
        self.notifying = False

        super(ReportCharacteristic, self).__init__(
                self.UUID,
                ["read"], service)
        self.add_descriptor(ReportDescriptor(self))

    def get_report(self):
        value = []
        try:
            with open(self.ReportFilename, 'r') as reportFile:
                strtemp = reportFile.read()
        except FileError:
            strtemp=''
        for c in strtemp:
            value.append(dbus.Byte(c.encode()))
        return value

    def ReadValue(self, options):
        value = self.get_report()
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
    UUID = "00000004-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, service):
        super(ParameterCharacteristic, self).__init__(
                self.UUID,
                ["read", "write"], service)
        self.add_descriptor(ParameterDescriptor(self))

    def WriteValue(self, value, options):
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
    UUID = "00000005-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, service):
        super(ProtocolCharacteristic, self).__init__(
                self.UUID,
                ["read", "write"], service)
        self.add_descriptor(ProtocolDescriptor(self))

    def WriteValue(self, value, options):
         val = value
         self.service.set_protocol_file(val)
         
         #now trigger generating a new report:
         self.service.generate_report()

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

class ReportFileCharacteristic(Characteristic):
    UUID = "00000006-710e-4a5b-8d75-3e5b444bc3cf"

    def __init__(self, service):
        super(ReportFileCharacteristic, self).__init__(
                self.UUID,
                ["read", "write"], service)
        self.add_descriptor(ReportFileDescriptor(self))

    def WriteValue(self, value, options):
         val = value
         self.service.set_report_filename(val)

    def ReadValue(self, options):
        value = []
        val = self.service.get_report_filename()
        for c in val:
            value.append(dbus.Byte(c.encode()))
        return value

class ReportFileDescriptor(Descriptor):
    UUID = "2902"
    DESCRIPTOR_VALUE = "Report Filename"

    def __init__(self, characteristic):
        super(ReportFileDescriptor, self).__init__(
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
app.add_service(ZionService(0))
app.register()

adv = ZionAdvertisement(0)
adv.register()

try:
    app.run()
except KeyboardInterrupt:
    app.quit()
