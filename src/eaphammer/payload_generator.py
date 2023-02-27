#!/usr/bin/env python

import base64
import string
import random
import sys

from argparse import ArgumentParser
from eaphammer_core.payloads import ScheduledPayload

def set_options():

    parser = ArgumentParser()

    parser.add_argument('--delay',
                    dest='delay',
                    type=int,
                    default=180,
                    help='Set the timed payload delay in seconds.')

    parser.add_argument('--command',
                    dest='command',
                    required=True,
                    type=str,
                    help='The command to run on the target machine.')

    parser.add_argument('--args',
                    dest='args',
                    required=True,
                    type=str,
                    help='Arguments passed to the command specified using the --comand flag.')

    args = parser.parse_args()

    options = args.__dict__

    return options

def main():

    options = set_options()

    s = ScheduledPayload(options['command'],
                        options['args'],
                        delay=options['delay']) 

    print
    print
    print s.execute()
