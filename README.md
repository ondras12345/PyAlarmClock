# PyAlarmClock
A Python library for interfacing with my [AlarmClock][AlarmClock] over
a serial port.

Requires AlarmClock version >=0.5.0.

**WARNING**: This is a really early development version and still a
work-in-progress.


## MQTT adapter
`examples/mqtt_bridge.py` is an MQTT adapter. It allows you to expose an
AlarmClock connected to a computer through UART as a MQTT API. This can be
used e.g. by a home automation system like Home Assistant.


## TODO list
- [ ] doxygen ??
- [ ] `setup.py`
- [ ] Example - HTTP API



[AlarmClock]: https://github.com/ondras12345/AlarmClock
