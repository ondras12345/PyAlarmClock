#!/usr/bin/env python3

import PyAlarmClock
from datetime import datetime
import time
import logging


logging.basicConfig(level=logging.DEBUG)

with PyAlarmClock.AlarmClock('/dev/ttyUSB0') as ac:
    ac.RTC_time = datetime.now()
    time.sleep(1.65)  # RTC is polled every 0.8 seconds
    print(ac.RTC_time)
