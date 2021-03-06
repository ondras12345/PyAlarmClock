from typing import Union, List


class DaysOfWeek:
    """An object that stores a boolean value for each day of the week.

    It can read or produce a one byte code compatible with what AlarmClock
    uses.
    """

    days = {
        'Monday': 1,
        'Tuesday': 2,
        'Wednesday': 3,
        'Thursday': 4,
        'Friday': 5,
        'Saturday': 6,
        'Sunday': 7,
        }

    def __init__(self, code: int = 0):
        """Initialize the DaysOfWeek object with specified code or 0x00.

        Code is a single byte binary representation of the object.
        0x00 means all stored values are False.
        """
        # Filter out bit 0. It has no meaning and should always be zero.
        self.code = code & 0xFE

    @classmethod
    def from_list(cls, li: Union[List[str], List[int]]):
        """Create an instance from a list of str names or numbers of days."""
        dow = cls()
        for day in li:
            dow.set_day(day, True)
        return dow

    def get_day(self, day: Union[str, int]) -> bool:
        """Get the boolean value for a single day of the week."""
        if isinstance(day, str):
            if day not in self.days:
                raise TypeError(f'unknown day: {repr(day)}')
            day = self.days[day]
        if day < 1 or day > 7:
            raise ValueError(f"{day} is not a valid day of the week")
        return self.code & (2**day) > 0

    def set_day(self, day: Union[str, int], value: bool) -> None:
        """Set the boolean value for a single day of the week."""
        if isinstance(day, str):
            if day not in self.days:
                raise TypeError(f'unknown day: {repr(day)}')
            day = self.days[day]
        if day < 1 or day > 7:
            raise ValueError(f"{day} is not a valid day of the week")
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
    def active_days(self) -> List[str]:
        """Get an array of days of the week for which the stored value is True.

        Names of the days of the week are returned as strings with the first
        letter capitalized.
        """
        return [day for day in self.days if self.get_day(day)]

    def __str__(self) -> str:
        """Get all days for which the stored value is True joined with ', '."""
        return ', '.join(self.active_days)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({repr(self.code)})'

    def __eq__(self, other):
        return self.code == other.code
