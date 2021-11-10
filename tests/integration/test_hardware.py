#!/usr/bin/env python3

"""Tests that need real hardware to be attached."""

import unittest
import time

import datetime
import PyAlarmClock
from PyAlarmClock import (CommandError, CommandErrorCode, Alarm, AlarmEnabled,
                          TimeOfDay, Snooze, Signalization, DaysOfWeek)


class TestConfiguration(unittest.TestCase):
    """Test configuration over CLI with real hardware.

    This will write to EEPROM and overwrite current configuration.
    """

    @classmethod
    def setUpClass(self):
        self.ac = PyAlarmClock.AlarmClock('/dev/ttyUSB0')

    @classmethod
    def tearDownClass(self):
        self.ac.RTC_time = datetime.datetime.now()
        self.ac.close()

    def test_select_deselect(self):
        self.ac.run_command('sel')
        self.assertEqual(self.ac._AlarmClock__serial.prompt, '')
        self.ac.run_command('sel0')
        self.assertEqual(self.ac._AlarmClock__serial.prompt, 'A0')

    def test_inhibit(self):
        self.ac.inhibit = True
        self.assertEqual(self.ac.inhibit, True)
        self.ac.inhibit = False
        self.assertEqual(self.ac.inhibit, False)

    def test_lamp(self):
        self.ac.lamp = True
        self.assertEqual(self.ac.lamp, True)
        self.ac.lamp = False
        self.assertEqual(self.ac.lamp, False)

    def test_rtc(self):
        test_time = datetime.datetime(2021, 1, 1, 0, 0, 0)
        self.ac.RTC_time = test_time
        time.sleep(2)
        self.assertGreater(self.ac.RTC_time - test_time,
                           datetime.timedelta(0, 0))
        self.assertLess(self.ac.RTC_time - test_time,
                        datetime.timedelta(0, 4))

    def test_alarm_config(self):
        alarm_old = self.ac.read_alarm(0)

        alarm = Alarm(enabled=AlarmEnabled.OFF,
                      days_of_week=DaysOfWeek(0x00),
                      time=TimeOfDay(12, 34),
                      snooze=Snooze(2, 3),
                      signalization=Signalization(120, True, False)
                      )
        self.ac.write_alarm(0, alarm)
        self.assertEqual(self.ac.read_alarm(0), alarm)

        alarm.enabled = AlarmEnabled.SGL
        self.ac.write_alarm(0, alarm)
        self.assertEqual(self.ac.read_alarm(0), alarm)
        alarm.enabled = AlarmEnabled.RPT
        self.ac.write_alarm(0, alarm)
        self.assertEqual(self.ac.read_alarm(0), alarm)
        alarm.enabled = AlarmEnabled.SKP
        self.ac.write_alarm(0, alarm)
        self.assertEqual(self.ac.read_alarm(0), alarm)

        self.ac.write_alarm(0, alarm_old)

    def test_alarm_trigger(self):
        alarm_old = self.ac.read_alarm(0)

        self.ac.ambient = 0
        self.ac.lamp = False

        self.ac.RTC_time = datetime.datetime(2021, 1, 1, 12, 33, 50)

        alarm = Alarm(enabled=AlarmEnabled.SGL,
                      days_of_week=DaysOfWeek(),
                      time=TimeOfDay(12, 34),
                      snooze=Snooze(1, 1),
                      signalization=Signalization(120, True, True)
                      )
        alarm.days_of_week.Friday = True
        self.ac.write_alarm(0, alarm)
        self.assertEqual(self.ac.read_alarm(0), alarm)

        self.ac.RTC_time = datetime.datetime(2021, 1, 1, 12, 33, 58)

        time.sleep(5)

        # TODO this will not work, ambient start dimming be enabled 15 minutes
        # before the alarm triggers.
        #self.assertEqual(self.ac.ambient, 120)

        self.assertEqual(self.ac.lamp, True)

        # user will need to stop the alarm manually
        input("Press snooze")
        self.assertEqual(self.ac.lamp, False)
        input("Wait until it retriggers; press snooze (should NOT work)")
        self.assertEqual(self.ac.lamp, True)
        input("Press stop")

        self.assertEqual(self.ac.ambient, 0)
        self.assertEqual(self.ac.lamp, False)
        # See if SGL works
        self.assertEqual(self.ac.read_alarm(0).enabled, AlarmEnabled.OFF)

        self.ac.write_alarm(0, alarm_old)

    def test_sav_useless(self):
        # we don't know what state we are in, so we'll execute sav twice
        try:
            self.ac.save_EEPROM()
        except CommandError as e:
            if e.code != CommandErrorCode.UselessSave:
                raise e

        with self.assertRaises(CommandError) as cm:
            self.ac.save_EEPROM()
        self.assertEqual(cm.exception.code, CommandErrorCode.UselessSave)


if __name__ == '__main__':
    # This is not useful because the PyAlarmClock module will not be
    # found if executed directly.
    unittest.main()
