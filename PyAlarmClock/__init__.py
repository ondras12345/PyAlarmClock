"""A Python library for interfacing with AlarmClock over a serial port."""

from enum import Enum
import serial  # type: ignore
import logging
import re
import yaml
import datetime
from typing import List
from dataclasses import dataclass

from .days_of_week import DaysOfWeek


_LOGGER = logging.getLogger(__name__)


class CommandErrorCode(Enum):
    """An enumeration of all errors that can be returned by AlarmClock CLI."""

    Ok = 0
    ArgumentError = 1
    NothingSelected = 2
    UselessSave = 4
    NotFound = 8
    Unsupported = 16


EEPROM_SIZE = 1024
EEPROM_MELODIES_HEADER_START = 0x0010
EEPROM_MELODIES_COUNT = 16
EEPROM_MELODIES_DATA_START = 0x0100
EEPROM_ALARMS_START = 0x0040


class AlarmEnabled(Enum):
    """An enumeration of all possible states of Alarm.enabled."""

    OFF = 0
    SGL = 1
    RPT = 2
    SKP = 3


@dataclass
class Signalization:
    """Representation of signalization settings of an alarm."""

    ambient: int
    lamp: bool
    buzzer: int  # TODO enum for melodies

    @classmethod
    def from_dict(cls, d):
        """Create an instance from a dict.

        The dict needs to contain the following
        keys: 'ambient', 'lamp', 'buzzer'.
        """
        return cls(ambient=d['ambient'],
                   lamp=bool(d['lamp']),
                   buzzer=d['buzzer'])


@dataclass
class TimeOfDay:
    """Representation of a time of day with minutes precision."""

    hours: int
    minutes: int


@dataclass
class Snooze:
    """Representation of snooze settings of an alarm."""

    time: int  # in minutes, max 99
    count: int  # max 9


@dataclass
class Alarm:
    """Representation of a single alarm."""

    enabled: AlarmEnabled
    days_of_week: DaysOfWeek
    time: TimeOfDay
    snooze: Snooze
    signalization: Signalization

    @classmethod
    def from_dict(cls, d):
        """Create an instance from a dict.

        The dict needs to contain the following
        keys: 'enabled', 'dow', 'time', 'snz', 'sig'.
        """
        return cls(
            enabled=AlarmEnabled[d['enabled']],
            days_of_week=DaysOfWeek(d['dow']),
            time=TimeOfDay(hours=int(d['time'].split(':')[0]),
                           minutes=int(d['time'].split(':')[1])),
            snooze=Snooze(d['snz']['time'], d['snz']['count']),
            signalization=Signalization.from_dict(d['sig'])
            )

    def __str__(self):
        mins = self.time.minutes
        mins = str(mins) if mins > 10 else '0' + str(mins)
        return (f'enabled: {self.enabled.name}\n'
                f'days of week: {self.days_of_week}\n'
                f'time: {self.time.hours}:{mins}\n'
                f'snooze:\n'
                f'\ttime: {self.snooze.time}\n'
                f'\tcount: {self.snooze.count}\n'
                f'signalization:\n'
                f'\tambient: {self.signalization.ambient}\n'
                f'\tlamp: {self.signalization.lamp}\n'
                f'\tbuzzer: {self.signalization.buzzer}')


class CommandError(Exception):
    """Error returned from AlarmClock during command execution."""

    def __init__(self, code, message='AlarmClock returned error'):
        self.code = code
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'{self.message}: {self.code}'


