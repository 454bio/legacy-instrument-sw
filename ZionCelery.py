import time
from celery import Celery

zion_celery = Celery('ZionCelery', backend='redis://localhost', broker='pyamqp://')

#celery -A ZionCelery worker --loglevel=info

@zion_celery.task(name='zion-report-spoofed', bind=True, track_started=True)
#def zion_report(params, protocol, report_filename, timeout=20):
#    time.sleep(timeout)
def spoof_zion_report(self, params, protocol, report_filename):
    ret = 0
    time.sleep(20)
    with open(report_filename, 'w') as file:
        file.writelines(['This is a Zion Report!,
                         'Parameters from: '+parameter_file,
                         'Protocol from: '+protocol_file])
    ret = 1
    return ret

@zion_celery.task(name='zion-report', bind=True, track_started=True)
#def zion_report(params, protocol, report_filename, timeout=20):
#    time.sleep(timeout)
def zion_report(self, params, protocol, report_filename):
    ret = 0
    time.sleep(20)
    with open(report_filename, 'w') as file:
        file.writelines(['This is a Zion Report!,
                         'Parameters from: '+parameter_file,
                         'Protocol from: '+protocol_file])
    ret = 1
    return ret