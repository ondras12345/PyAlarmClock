import datetime
from typing import List
from dataclasses import dataclass
from ..dataclasses import Signalization, Alarm, AlarmClockStatus
from ..const import EEPROM_SIZE


class AlarmClock:
    """Base class for representations of an AlarmClock communications adapter.

    Specifying how to communicate with the AlarmClock is left to derived
    classes that need to implement run_command.
    """

    def __init__(self):
        a = self.run_command('ver')['ver']
        self.number_of_alarms = a['number of alarms']
        self.build_time = a['build time']
        self.alarmclock_version = a.get('version', None)

    def run_command(self, command: str):
        """Send a command, parse it's YAML output and return the result."""
        raise NotImplementedError()

    def read_alarm(self, index: int) -> Alarm:
        """Read a single alarm."""
        if index < 0 or index >= self.number_of_alarms:
            raise ValueError(f'{index} is not a valid alarm index '
                             f'(0...{self.number_of_alarms-1})')
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
        """Write an alarm.

        This does NOT make sure it is saved to the EEPROM. Use save_EEPROM for
        that.
        """
        if index < 0 or index >= self.number_of_alarms:
            raise ValueError(f'{index} is not a valid alarm index '
                             f'(0...{self.number_of_alarms-1})')
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

    def button_stop(self) -> None:
        """Stop all active alarms and the timer.

        This is the same as pressing the physical stop button,
        except it works even when the display backlight is off
        and does not turn display backlight on.
        """
        self.run_command('stop')

    @property
    def lamp(self) -> bool:
        return bool(self.run_command('lamp')['lamp'])

    @lamp.setter
    def lamp(self, value: bool) -> None:
        self.run_command(f'lamp{int(bool(value))}')

    @property
    def ambient(self) -> int:
        return self.run_command('amb')['ambient']['target']
        # TODO add getter for current value

    @ambient.setter
    def ambient(self, value: int) -> None:
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

    class CountdownTimer:
        @dataclass
        class TimerInfo:
            time: datetime.timedelta
            running: bool
            events: Signalization

        def __init__(self, ac):
            self.ac = ac

        def __get_info(self):
            out = self.ac.run_command('tmr')['timer']
            self.__running = out['running']
            time = out['time left'].split(':')
            self.__time = datetime.timedelta(hours=int(time[0]),
                                             minutes=int(time[1]),
                                             seconds=int(time[2]))
            self.__events = Signalization.from_dict(out)

        def get_all(self):
            """Get all info about the timer with a single command.

            This is much faster than querying the individual properties
            one by one.
            """

            self.__get_info()
            return self.TimerInfo(time=self.__time,
                                  running=self.__running,
                                  events=self.__events)

        @property
        def time(self) -> datetime.timedelta:
            self.__get_info()
            return self.__time

        @time.setter
        def time(self, value: datetime.timedelta) -> None:
            hours = value.seconds // 3600
            minutes = (value.seconds // 60) % 60
            seconds = value.seconds % 60
            self.ac.run_command(f'tmr{hours}:{minutes}:{seconds}')

        @property
        def running(self) -> bool:
            self.__get_info()
            return self.__running

        @running.setter
        def running(self, value: bool) -> None:
            self.ac.run_command(f'tmr-{"start" if value else "stop"}')

        @property
        def events(self) -> Signalization:
            self.__get_info()
            return self.__events

        @events.setter
        def events(self, value: Signalization) -> None:
            ambient = value.ambient
            lamp = int(value.lamp)
            buzzer = int(value.buzzer)
            self.ac.run_command(f'tme{ambient};{lamp};{buzzer}')

        def start(self) -> None:
            self.running = True

        def stop(self) -> None:
            self.running = False

    @property
    def countdown_timer(self):
        return self.CountdownTimer(self)

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

    @property
    def status(self):
        """Get (read) a status object."""
        return AlarmClockStatus.from_dict(self.run_command('status'))


# TODO make everything json serializable
