#!/usr/bin/env python3
"""MQTT adapter for AlarmClock."""

# TODO https://github.com/unixorn/ha-mqtt-discoverable

import argparse
import configparser
import logging
import json
import datetime
import time
import sys
from enum import Enum
import dataclasses
from dataclasses import dataclass
from typing import Union, Optional, Dict, Tuple, List
from getpass import getpass
from PyAlarmClock import (AlarmClock, SerialAlarmClock, Alarm, AlarmEnabled,
                          Signalization, DaysOfWeek, TimeOfDay, Snooze,
                          AmbientStatus)
import paho.mqtt.client as mqtt  # type: ignore

_LOGGER = logging.getLogger(__name__)


# Python3.9 has removeprefix, but this program needs to work with older
# versions of Python
def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


class JSON_AlarmClock(json.JSONEncoder):
    """JSON encoder for PyAlarmClock objects."""

    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.name
        if dataclasses.is_dataclass(obj):
            return obj.__dict__
        if isinstance(obj, DaysOfWeek):
            return obj.active_days  # TODO also return code ??
        if (isinstance(obj, datetime.datetime) or
                isinstance(obj, datetime.timedelta)):
            return str(obj)
        return super().default(obj)


class MQTTCommandError(Exception):
    """Error raised by an MQTT command handler."""


class Command:
    """Representation of an MQTT command handler."""

    retain = False

    def do_command(
        self, ac: AlarmClock, msg: str
    ) -> Union[None, str, Tuple[str, str], List]:
        """Handle reception of msg.

        The return value (if not None) of this function will be published
        in the corresponding state_topic. If the retain attribute is set on
        the command, the messages will sent with retain=True.

        If a tuple is returned, the first value in the tuple is a topic
        under state_topic where the second value should be published.

        If a list is returned, each item will be handled according to
        the above rules.
        """
        raise NotImplementedError()


class Switch(Command):
    """A switch that can be turned OFF or ON.

    E.g. lamp, inhibit
    """

    def __init__(self, name: str):
        """Initialize a switch.

        name must be a valid name of an AlarmClock attribute.
        """
        self.name = name

    def do_command(self, ac: AlarmClock, msg: str) -> None:
        messages = {
            'ON': lambda ac: self.turn_on(ac),
            'OFF': lambda ac: self.turn_off(ac),
            '?': lambda ac: None,  # empty lambda - only stat
            '': lambda ac: None,
        }

        msg = msg.upper()
        if msg in messages:
            messages[msg](ac)
        else:
            raise MQTTCommandError()

    def turn_on(self, ac: AlarmClock):
        setattr(ac, self.name, True)

    def turn_off(self, ac: AlarmClock):
        setattr(ac, self.name, False)


class DimmableLight(Switch):
    """A dimmable light."""

    def __init__(self, name: str):
        super().__init__(name)

    def do_command(self, ac: AlarmClock, msg: str) -> None:
        try:
            super().do_command(ac, msg)
        except MQTTCommandError:
            try:
                setattr(ac, self.name, int(msg))
            except ValueError as e:
                raise MQTTCommandError(repr(e))

    def turn_on(self, ac: AlarmClock):
        setattr(ac, self.name, 255)

    def turn_off(self, ac: AlarmClock):
        setattr(ac, self.name, 0)


class RTC(Command):
    """Real time clock."""

    def do_command(self, ac: AlarmClock, msg: str):
        if msg in ("", "?"):
            return self.get_state(ac)
        try:
            ac.RTC_time = datetime.datetime.fromisoformat(msg)
        except Exception as e:
            raise MQTTCommandError(repr(e))

    def get_state(self, ac: AlarmClock) -> str:
        return ac.RTC_time.astimezone().isoformat(timespec="seconds")


class CountdownTimer(Command):
    def do_command(self, ac: AlarmClock, msg: str):
        messages = {
            'START': ac.countdown_timer.start,
            'STOP': ac.countdown_timer.stop,
            '?': lambda: None,  # empty lambda - only stat
            '': lambda: None,
        }

        if msg.upper() in messages:
            messages[msg.upper()]()
            return self.get_state(ac)

        try:
            d = json.loads(msg)
            _LOGGER.debug("Got json: %r", d)
            if "events" in d:
                ac.countdown_timer.events = Signalization(
                    ambient=d["events"]["ambient"],
                    lamp=d["events"]["lamp"],
                    buzzer=d["events"]["buzzer"]
                )
            if "time" in d:
                time = d["time"].split(":")
                ac.countdown_timer.time = datetime.timedelta(
                    hours=int(time[0]),
                    minutes=int(time[1]),
                    seconds=int(time[2])
                )
            if "running" in d:
                if d["running"]:
                    ac.countdown_timer.start()
                else:
                    ac.countdown_timer.stop()
        except Exception as e:
            raise MQTTCommandError(repr(e))

    def get_state(self, ac: AlarmClock) -> str:
        info = ac.countdown_timer.get_all()
        _LOGGER.debug("CountdownTimer state: %r", info)
        return json.dumps(info, cls=JSON_AlarmClock)


