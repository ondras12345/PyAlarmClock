#!/usr/bin/env python3

"""MQTT adapter for AlarmClock."""

import sys
import argparse
import logging
import json
import datetime
import time
from enum import Enum
from dataclasses import dataclass
from typing import Union
from getpass import getpass
from PyAlarmClock import (AlarmClock, SerialAlarmClock, Alarm, AlarmEnabled,
                          Signalization, DaysOfWeek, TimeOfDay, Snooze)
import paho.mqtt.client as mqtt  # type: ignore

_LOGGER = logging.getLogger(__name__)


# Python3.9 has removeprefix, but this program needs to work with older
# versions of Python
def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix):]
    return text


class JSON_AlarmClock(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.name
        if (isinstance(obj, Snooze) or isinstance(obj, Signalization) or
                isinstance(obj, Alarm) or isinstance(obj, TimeOfDay)):
            return obj.__dict__
        if isinstance(obj, DaysOfWeek):
            return obj.active_days  # TODO also return code ??
        if isinstance(obj, AlarmEnabled):
            return obj.name
        if isinstance(obj, datetime.datetime):
            return str(obj)
        return super().default(obj)


@dataclass
class AlarmClockMQTTConfig:
    """Configuration of AlarmClockMQTT adapter."""

    # Attributes without a default cannot follow attributes with one
    device: str
    hostname: str
    port: int
    # topic without trailing '/'
    err_topic: str
    state_topic: str
    command_topic: str
    username: Union[str, None] = None
    password: str = ""
    baudrate: int = 9600


class AlarmClockMQTT:
    """An MQTT adapter for AlarmClock."""

    class Entity:
        """Representation of an AlarmClock attribute with a pollable state."""

        def get_state(self, ac: AlarmClock):
            """Get state of the entity.

            Returns a result that should be published in the entity's
            state_topic.
            """
            raise NotImplementedError()

    class CommandError(Exception):
        """Error raised by a MQTT command handler."""

    class Command:
        """Representation of a MQTT command handler."""

        def do_command(self, ac: AlarmClock, msg: str):
            """Handle reception of msg.

            The return value (if not None) of this function will be published
            in the corresponding state_topic.

            If a tuple is returned, the first value in the tuple is a topic
            under state_topic where the second value should be published.

            If a list is returned, each item will be handled according to
            the above rules.
            """
            raise NotImplementedError()

    class Switch(Entity, Command):
        """A switch that can either be OFF or ON.

        e.g. lamp, inhibit
        """

        def __init__(self, name: str):
            """Initialize a switch.

            name must be a valid name of a AlarmClock attribute.
            """
            self.name = name

        def do_command(self, ac: AlarmClock, msg: str):
            messages = {
                'ON': lambda ac: self.turn_on(ac),
                'OFF': lambda ac: self.turn_off(ac),
                '?': lambda ac: None,  # empty lambda - only stat
                '': lambda ac: None,
            }

            msg = msg.upper()
            if msg in messages:
                messages[msg](ac)
                return self.get_state(ac)
            else:
                raise AlarmClockMQTT.CommandError()

        def turn_on(self, ac: AlarmClock):
            setattr(ac, self.name, True)

        def turn_off(self, ac: AlarmClock):
            setattr(ac, self.name, False)

        def get_state(self, ac: AlarmClock):
            value = getattr(ac, self.name)
            value = 'ON' if value else 'OFF'
            return value

    class DimmableLight(Switch):
        """A dimmable light."""

        def __init__(self, name: str):
            super().__init__(name)

        def do_command(self, ac: AlarmClock, msg: str):
            try:
                value = super().do_command(ac, msg)
                return value
            except AlarmClockMQTT.CommandError:
                try:
                    setattr(ac, self.name, int(msg))
                    return self.get_state(ac)
                except ValueError as e:
                    raise AlarmClockMQTT.CommandError(str(e))

        def turn_on(self, ac: AlarmClock):
            setattr(ac, self.name, 255)

        def turn_off(self, ac: AlarmClock):
            setattr(ac, self.name, 0)

        def get_state(self, ac: AlarmClock):
            return getattr(ac, self.name)

    class AlarmCommand(Command):
        """Read an alarm."""

        def do_command(self, ac: AlarmClock, msg: str):
            try:
                index = int(msg)
            except ValueError as e:
                raise AlarmClockMQTT.CommandError(str(e))
            alarm = ac.read_alarm(index)
            alarm_json = json.dumps(alarm, cls=JSON_AlarmClock)
            return (f'alarm{index}', alarm_json)

    class AlarmsCommand(Command):
        """Read all alarms at once, faster than reading one by one."""

        def do_command(self, ac: AlarmClock, msg: str):
            alarms = ac.read_alarms()

            ret = []
            for index, alarm in enumerate(alarms):
                alarm_json = json.dumps(alarm, cls=JSON_AlarmClock)
                ret.append((f'alarm{index}', alarm_json))
            return ret

    def __init__(self, config: AlarmClockMQTTConfig):
        self._config = config

        self.COMMANDS = {
            # MQTT topic after "cmnd": function
            'ambient': self.DimmableLight('ambient'),
            'lamp': self.Switch('lamp'),
            'inhibit': self.Switch('inhibit'),
            'alarm': self.AlarmCommand(),
            'alarms': self.AlarmsCommand(),
        }

        self.ENTITIES = {
            'ambient': self.COMMANDS['ambient'],
            'lamp': self.COMMANDS['lamp'],
            'inhibit': self.COMMANDS['inhibit'],
        }

        _LOGGER.info(f'err topic: {self._config.err_topic}')
        _LOGGER.info(f'state topic: {self._config.state_topic}')
        _LOGGER.info(f'command topic: {self._config.command_topic}')

    def loop_forever(self):
        """Start the adapter.

        This is a blocking call.
        """
        client = mqtt.Client()
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        _LOGGER.info('Connecting to MQTT on '
                     f'{self._config.hostname}:{self._config.port}')
        if self._config.username is not None:
            client.username_pw_set(self._config.username,
                                   self._config.password)

        client.will_set(f'{self._config.state_topic}/available', 'offline',
                        retain=True)
        client.connect(self._config.hostname, self._config.port, 60)

        with SerialAlarmClock(self._config.device,
                              self._config.baudrate) as self.ac:
            try:
                while True:
                    client.loop_read()
                    client.loop_write()
                    client.loop_misc()
                    if self.ac.state_changed():
                        self._report_state(client, 'lamp')
                        self._report_state(client, 'inhibit')
                        self._report_state(client, 'ambient')
                    time.sleep(0.1)
            except KeyboardInterrupt:
                client.publish(f'{self._config.state_topic}/available',
                               'offline', retain=True)
                client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        _LOGGER.info(f'MQTT connected with result code {str(rc)}')
        if rc == 5:
            _LOGGER.critical('Incorrect MQTT login credentials')
            sys.exit(2)

        client.publish(f'{self._config.state_topic}/available', 'online',
                       retain=True)

        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        _LOGGER.debug(f'Subscribing to {self._config.command_topic}/+')
        client.subscribe(f'{self._config.command_topic}/+')

        for entity_id in self.ENTITIES:
            self._report_state(client, entity_id)

    def _on_message(self, client, userdata, msg):
        _LOGGER.debug(f'{msg.topic}: {str(msg.payload)}')

        if self._config.command_topic in msg.topic:
            command_id = remove_prefix(msg.topic,
                                       f'{self._config.command_topic}/')
            payload = msg.payload.decode('ascii')
            if command_id in self.COMMANDS:
                self._execute_command(client, command_id, payload)
            elif command_id in self.ENTITIES and payload == '?':
                entity_id = command_id
                self._report_state(client, entity_id)
            else:
                text = f'Bad topic for command: {msg.topic}'
                _LOGGER.error(text)
                client.publish(self._config.err_topic, text)

    def _report_state(self, client: mqtt.Client, entity_id: str):
        client.publish(f'{self._config.state_topic}/{entity_id}',
                       self.ENTITIES[entity_id].get_state(self.ac))

    def _execute_command(self, client: mqtt.Client, command_name: str,
                         msg: str):
        try:
            ret = self.COMMANDS[command_name].do_command(self.ac, msg)
            if ret is not None:
                if not isinstance(ret, list):
                    ret = [ret]
                for value in ret:
                    if isinstance(value, tuple):
                        topic, message = value
                        client.publish(f'{self._config.state_topic}/{topic}',
                                       message)
                    else:
                        client.publish(
                                f'{self._config.state_topic}/{command_name}',
                                value
                                )
        except self.CommandError as e:
            details = '\n' + str(e) if str(e) != '' else ''
            text = (f'Bad payload for '
                    f'{self._config.command_topic}/{command_name}:'
                    f' {msg}{details}')
            _LOGGER.error(text)
            client.publish(self._config.err_topic, text)


if __name__ == '__main__':
    # add_help=False avoids conflict with -h for hostname
    parser = argparse.ArgumentParser(
            add_help=False,
            description='A MQTT bridge for PyAlarmClock')

    parser.add_argument('--help', '-H', action='help',
                        help='show this help message and exit')

    parser.add_argument('--hostname', '-h', default='localhost',
                        help='MQTT broker host (default: %(default)s')

    parser.add_argument('--port', '-p', type=int, default=1883,
                        help='MQTT broker port (default: %(default)d)')

    parser.add_argument('--topic', '-t', default='alarmclock',
                        help='MQTT topic prefix (default: %(default)s)')

    parser.add_argument('--username', '-u', default=None,
                        help='MQTT username (default: anonymous login)')

    parser.add_argument('--password', '-P', default=None,
                        help='MQTT password (default: prompt for password)')

    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Log debug level messages')

    parser.add_argument('--logfile', default=None,
                        help='File to output the log to. (default: stderr)')

    parser.add_argument('device',
                        help='Serial port the device is attached to')

    parser.add_argument('--baudrate', '-b', type=int, default=9600,
                        help='baudrate to be used with the serial port'
                        ' (default: %(default)d)')

    args = parser.parse_args()

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG

    format_string = '%(asctime)s %(levelname)s %(message)s'
    formatter = logging.Formatter(format_string)
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
