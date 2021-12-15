#!/usr/bin/env python3
"""Do various operations with the alarm clock's EEPROM."""

import PyAlarmClock
import argparse
import sys
import logging
from tqdm import tqdm


def arg_auto_int(x):
    """Convert a string representing an integer literal to int."""
    return int(x, 0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('device',
                        help='Serial port the device is attached to')

    parser.add_argument('--baudrate', '-b', type=int, default=9600,
                        help='baudrate to be used with the serial port'
                        ' (default: %(default)d)')

    subparsers = parser.add_subparsers(dest='operation')

    parser_read = subparsers.add_parser(
            'read',
            help='Read data from EEPROM to a binary file'
            )
    parser_read.add_argument('address', type=arg_auto_int,
                             help='Start address')
    parser_read.add_argument('size', type=arg_auto_int,
                             help='Size of region to dump')
    parser_read.add_argument('file', type=argparse.FileType('wb'),
                             help='Name of the binary file')

    parser_write = subparsers.add_parser(
            'write',
            help='Write data from a binary file to EEPROM'
            )
    parser_write.add_argument('address', type=arg_auto_int,
                              help='Start address')
    parser_write.add_argument('file', type=argparse.FileType('rb'),
                              help='Name of the binary file')

    args = parser.parse_args()

    if args.operation is None:
        parser.print_help()
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)

    with PyAlarmClock.AlarmClock(args.device, args.baudrate) as ac:
        if args.operation == "read":
            for address in tqdm(range(args.address, args.address+args.size)):
                args.file.write(bytes([ac.EEPROM[address]]))

        if args.operation == "write":
            data = args.file.read()
            for address, byte in enumerate(tqdm(data)):
                ac.EEPROM[args.address + address] = byte