class AlarmCommand(Command):
    """Read an alarm."""

    def do_command(self, ac: AlarmClock, msg: str) -> Tuple[str, str]:
        try:
            index = int(msg)
            alarm = ac.read_alarm(index)
        except ValueError as e:
            raise MQTTCommandError(repr(e))
        now = datetime.datetime.now()
        alarm_dict = {
            **alarm.__dict__,
            'next_alarm_time': alarm.get_next_alarm_time(now)
        }
        alarm_json = json.dumps(alarm_dict, cls=JSON_AlarmClock)
        return (f'alarms/alarm{index}', alarm_json)


class AlarmsCommand(Command):
    """Read all alarms at once, faster than reading one by one."""

    # We poll alarms automatically (see _report_status),
    # so it should be safe to use retain=True.
    retain = True

    next_update = None

    def do_command(self, ac: AlarmClock, msg: str) -> List[Tuple[str, str]]:
        self.alarms = ac.read_alarms()
        return self.send_update()

    def send_update(self) -> List[Tuple[str, str]]:
        ret = []
        now = datetime.datetime.now()
        next_alarm_times = [a.get_next_alarm_time(now) for a in self.alarms]
        for index, alarm in enumerate(self.alarms):
            alarm_dict = {
                **alarm.__dict__,
                'next_alarm_time': next_alarm_times[index]
            }
            alarm_json = json.dumps(alarm_dict, cls=JSON_AlarmClock)
            ret.append((f'alarms/alarm{index}', alarm_json))

            valid_dts = [dt for dt in next_alarm_times if dt is not None]
            if len(valid_dts) == 0:
                self.next_update = None
            else:
                self.next_update = min(valid_dts)
        return ret


class WriteAlarmCommand(Command):
    """Write an alarm and save the changes to the EEPROM."""

    def do_command(self, ac: AlarmClock, msg: str):
        try:
            d = json.loads(msg)
            _LOGGER.debug("Got json: %r", d)
            index = int(d["index"])
            alarm = Alarm(
                enabled=AlarmEnabled[d["enabled"]],
                days_of_week=DaysOfWeek.from_list(d["days_of_week"]),
                time=TimeOfDay(hours=d["time"]["hours"],
                               minutes=d["time"]["minutes"]),
                snooze=Snooze(time=d["snooze"]["time"],
                              count=d["snooze"]["count"]),
                signalization=Signalization(
                    ambient=d["signalization"]["ambient"],
                    lamp=d["signalization"]["lamp"],
                    buzzer=d["signalization"]["buzzer"]
                    )
                )
            ac.write_alarm(index, alarm)
            ac.save_EEPROM()
        except Exception as e:
            raise MQTTCommandError(repr(e))


class StopButtonCommand(Command):
    """Emulate pressing the stop button."""

    def do_command(self, ac: AlarmClock, msg: str):
        if msg.upper() == 'STOP':
            ac.button_stop()
        else:
            raise MQTTCommandError(f"invalid payload for stop: {msg}")


class RunCommandCommand(Command):
    """Run a CLI command, parse it's YAML output and return it as JSON."""

    def do_command(self, ac: AlarmClock, msg: str) -> str:
        try:
            return json.dumps(ac.run_command(msg), default=str)
        except Exception as e:
            raise MQTTCommandError(repr(e))


@dataclass
class AlarmClockMQTTConfig:
    """Configuration of AlarmClockMQTT adapter."""

    # Attributes without a default must be specified first
    device: str
    hostname: str
    port: int
    # topic without trailing '/'
    err_topic: str
    state_topic: str
    command_topic: str
    username: Optional[str] = None
    password: str = ""
    baudrate: int = 9600