class AlarmClock:
    """Base class for representations of an AlarmClock communications adapter.

    Specifying how to communicate with the AlarmClock is left to derived
    classes that need to implement run_command.
    """

    def __init__(self):
        a = self.run_command('ver')['ver']
        self.number_of_alarms = a['number of alarms']
        self.build_time = a['build time']

    def run_command(self, command: str):
        """Send a command, parse it's YAML output and return the result."""
        raise NotImplementedError()

    def read_alarm(self, index: int) -> Alarm:
        """Read a single alarm."""
        if index < 0 or index >= self.number_of_alarms:
            raise ValueError(f'{index} is not a valid alarm index '
                             f'(0...{self.number_of_alarms})')
        self.run_command(f'sel{index}')
        return Alarm.from_dict(self.run_command('ls')[f'alarm{index}'])

    def read_alarms(self) -> List[Alarm]:
        """Read all alarms.

        This uses the la command and is much faster than calling `read_alarm`
        in a loop.
        """
        output = self.run_command('la')
        alarms = [Alarm.from_dict(output[key]) for key in output]
        return alarms

    def write_alarm(self, index: int, value: Alarm) -> None:
        """Write an alarm."""
        if index < 0 or index >= self.number_of_alarms:
            raise ValueError(f'{index} is not a valid alarm index '
                             f'(0...{self.number_of_alarms})')
        current = self.read_alarm(index)
        # read_alarm has already selected the correct alarm
        if current.enabled != value.enabled:
            self.run_command(f'en-{value.enabled.name.lower()}')
        for day in list(range(1, 8)):
            bit = 2**day
            # TODO DaysOfWeek diff
            new_bit_value = int(bool(value.days_of_week.code & bit))
            if int(bool(current.days_of_week.code & bit)) != new_bit_value:
                self.run_command(f'dow{day}:{new_bit_value}')
        if current.time != value.time:
            self.run_command(f'time{value.time.hours}:{value.time.minutes}')
        if current.snooze != value.snooze:
            self.run_command(f'snz{value.snooze.time};{value.snooze.count}')
        if current.signalization != value.signalization:
            ambient = value.signalization.ambient
            lamp = int(value.signalization.lamp)
            buzzer = int(value.signalization.buzzer)
            self.run_command(f'sig{ambient};{lamp};{buzzer}')

    def save_EEPROM(self) -> None:
        """Save all changes to the EEPROM.

        This can raise 'UselessSave' error.
        """
        self.run_command('sav')

    @property
    def lamp(self) -> bool:
        return bool(self.run_command('lamp')['lamp'])

    @lamp.setter
    def lamp(self, value: bool) -> None:
        self.run_command(f'lamp{int(bool(value))}')

    @property
    def ambient(self):
        return self.run_command('amb')['ambient']['target']
        # TODO add getter for current value

    @ambient.setter
    def ambient(self, value: int):
        if value < 0 or value > 255:
            raise ValueError(f'{repr(value)} is not in range 0...255')
        self.run_command(f'amb{value}')

    @property
    def inhibit(self) -> bool:
        return bool(self.run_command('inh')['inhibit'])

    @inhibit.setter
    def inhibit(self, value: bool) -> None:
        self.run_command(f'inh{int(bool(value))}')

    @property
    def RTC_time(self) -> datetime.datetime:
        return self.run_command('rtc')['rtc']['time']

    @RTC_time.setter
    def RTC_time(self, value: datetime.datetime) -> None:
        """Set RTC time.

        Be careful when setting RTC time around midnight, the operation is NOT
        atomic. Time is set first, then date.
        """
        # set time first to avoid delay
        self.run_command(value.strftime('st%H:%M:%S'))
        self.run_command(value.strftime('sd%Y-%m-%d'))

    @property
    def countdown_timer(self):
        class CountdownTimer:
            def __get_info(otherself):
                out = self.run_command('tmr')['timer']
                otherself.__running = out['running']
                time = out['time left'].split(':')
                otherself.__time = datetime.timedelta(hours=int(time[0]),
                                                      minutes=int(time[1]),
                                                      seconds=int(time[2]))
                otherself.__events = Signalization.from_dict(out)

            def get_all(otherself):
                """Get all info about the timer with a single command.

                This is much faster than querying the individual properties
                one by one.
                """
                @dataclass
                class TimerInfo:
                    time: datetime.timedelta
                    running: bool
                    events: Signalization

                otherself.__get_info()
                return TimerInfo(time=otherself.__time,
                                 running=otherself.__running,
                                 events=otherself.__events)

            @property
            def time(otherself) -> datetime.timedelta:
                otherself.__get_info()
                return otherself.__time

            @time.setter
            def time(otherself, value: datetime.timedelta) -> None:
                hours = value.seconds // 3600
                minutes = (value.seconds // 60) % 60
                seconds = value.seconds % 60
                self.run_command(f'tmr{hours}:{minutes}:{seconds}')

            @property
            def running(otherself) -> bool:
                otherself.__get_info()
                return otherself.__running

            @running.setter
            def running(otherself, value: bool) -> None:
                self.run_command(f'tmr-{"start" if value else "stop"}')

            @property
            def events(otherself) -> Signalization:
                otherself.__get_info()
                return otherself.__events

            @events.setter
            def events(otherself, value: Signalization) -> None:
                ambient = value.ambient
                lamp = int(value.lamp)
                buzzer = int(value.buzzer)
                self.run_command(f'tme{ambient};{lamp};{buzzer}')

            def start(otherself):
                otherself.running = True

            def stop(otherself):
                otherself.running = False

        return CountdownTimer()

    class EEPROMArray:
        # I cannot specify ac: AlarmClock because AlarmClock is not defined.
        def __init__(self, ac):
            self.ac = ac

        def __getitem__(self, key: int) -> int:
            if key < 0 or key >= EEPROM_SIZE:
                raise KeyError(key)
            return self.ac.run_command(f'eer{key}')['EEPROM'][key]

        def __setitem__(self, key: int, value: int):
            if key < 0 or key >= EEPROM_SIZE:
                raise KeyError(key)
            if value < 0 or value > 255:
                raise ValueError(f"{value} is not an unsigned 8bit integer")
            self.ac.run_command(f'eew{key};{value}')

    @property
    def EEPROM(self):
        """Direct read/write access to the EEPROM."""
        return self.EEPROMArray(self)


class SerialAlarmClock(AlarmClock):
    """Representation of an AlarmClock connected via a serial port."""

    class Serial:
        """An object that handles serial port communication with AlarmClock."""

        class PromptTimeout(Exception):
            """Timeout when waiting for a prompt."""

        ERROR_REGEX = "^err (0x[0-9]{,2}): .*\r?$"
        PROMPT_REGEX = "^(A?[0-9]{,3})> "
        YAML_BEGIN_REGEX = "^---\r?$"
        YAML_END_REGEX = "^[.]{3}\r?$"

        def __init__(self, port, baudrate):
            """Initialize the serial port connection.

            This can take a few seconds because it needs to wait until
            a prompt is received.
            """
            _LOGGER.info('Initializing serial port')
            self.ser = serial.Serial()
            self.ser.port = port
            self.ser.baudrate = baudrate
            # If you change this timeout, please check if `wait_for_prompt`
            # still works properly.
            self.ser.timeout = 1
            # This does not prevent a reset because the dtr line still falls
            # to 0 V for 1 to 2 ms, which seems to be enough to reset the MCU.
            # self.ser.dtr = False
            self.ser.open()
            self.prompt = ''
            self.bel_received = False
            try:
                self.wait_for_prompt()
            except self.PromptTimeout:
                # This should happen if opening the serial port does not cause
                # a reset of the Arduino. To prevent it from resetting, try
                # something like this:
                # stty -F /dev/ttyUSB0 -hup
                self.process_command('sync')

        def wait_for_prompt(self, timeout_count_max=4):
            """Wait unit a prompt is received on the serial port.

            This function should only be called after a command is sent.
            Otherwise, the whole thing would get stuck waiting for a prompt
            that will never come. `PromptTimeout` is raised after
            `timeout_count_max` timeouts of `ser.read()`.
            """
            _LOGGER.debug('Waiting for prompt...')
            line = ''
            match = None
            timeout_count = 0
            while not match:
                if timeout_count >= timeout_count_max:
                    raise self.PromptTimeout()
                char = self.ser.read(1).decode('ASCII')
                if char == '\a':
                    self.bel_received = True
                if char == '':
                    _LOGGER.debug('timeout')
                    timeout_count += 1
                    continue
                _LOGGER.debug(f'got: {repr(char)}')
                if char in ['\r', '\n']:
                    # We don't care about ending the line, PROMPT_REGEX does
                    # not require that.
                    line = ''
                else:
                    line += char
                    match = re.match(self.PROMPT_REGEX, line)

            self.prompt = match.group(1)
            _LOGGER.debug('Prompt received')

        def send(self, command):
            """Send a string to the serial port."""
            a = command.encode('ASCII')
            _LOGGER.debug(f'Sending: {a}')
            self.ser.write(a)

        def process_command(self, command):
            """Send a command and get it's output."""
            self.send(command + '\n')
            line = ''
            yaml_output = ''
            error_line = None
            in_yaml = False
            while not error_line:
                line = self.ser.readline().decode('ASCII')
                _LOGGER.debug(f'got: {repr(line)}')
                if '\a' in line:
                    self.bel_received = True
                if re.match(self.YAML_BEGIN_REGEX, line):
                    in_yaml = True
                    _LOGGER.debug('Entered YAML command output')

                if in_yaml:
                    yaml_output += line

                if re.match(self.YAML_END_REGEX, line):
                    in_yaml = False
                    _LOGGER.debug('Exited YAML command output')

                error_line = re.match(self.ERROR_REGEX, line)

            error = CommandErrorCode(int(error_line.group(1), 0))
            self.wait_for_prompt()

            return error, yaml_output

        def check_bel_received(self) -> bool:
            """Return value of bel_received and clear it.

            This also checks characters in the buffer.
            """
            old_timeout = self.ser.timeout
            self.ser.timeout = 0
            while character := self.ser.read(1).decode('ASCII'):
                _LOGGER.debug(f'check_bel_received got: {repr(character)}')
                if character == '\a':
                    self.bel_received = True
            self.ser.timeout = old_timeout

            value = self.bel_received
            self.bel_received = False

            return value

    def __init__(self, port, baudrate=9600):
        """Initialize the object and establish serial communication."""
        self.__serial = self.Serial(port, baudrate)
        super().__init__()

    def run_command(self, command: str):
        """Send a command, parse it's YAML output and return the result."""
        error, yaml_output = self.__serial.process_command(command)
        if error != CommandErrorCode.Ok:
            raise CommandError(error)
        if yaml_output == '':
            return None
        _LOGGER.debug(f'Parsing YAML:\n{yaml_output}')
        output = yaml.safe_load(yaml_output)
        return output

    def read_alarm(self, index: int) -> Alarm:
        alarm = super().read_alarm(index)
        if self.__serial.prompt != f'A{index}':
            raise AssertionError(
                f"AlarmClock prompt is incorrect: {self.__serial.prompt}")
        return alarm

    def state_changed(self) -> bool:
        """Return true if BEL character was received from AlarmClock.

        This is NOT a blocking call.

        AlarmClock needs to have feature/CLI-BEL merged in order to send
        BEL (0x07) on state changes.
        """
        return self.__serial.check_bel_received()

    def __enter__(self):
        """For use with `with`."""
        return self

    def __exit__(self, type, value, traceback):
        """For use with `with`."""
        self.close()
        return False

    def is_open(self):
        """Return True if the serial port is open."""
        return self.__serial.ser.isOpen()

    def close(self):
        """Close the serial port."""
        _LOGGER.debug('Closing serial port')
        self.__serial.ser.close()

    # def open(self):
    #     """Open the serial port"""
    #     self.__serial.ser.open()


# Warning: If you try to implement something like MQTTAlarmClock, keep in mind
# that there might be hidden race conditions - e.g. you need to `sel` the
# correct alarm before you `ls`.
