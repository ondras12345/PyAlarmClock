"""Drivers for communicating with AlarmClock."""

from .base import AlarmClock  # noqa: F401
from .serial import SerialAlarmClock  # noqa: F401

# Warning: If you try to implement something like MQTTAlarmClock, keep in mind
# that there might be hidden race conditions - e.g. you need to `sel` the
# correct alarm before you `ls`.