class AlarmClockMQTT:
    """An MQTT adapter for AlarmClock."""

    def __init__(self, config: AlarmClockMQTTConfig):
        self._config = config

        ambient = DimmableLight('ambient')
        lamp = Switch('lamp')
        inhibit = Switch('inhibit')
        rtc = RTC()
        timer = CountdownTimer()

        self.COMMANDS: Dict[str, Command] = {
            # MQTT topic after "cmnd": function
            'ambient': ambient,
            'lamp': lamp,
            'inhibit': inhibit,
            'rtc': rtc,
            'timer': timer,
            'alarm': AlarmCommand(),
            'alarms': AlarmsCommand(),
            'alarm/write': WriteAlarmCommand(),
            'button/stop': StopButtonCommand(),
            'run_command': RunCommandCommand(),
        }

        _LOGGER.info(f'err topic: {self._config.err_topic}')
        _LOGGER.info(f'state topic: {self._config.state_topic}')
        _LOGGER.info(f'command topic: {self._config.command_topic}')

    def loop_forever(self):
        """Start the adapter.

        This is a blocking call.
        """
        client = mqtt.Client()
        client.on_disconnect = self._on_disconnect
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        _LOGGER.info('Connecting to MQTT on '
                     f'{self._config.hostname}:{self._config.port}')
        if self._config.username is not None:
            client.username_pw_set(self._config.username,
                                   self._config.password)

        client.will_set(
            f'{self._config.state_topic}/available',
            'offline', retain=True
        )
        client.connect(self._config.hostname, self._config.port, 60)

        with SerialAlarmClock(self._config.device,
                              self._config.baudrate) as self.ac:
            try:
                while True:
                    # TODO use client.loop_start() (loop in a new thread) ??
                    client.loop_read()
                    client.loop_write()
                    client.loop_misc()

                    if self.ac.state_changed():
                        self._report_status(client)

                    # keep next_alarm_time updated
                    now = datetime.datetime.now()
                    alarms_command = self.COMMANDS['alarms']
                    next_update = alarms_command.next_update
                    if next_update is not None and now > next_update:
                        self._publish_command_response(
                            client,
                            'alarms',
                            alarms_command.send_update()
                        )

                    time.sleep(0.1)
            except KeyboardInterrupt:
                client.publish(f'{self._config.state_topic}/available',
                               'offline', retain=True)
                client.disconnect()

    def _error(self, client, text: str) -> None:
        """Send error to _LOGGER and MQTT err_topic."""
        _LOGGER.error(text)
        client.publish(self._config.err_topic, text)

    def _on_disconnect(self, client, userdata, rc) -> None:
        if rc != 0:
            _LOGGER.error(f"MQTT disconnected ({rc})")
            _LOGGER.info("MQTT reconnecting")
            client.reconnect()

    def _on_connect(self, client, userdata, flags, rc) -> None:
        _LOGGER.info(f'MQTT connected with result code {str(rc)}')
        if rc == 5:
            raise Exception('Incorrect MQTT login credentials')

        client.publish(f'{self._config.state_topic}/available', 'online',
                       retain=True)

        client.publish(f'{self._config.state_topic}/number_of_alarms',
                       self.ac.number_of_alarms, retain=True)

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        _LOGGER.debug(f'Subscribing to {self._config.command_topic}/#')
        client.subscribe(f'{self._config.command_topic}/#')

        self._report_status(client, onconnect=True)

    def _on_message(self, client, userdata, msg) -> None:
        _LOGGER.debug('%s: %s', msg.topic, msg.payload)

        if self._config.command_topic in msg.topic:
            command_id = remove_prefix(msg.topic,
                                       f'{self._config.command_topic}/')
            payload = msg.payload.decode('ascii')
            if command_id in self.COMMANDS:
                self._execute_command(client, command_id, payload)
            else:
                self._error(client, f'Bad topic for command: {msg.topic}')

    def _report_status(self, client: mqtt.Client, onconnect=False) -> None:
        """Poll AlarmClock status & publish with retain."""
        status = self.ac.status
        for attr in ('ambient', 'lamp', 'inhibit', 'display_backlight',
                     'active_alarm_ids', 'alarm_with_active_ambient_ids'):
            value = getattr(status, attr)
            if isinstance(value, bool):
                value = 'ON' if value else 'OFF'
            elif isinstance(value, list):
                value = json.dumps(value)
            elif isinstance(value, Enum):
                value = value.name
            elif isinstance(value, AmbientStatus):
                # current will be outdated, do not publish
                value = str(value.target)
            # TODO only publish if it changed
            client.publish(
                f'{self._config.state_topic}/{attr}', value, retain=True
            )
        if status.alarms_changed or onconnect:
            self._execute_command(client, 'alarms', '?')

    def _execute_command(self, client: mqtt.Client, command_name: str,
                         msg: str) -> None:
        command = self.COMMANDS[command_name]
        try:
            ret = command.do_command(self.ac, msg)
            self._publish_command_response(client, command_name, ret)
        except MQTTCommandError as e:
            details = '\n' + str(e) if str(e) != '' else ''
            self._error(
                client,
                f'Bad payload for '
                f'{self._config.command_topic}/{command_name}: {msg}{details}'
            )

    def _publish_command_response(self, client: mqtt.Client,
                                  command_name: str, ret) -> None:
        command = self.COMMANDS[command_name]
        if ret is None:
            return
        if not isinstance(ret, list):
            ret = [ret]
        for value in ret:
            if isinstance(value, tuple):
                topic, message = value
            else:
                topic, message = command_name, value

            client.publish(
                f'{self._config.state_topic}/{topic}',
                message, retain=command.retain
            )


