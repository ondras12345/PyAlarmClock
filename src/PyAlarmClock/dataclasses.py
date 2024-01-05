from dataclasses import dataclass
from typing import List
from .const import AlarmEnabled, DisplayBacklightStatus
from .days_of_week import DaysOfWeek


@dataclass
class Signalization:
    """Signalization settings of an alarm."""

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


@dataclass(frozen=True)
class AmbientStatus:
    """Representation of ambient status.

    This object is immutable to indicate that it cannot be used to send
    commands to the alarm clock.
    """
    current: int
    target: int


@dataclass(frozen=True)
class AlarmClockStatus:
    """AlarmClock status object.

    All this information can be fetched using one command.
    Updating status is a good first response to state_changed event (BEL)
    in serial driver.
    """

    active_alarm_ids: List[int]
    alarm_with_active_ambient_ids: List[int]
    # true if alarms have changed since last 'la' command (read_alarms).
    alarms_changed: bool
    # hardware status & inhibit
    display_backlight: DisplayBacklightStatus
    ambient: AmbientStatus
    lamp: bool
    inhibit: bool

    @classmethod
    def from_dict(cls, d):
        """Create an instance from a dict.

        The dict needs to contain the following
        keys:
        - "active alarms"
        - "alarms with active ambient"
        - "alarms changed"
        - "display"
        - "ambient"
          - "current"
          - "target"
        - "lamp"
        - "inhibit"
        """

        # convert the following yaml syntax
        # ---
        # active alarms:
        # ---
        # to an empty list
        for key in ("active alarms", "alarms with active ambient"):
            if d[key] is None:
                d[key] = []

        return cls(
            active_alarm_ids=d["active alarms"],
            alarm_with_active_ambient_ids=d["alarms with active ambient"],
            alarms_changed=bool(d["alarms changed"]),
            display_backlight=DisplayBacklightStatus(d["display"]),
            ambient=AmbientStatus(current=d["ambient"]["current"],
                                  target=d["ambient"]["target"]),
            lamp=bool(d["lamp"]),
            inhibit=bool(d["inhibit"])
            )
