"""PyAlarmClock exceptions.

Some driver-specific exceptions are defined within that driver's source code,
but they should all inherit PyAlarmClockException.
"""


class PyAlarmClockException(Exception):
    """Generic PyAlarmClock exception."""


class CommandError(PyAlarmClockException):
    """Error returned from AlarmClock during command execution."""

    def __init__(self, code, message='AlarmClock returned error'):
        self.code = code
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f'{self.message}: {self.code}'