def main():
    parser = argparse.ArgumentParser(
            add_help=False,  # avoids conflict with -h for hostname
            description='An MQTT bridge for PyAlarmClock')

    parser.add_argument(
        '--help', '-H', action='help',
        help='show this help message and exit'
    )

    defaults = dict()
    defaults['hostname'] = 'localhost'
    parser.add_argument(
        '--hostname', '-h', default=None,
        help=f"MQTT broker host (default: {defaults['hostname']})"
    )

    defaults['port'] = 1883
    parser.add_argument(
        '--port', '-p', type=int, default=None,
        help=f"MQTT broker port (default: {defaults['port']})"
    )

    defaults['topic'] = 'alarmclock'
    parser.add_argument(
        '--topic', '-t', default=None,
        help=f"MQTT topic prefix (default: {defaults['topic']})"
    )

    defaults['username'] = None
    parser.add_argument(
        '--username', '-u', default=None,
        help='MQTT username (default: anonymous login)'
    )

    defaults['password'] = None
    parser.add_argument(
        '--password', '-P', default=None,
        help='MQTT password (default: prompt for password)'
    )

    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='log debug level messages'
    )

    defaults['logfile'] = None
    parser.add_argument(
        '--logfile', default=None,
        help='File to output the log to. (default: stderr)'
    )

    defaults['device'] = None
    parser.add_argument(
        '--device', type=str, default=None,
        help='serial port the device is attached to'
    )

    defaults['baudrate'] = 9600
    parser.add_argument(
        '--baudrate', '-b', type=int, default=None,
        help="baudrate to be used with the serial port"
             f" (default: {defaults['baudrate']})"
    )

    parser.add_argument(
        '--config-file', '-c',
        type=argparse.FileType('r'),
        help='configuration file'
    )

    args = parser.parse_args()

    # Needed to determine if value from configuration file should be applied.
    default_args = []

    for arg in vars(args):
        if getattr(args, arg) is None and arg in defaults:
            setattr(args, arg, defaults[arg])
            default_args.append(arg)

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    format_string = '%(asctime)s %(levelname)s %(message)s'
    formatter = logging.Formatter(format_string)
    # TODO all logging, not just _LOGGER
    _LOGGER.setLevel(logging.DEBUG)
    if args.logfile is not None:
        # At least some info in stderr
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(formatter)
        _LOGGER.addHandler(handler)

        handler = logging.FileHandler(args.logfile)
        handler.setLevel(level)
        handler.setFormatter(formatter)
        _LOGGER.addHandler(handler)

    else:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(formatter)
        _LOGGER.addHandler(handler)

    if args.config_file is not None:
        _LOGGER.info(f'Reading config from {args.config_file.name}')
        config = configparser.ConfigParser()
        config.read_file(args.config_file)
        _LOGGER.debug('Config sections: %r', config.sections())

        def parseopt(section, opt):
            if opt in config[section]:
                value = config[section][opt]
                # do not override arguments
                if opt in default_args:
                    _LOGGER.debug('Setting from config file: %s', opt)
                    setattr(args, opt, value)

        parseopt('MQTT', 'hostname')
        parseopt('MQTT', 'port')
        args.port = int(args.port)
        parseopt('MQTT', 'username')
        parseopt('MQTT', 'password')
        parseopt('MQTT', 'topic')
        parseopt('serial', 'device')
        parseopt('serial', 'baudrate')
        args.baudrate = int(args.baudrate)

    if args.device is None:
        _LOGGER.error("Device is not specified")
        sys.exit(255)

    password = args.password
    if args.username is not None and password is None:
        password = getpass()

    config = AlarmClockMQTTConfig(
            device=args.device, baudrate=args.baudrate,
            hostname=args.hostname, port=args.port,
            username=args.username, password=password,
            err_topic=f'{args.topic}/err',
            state_topic=f'{args.topic}/stat',
            command_topic=f'{args.topic}/cmnd',
            )
    ac_mqtt = AlarmClockMQTT(config)
    ac_mqtt.loop_forever()


if __name__ == '__main__':
    main()
