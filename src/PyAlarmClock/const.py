"""Global constants for PyAlarmClock.

These will need to be updated if AlarmClock firmware changes.
"""

from enum import Enum

EEPROM_SIZE = 1024
EEPROM_MELODIES_HEADER_START = 0x0010
EEPROM_MELODIES_COUNT = 16
EEPROM_MELODIES_DATA_START = 0x0100
EEPROM_ALARMS_START = 0x0040


class CommandErrorCode(Enum):
    """All errors that can be returned by AlarmClock CLI."""
    Ok = 0
    ArgumentError = 1
    NothingSelected = 2
    UselessSave = 4
    NotFound = 8
    Unsupported = 16


class AlarmEnabled(Enum):
    """An enumeration of all possible states of Alarm.enabled."""
    OFF = 0
    SGL = 1
    RPT = 2
    SKP = 3


class DisplayBacklightStatus(Enum):
    """An enumeration of all possible display backlight levels."""
    OFF = 0
    DIM = 1
    BRIGHT = 2
    PERMANENT = 3
