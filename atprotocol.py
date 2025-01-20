#!/usr/bin/env python3

import argparse
from tinydb import TinyDB, Query
import pendulum
from InquirerPy import inquirer
from rich.console import Console
from atproto import Client, models
import keyring
import logging
import sys
import termios
import tty
import piexif


def get_password_from_keyring(logger, user: str):
    try:
        password = keyring.get_password("photomise-atprotocol", user)
        return password
    except Exception as e:
        logger.debug(f"Unable to get password: {e}")
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            password = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        keyring.set_password("photomise-atprotocol", user, password)
        return password


def get_image_aspect_ratio(image_path: str) -> tuple:
    try:
        exif_dict = piexif.load(image_path)
        image_width = exif_dict["0th"][piexif.ImageIFD.ImageWidth]
        image_height = exif_dict["0th"][piexif.ImageIFD.ImageLength]
        return (image_width, image_height)
    except (piexif.InvalidImageDataError, KeyError):
        return None


def main(args):
    client = Client()
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)

    if not args.user:
        args.user = inquirer.text(message="Enter username").execute()

    password = get_password_from_keyring(logger, args.user)
    client.login(args.user, password)

    paths = ["cat.jpg", "dog.jpg", "bird.jpg"]
    image_alts = [
        "Text version",
        "of the image (ALT)",
        "This parameter is optional",
    ]

    image_aspect_ratios = [
        models.AppBskyEmbedDefs.AspectRatio(height=1, width=1),
        models.AppBskyEmbedDefs.AspectRatio(height=4, width=3),
        models.AppBskyEmbedDefs.AspectRatio(height=16, width=9),
    ]

    images = []
    for path in paths:
        with open(path, "rb") as f:
            images.append(f.read())

    client.send_images(
        text="Post with image from Python",
        images=images,
        image_alts=image_alts,
        image_aspect_ratios=image_aspect_ratios,
    )

    return


def parse_args():
    description = "Upload photos processed by photomise to bluesky"

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=description
    )

    parser.add_argument(
        "--user",
        "-u",
        help="Your bluesky username",
    )

    parser.add_argument(
        "--random",
        "-r",
        action="store_true",
        help="Post a random photo",
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
