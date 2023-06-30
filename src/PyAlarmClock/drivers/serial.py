import logging
import serial  # type: ignore
import re
import yaml
from .base import AlarmClock
from ..dataclasses import Alarm
from ..exceptions import PyAlarmClockException, CommandError
from ..const import CommandErrorCode

_LOGGER = logging.getLogger(__name__)


class SerialAlarmClock(AlarmClock):
    """Representation of an AlarmClock connected via a serial port."""

    class Serial:
        """An object that handles serial port communication with AlarmClock."""

        class PromptTimeout(PyAlarmClockException):
            """Timeout when waiting for a prompt."""

        ERROR_REGEX = "^err (0x[0-9]{,2}): .*\r?$"
        PROMPT_REGEX = "^(A?[0-9]{,3})> "
        YAML_BEGIN_REGEX = "^---\r?$"
        YAML_END_REGEX = "^[.]{3}\r?$"

        def __init__(self, port, baudrate):
            """Initialize the serial port connection.

            This can take a few seconds because it needs to wait until
            a prompt is received.
            """
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
            self.bel_received = False
            try:
                self.wait_for_prompt()
            except self.PromptTimeout:
                # This should happen if opening the serial port does not cause
                # a reset of the Arduino. To prevent it from resetting, try
                # something like this:
                # stty -F /dev/ttyUSB0 -hup
                self.process_command('sync')

        def wait_for_prompt(self, timeout_count_max=4):
            """Wait unit a prompt is received on the serial port.

            This function should only be called after a command is sent.
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
                if char == '\a':
                    self.bel_received = True
                if char == '':
                    _LOGGER.debug('timeout')
                    timeout_count += 1
                    continue
                _LOGGER.debug(f'got: {repr(char)}')
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
            """Send a string to the serial port."""
            a = command.encode('ASCII')
            _LOGGER.debug(f'Sending: {a}')
            self.ser.write(a)

        def process_command(self, command):
            """Send a command and get it's output."""
            self.send(command + '\n')
            line = ''
            yaml_output = ''
            error_line = None
            in_yaml = False
            while not error_line:
                line = self.ser.readline().decode('ASCII')
                _LOGGER.debug(f'got: {repr(line)}')
                if '\a' in line:
                    self.bel_received = True
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

        def check_bel_received(self) -> bool:
            """Return value of bel_received and clear it.

            This also checks characters in the buffer.
            """
            old_timeout = self.ser.timeout
            self.ser.timeout = 0
            while True:
                character = self.ser.read(1).decode('ASCII')
                if not character:
                    break
                _LOGGER.debug(f'check_bel_received got: {repr(character)}')
                if character == '\a':
                    self.bel_received = True
            self.ser.timeout = old_timeout

            value = self.bel_received
            self.bel_received = False

            return value

    def __init__(self, port: str, baudrate: int = 9600):
        """Initialize the object and establish serial communication."""
        self.__serial = self.Serial(port, baudrate)
        super().__init__()

    def run_command(self, command: str):
        """Send a command, parse it's YAML output and return the result."""
        error, yaml_output = self.__serial.process_command(command)
        if error != CommandErrorCode.Ok:
            raise CommandError(error)
        if yaml_output == '':
            return None
        _LOGGER.debug(f'Parsing YAML:\n{yaml_output}')
        output = yaml.safe_load(yaml_output)
        return output

    def read_alarm(self, index: int) -> Alarm:
        alarm = super().read_alarm(index)
        if self.__serial.prompt != f'A{index}':
            raise AssertionError(
                f"AlarmClock prompt is incorrect: {self.__serial.prompt}")
        return alarm

    def state_changed(self) -> bool:
        """Return true if BEL character was received from AlarmClock.

        This is NOT a blocking call.

        AlarmClock needs to have feature/CLI-BEL merged in order to send
        BEL (0x07) on state changes.
        """
        return self.__serial.check_bel_received()

    def __enter__(self):
        """For use with `with`."""
        return self

    def __exit__(self, type, value, traceback):
        """For use with `with`."""
        self.close()
        return False

    def is_open(self):
        """Return True if the serial port is open."""
        return self.__serial.ser.isOpen()

    def close(self):
        """Close the serial port."""
        _LOGGER.debug('Closing serial port')
        self.__serial.ser.close()

    # def open(self):
    #     """Open the serial port"""
    #     self.__serial.ser.open()
