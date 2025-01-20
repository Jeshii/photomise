#!/usr/bin/env python3

import argparse
from tinydb import TinyDB, Query
import pendulum
from InquirerPy import inquirer
from rich.console import Console

def main(args):
    
    return

def parse_args():
    description = "Upload photos processed by photomise to bluesky"

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=description
    )

    args = parser.parse_args()

    return args


def entry():
    try:
        args = parse_args()
        main(args)
    except KeyboardInterrupt:
        print("Exiting...")


if __name__ == "__main__":
    entry()