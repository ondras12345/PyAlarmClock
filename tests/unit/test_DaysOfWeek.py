#!/usr/bin/env python3

import unittest

from PyAlarmClock import DaysOfWeek


class TestDaysOfWeek(unittest.TestCase):
    DATA = [(0x00, (False,  False,  False,  False,  False,  False,  False)),
            (0x01, (False,  False,  False,  False,  False,  False,  False)),
            (0x02, (True,   False,  False,  False,  False,  False,  False)),
            (0x04, (False,  True,   False,  False,  False,  False,  False)),
            (0x08, (False,  False,  True,   False,  False,  False,  False)),
            (0x10, (False,  False,  False,  True,   False,  False,  False)),
            (0x20, (False,  False,  False,  False,  True,   False,  False)),
            (0x40, (False,  False,  False,  False,  False,  True,   False)),
            (0x80, (False,  False,  False,  False,  False,  False,  True)),
            (0x20, (False,  False,  False,  False,  True,   False,  False)),
            (0xC0, (False,  False,  False,  False,  False,  True,   True)),
            (0x1E, (True,   True,   True,   True,   False,  False,  False)),
            (0xFE, (True,   True,   True,   True,   True,   True,   True)),
            ]

    def test_decode(self):
        for case in self.DATA:
            code, correct = case
            dow = DaysOfWeek(code)
            self.assertEqual((dow.Monday, dow.Tuesday, dow.Wednesday,
                             dow.Thursday, dow.Friday, dow.Saturday,
                             dow.Sunday), correct)

    def test_encode(self):
        for case in self.DATA:
            code, correct = case
            dow = DaysOfWeek(0)
            (dow.Monday, dow.Tuesday, dow.Wednesday, dow.Thursday, dow.Friday,
             dow.Saturday, dow.Sunday) = correct
            if code == 0x01:
                self.assertEqual(dow.code, 0x00)
            else:
                self.assertEqual(dow.code, code)

    def test_repr(self):
        for i in range(0, 255):
            correct = i & 0xFE
            dow = DaysOfWeek(i)
            self.assertEqual(repr(dow), 'DaysOfWeek(' + repr(correct) + ')')

    def test_str(self):
        dow = DaysOfWeek()
        dow.Tuesday = True
        dow.Wednesday = True
        dow.Friday = True
        self.assertEqual(dow.active_days, ["Tuesday", "Wednesday", "Friday"])
        self.assertEqual(str(dow), "Tuesday, Wednesday, Friday")

    def test_get_str(self):
        dow = DaysOfWeek(0x04)
        self.assertFalse(dow.get_day('Monday'))
        self.assertTrue(dow.get_day('Tuesday'))
        self.assertRaises(TypeError, dow.get_day, 'test')

    def test_set_str(self):
        dow = DaysOfWeek()
        dow.set_day('Monday', True)
        self.assertTrue(dow.Monday)
        self.assertEqual(dow.code, 0x02)
        self.assertRaises(TypeError, dow.set_day, 'test', True)

    def test_from_list(self):
        dow = DaysOfWeek.from_list(["Tuesday", "Wednesday", "Friday"])
        self.assertEqual(dow.code, 0x2C)

        dow = DaysOfWeek.from_list([2, 3, 5])
        self.assertEqual(dow.code, 0x2C)

    def test_equal(self):
        self.assertEqual(DaysOfWeek(0x08), DaysOfWeek(0x08))


if __name__ == '__main__':
    unittest.main()
