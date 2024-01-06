#!/usr/bin/env python3

import unittest
from datetime import datetime

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

    def test_next_alarm_time_OFF(self):
        d = {
            'enabled': 'OFF',
            'dow': 0xFE,
            'time': '13:01',
            'snz': {'time': 1, 'count': 3},
            'sig': {'ambient': 240, 'lamp': 1, 'buzzer': 1},
        }
        a = Alarm.from_dict(d)
        dt = datetime.fromisoformat('2024-01-06T15:30:00')
        self.assertIsNone(a.get_next_alarm_time(dt))

    def test_next_alarm_time_SKP(self):
        d = {
            'enabled': 'SKP',
            'dow': 0xFE,
            'time': '13:01',
            'snz': {'time': 1, 'count': 3},
            'sig': {'ambient': 240, 'lamp': 1, 'buzzer': 1},
        }
        a = Alarm.from_dict(d)
        dt = datetime.fromisoformat('2024-01-06T15:30:00')
        self.assertIsNone(a.get_next_alarm_time(dt))

    def test_next_alarm_time_all_dow_disabled(self):
        d = {
            'enabled': 'RPT',
            'dow': 0x00,
            'time': '13:01',
            'snz': {'time': 1, 'count': 3},
            'sig': {'ambient': 240, 'lamp': 1, 'buzzer': 1},
        }
        a = Alarm.from_dict(d)
        dt = datetime.fromisoformat('2024-01-06T15:30:00')
        self.assertIsNone(a.get_next_alarm_time(dt))

    def test_next_alarm_time_today(self):
        d = {
            'enabled': 'RPT',
            'dow': 1 << 6,
            'time': '13:01',
            'snz': {'time': 1, 'count': 3},
            'sig': {'ambient': 240, 'lamp': 1, 'buzzer': 1},
        }
        a = Alarm.from_dict(d)
        dt = datetime.fromisoformat('2024-01-06T10:30:00')
        self.assertEqual(
            a.get_next_alarm_time(dt),
            datetime.fromisoformat('2024-01-06T13:01:00')
        )

        dt = datetime.fromisoformat('2024-01-06T13:00:59')
        self.assertEqual(
            a.get_next_alarm_time(dt),
            datetime.fromisoformat('2024-01-06T13:01:00')
        )

        dt = datetime.fromisoformat('2024-01-06T13:01:00')
        self.assertEqual(
            a.get_next_alarm_time(dt),
            datetime.fromisoformat('2024-01-13T13:01:00')
        )

    def test_next_alarm_time_next_week(self):
        d = {
            'enabled': 'RPT',
            'dow': 1 << 6,
            'time': '13:01',
            'snz': {'time': 1, 'count': 3},
            'sig': {'ambient': 240, 'lamp': 1, 'buzzer': 1},
        }
        a = Alarm.from_dict(d)
        dt = datetime.fromisoformat('2024-01-06T15:30:00')
        self.assertEqual(
            a.get_next_alarm_time(dt),
            datetime.fromisoformat('2024-01-13T13:01:00')
        )

    def test_next_alarm_tomorrow(self):
        d = {
            'enabled': 'RPT',
            'dow': 0xFE,
            'time': '13:01',
            'snz': {'time': 1, 'count': 3},
            'sig': {'ambient': 240, 'lamp': 1, 'buzzer': 1},
        }
        a = Alarm.from_dict(d)
        dt = datetime.fromisoformat('2024-01-06T15:30:00')
        self.assertEqual(
            a.get_next_alarm_time(dt),
            datetime.fromisoformat('2024-01-07T13:01:00')
        )

    def test_next_alarm_SGL(self):
        d = {
            'enabled': 'SGL',
            'dow': 0xFE,
            'time': '13:01',
            'snz': {'time': 1, 'count': 3},
            'sig': {'ambient': 240, 'lamp': 1, 'buzzer': 1},
        }
        a = Alarm.from_dict(d)
        dt = datetime.fromisoformat('2024-01-06T15:30:00')
        self.assertEqual(
            a.get_next_alarm_time(dt),
            datetime.fromisoformat('2024-01-07T13:01:00')
        )


if __name__ == '__main__':
    unittest.main()
