from enum import Enum
import serial  # type: ignore
import logging
import re
import yaml
import datetime
from typing import List
from dataclasses import dataclass


_LOGGER = logging.getLogger(__name__)


class CommandErrorCode(Enum):
    Ok = 0
    ArgumentError = 1
    NothingSelected = 2
    UselessSave = 4
    NotFound = 8


class DaysOfWeek:
    days = {
        'Monday': 1,
        'Tuesday': 2,
        'Wednesday': 3,
        'Thursday': 4,
        'Friday': 5,
        'Saturday': 6,
        'Sunday': 7,
        }

    def __init__(self, code=0):
        # Filter out bit 0. It has no meaning and should always be zero.
        self.code = code & 0xFE

    def get_day(self, day):
        if isinstance(day, str):
            if day not in self.days:
                raise TypeError(f'unknown day: {repr(day)}')
            day = self.days[day]
        return self.code & (2**day) > 0

    def set_day(self, day, value):
        if isinstance(day, str):
            if day not in self.days:
                raise TypeError(f'unknown day: {repr(day)}')
            day = self.days[day]
        if value:
            self.code |= (2**day)
        else:
            self.code &= ~(2**day)

    Monday = property(lambda self: self.get_day('Monday'),
                      lambda self, value: self.set_day('Monday', value))

    Tuesday = property(lambda self: self.get_day('Tuesday'),
                       lambda self, value: self.set_day('Tuesday', value))

    Wednesday = property(lambda self: self.get_day('Wednesday'),
                         lambda self, value: self.set_day('Wednesday', value))

    Thursday = property(lambda self: self.get_day('Thursday'),
                        lambda self, value: self.set_day('Thursday', value))

    Friday = property(lambda self: self.get_day('Friday'),
                      lambda self, value: self.set_day('Friday', value))

    Saturday = property(lambda self: self.get_day('Saturday'),
                        lambda self, value: self.set_day('Saturday', value))

    Sunday = property(lambda self: self.get_day('Sunday'),
                      lambda self, value: self.set_day('Sunday', value))

    @property
    def active_days(self):
        return [day for day in self.days if self.get_day(day)]

    def __str__(self):
        return ', '.join(self.active_days)

    def __repr__(self):
        return f'{self.__class__.__name__}({repr(self.code)})'

    def __eq__(self, other):
        return self.code == other.code


class AlarmEnabled(Enum):
    OFF = 0
    SGL = 1
    RPT = 2
    SKP = 3


@dataclass
class Signalization:
    ambient: int
    lamp: bool
    buzzer: bool

    @classmethod
    def from_dict(cls, d):
        return cls(ambient=d['ambient'],
                   lamp=bool(d['lamp']),
                   buzzer=bool(d['buzzer']))


@dataclass
class TimeOfDay:
    hours: int
    minutes: int


@dataclass
class Snooze:
    time: int  # in minutes, max 99
    count: int  # max 9


@dataclass
class Alarm:
    enabled: AlarmEnabled
    days_of_week: DaysOfWeek
    time: TimeOfDay
    snooze: Snooze
    signalization: Signalization

    @classmethod
    def from_dict(cls, d):
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
    def __init__(self, code, message='Alarm clock returned error'):
        self.code = code
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'{self.message}: {self.code}'


class AlarmClock:
    class Serial:
        class PromptTimeout(Exception):
            pass

        ERROR_REGEX = "^err (0x[0-9]{,2}): .*\r?$"
        PROMPT_REGEX = "^(A?[0-9]{,3})> "
        YAML_BEGIN_REGEX = "^---\r?$"
        YAML_END_REGEX = "^[.]{3}\r?$"

        def __init__(self, port, baudrate):
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
            try:
                self.wait_for_prompt()
            except self.PromptTimeout:
                # This should happen if opening the serial port does not cause
                # a reset of the Arduino. To prevent it from resetting, try
                # something like this:
                # stty -F /dev/ttyUSB0 -hup
                self.process_command('sync')

        def wait_for_prompt(self, timeout_count_max=4):
            """This function should only be called after a command is sent.
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
                if char == '':
                    _LOGGER.debug('timeout')
                    timeout_count += 1
                    continue
                _LOGGER.debug(f'got: {char}')
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
            """Send a string to the serial port"""
            a = command.encode('ASCII')
            _LOGGER.debug(f'Sending: {a}')
            self.ser.write(a)

        def process_command(self, command):
            """Send a command and get it's output"""
            self.send(command + '\n')
            line = ''
            yaml_output = ''
            error_line = None
            in_yaml = False
            while not error_line:
                line = self.ser.readline().decode('ASCII')
                _LOGGER.debug(f'got: {repr(line)}')
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

    def __init__(self, port, baudrate=9600):
        self.__serial = self.Serial(port, baudrate)
        a = self.run_command('ver')['ver']
        self.number_of_alarms = a['number of alarms']
        self.build_time = a['build time']

    def run_command(self, command: str):
        """Send a command to the alarm clock, parse it's YAML output and
        return the result
        """
        error, yaml_output = self.__serial.process_command(command)
        if error != CommandErrorCode.Ok:
            raise CommandError(error)
        if yaml_output == '':
            return None
        _LOGGER.debug(f'Parsing YAML:\n{yaml_output}')
        output = yaml.safe_load(yaml_output)
        return output

    def read_alarm(self, index: int) -> Alarm:
        if index < 0 or index >= self.number_of_alarms:
            raise ValueError(f'{index} is not a valid alarm index '
                             f'(0...{self.number_of_alarms})')
        self.run_command(f'sel{index}')
        return Alarm.from_dict(self.run_command('ls')[f'alarm{index}'])

    def read_alarms(self) -> List[Alarm]:
        """This uses the la command and is much faster than calling
        `read_alarm` in a loop"""
        output = self.run_command('la')
        alarms = [Alarm.from_dict(output[key]) for key in output]
        return alarms

    def write_alarm(self, index: int, value: Alarm) -> None:
        if index < 0 or index >= self.number_of_alarms:
            raise ValueError(f'{index} is not a valid alarm index '
                             f'(0...{self.number_of_alarms})')
        current = self.read_alarm(index)
        # read_alarm has already selected the correct alarm
        if current.enabled != value.enabled:
            self.run_command(f'en-{value.enabled.name.lower()}')
        for day in [x for x in range(1, 8)]:
            bit = 2**day
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
        """Don't forget that this can raise 'UselessSave' error"""
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
        atomic. Time is set first, then date."""
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
                """This gets all info about the timer with one command. It is
                much faster than querying the individual properties"""
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

    def __enter__(self):
        """For use with `with`"""
        return self

    def __exit__(self, type, value, traceback):
        """For use with `with`"""
        self.close()
        return False

    def is_open(self):
        """Report whether the serial port is open"""
        return self.__serial.ser.isOpen()

    def close(self):
        """Close the serial port"""
        _LOGGER.debug('Closing serial port')
        self.__serial.ser.close()

    # def open(self):
    #     """Open the serial port"""
    #     self.__serial.ser.open()
