#!/usr/bin/env python3

import unittest

from PyAlarmClock import Alarm, AlarmEnabled, DaysOfWeek
from PyAlarmClock import Snooze, TimeOfDay, Signalization


class TestAlarm(unittest.TestCase):
    def test_empty_dict(self):
        d = {}
        self.assertRaises(KeyError, Alarm.from_dict, d)

    def test_dict(self):
        d = {
                'enabled': 'OFF',
                'dow': 0xFE,
                'time': '13:01',
                'snz': {
                    'time': 1,
                    'count': 3,
                    },
                'sig': {
                    'ambient': 240,
                    'lamp': 1,
                    'buzzer': 1,
                    },
            }
        alarm = Alarm.from_dict(d)
        self.assertEqual(alarm.enabled, AlarmEnabled.OFF)
        self.assertEqual(alarm.days_of_week.code, 0xFE)
        self.assertEqual(alarm.time, TimeOfDay(hours=13, minutes=1))
        self.assertEqual(alarm.snooze, Snooze(time=1, count=3))
        self.assertEqual(alarm.signalization,
                         Signalization(ambient=240, lamp=True, buzzer=True))

    def test_equal(self):
        a = Alarm(enabled=AlarmEnabled.RPT, days_of_week=DaysOfWeek(0x08),
                  time=TimeOfDay(hours=12, minutes=20),
                  snooze=Snooze(time=1, count=3),
                  signalization=Signalization(ambient=240, lamp=True,
                                              buzzer=True))

        b = Alarm(enabled=AlarmEnabled.RPT, days_of_week=DaysOfWeek(0x08),
                  time=TimeOfDay(hours=12, minutes=20),
                  snooze=Snooze(time=1, count=3),
                  signalization=Signalization(ambient=240, lamp=True,
                                              buzzer=True))

        self.assertEqual(a, b)


if __name__ == '__main__':
    # This is not useful because the PyAlarmClock module will not be
    # found if executed directly.
    # Run `python3 -m unittest` in the root of the repository to run all tests.
    unittest.main()
