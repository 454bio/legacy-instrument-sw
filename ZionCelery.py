import time
from celery import Celery

zion_celery = Celery('ZionCelery', broker='pyamqp://', backend='redis://localhost:6379/0')

#celery -A ZionCelery worker --loglevel=info

@zion_celery.task(name='zion-report-spoofed', bind=True, track_started=True)
def spoof_zion_report(self, parameter_file, protocol_file, report_filename, timeout=20):
    ret = 0
    time.sleep(timeout)
    with open(report_filename, 'w') as file:
        file.writelines(['This is a Zion Report!\n',
                         'Parameters from: '+parameter_file+'\n',
                         'Protocol from: '+protocol_file])
    ret = 1
    return ret

@zion_celery.task(name='zion-report', bind=True, track_started=True)
def zion_report(self, parameter_file, protocol_file, report_filename, timeout=20):
    ret = 0
    time.sleep(timeout)
    with open(report_filename, 'w') as file:
        file.writelines(['This is a Zion Report!\n',
                         'Parameters from: '+parameter_file+'\n',
                         'Protocol from: '+protocol_file])
    ret = 1
    return ret

@zion_celery.task(bind=True, track_started=True)
def test_celery(self,x,y):
    return x+y
    
if __name__=='__main__':
    zion_celery.start()
