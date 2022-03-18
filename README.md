# PyAlarmClock
A Python library for interfacing with my [AlarmClock][AlarmClock] over
a serial port.

Requires AlarmClock version >=0.5.0.

**WARNING**: This is a really early development version and still a
work-in-progress.


## Installation
I recommend that you do this in a virtual environment.
```
# standard installation
pip3 install .

# development version
pip3 install .[tests,dev]
# Type `make help` for information about linting and testing.
```

`src/PyAlarmClock/cmds/mqtt_bridge.py` will be installed as `ac2mqtt`
and `src/PyAlarmClock/cmds/EEPROM_tool.py` will be installed as `acEEPROM`.


## MQTT adapter
`ac2mqtt` is an MQTT adapter. It allows you to expose an
AlarmClock connected to a computer through UART as an MQTT API. This can be
used e.g. by a home automation system like Home Assistant.

### Configuration
You can either use command line arguments or a configuration file (or both, in
which case arguments override what's set in the file).

```
[MQTT]
hostname = localhost
username = user
password = pass

[serial]
device = /dev/ttyUSB0
baudrate = 9600
```

To tell the program to read a config file, use the `--config-file` / `-c`
argument.


### Systemd
`ac2mqtt` can be used as a systemd service.
Put your configuration in `/etc/ac2mqtt.conf`.

Put a systemd unit file like this in `/etc/systemd/system/ac2mqtt.service`:
(Path to the ac2mqtt command will depend on where you installed it.
`which ac2mqtt` is your friend. I tend to put stuff like this in venvs under
`/opt`.)
```
[Unit]
Description=Provide MQTT API for AlarmClock
# mosquitto.service only if you run mosquitto broker on the same machine
# dev-ttyUSB0 is just an example, adjust for your real device
After=mosquitto.service dev-ttyUSB0.device

[Service]
# User to run the service as instead of root.
User=homeassistant
ExecStart=/path/to/ac2mqtt -c /etc/ac2mqtt.conf
Restart=on-failure
RestartSec=30s
RestartPreventExitStatus=255

[Install]
WantedBy=multi-user.target
```

Start the service:
```
sudo systemctl daemon-reload
sudo systemctl enable --now ac2mqtt.service
```


## TODO list
- [ ] doxygen ??



[AlarmClock]: https://github.com/ondras12345/AlarmClock
