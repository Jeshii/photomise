#!/usr/bin/env python3

import argparse
from tinydb import Query
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
import photomise as base
import configparser
import random


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


def get_users(config):
    try:
        users = config["Accounts"].get("Bluesky") 
        return users.split(',') 
    except (configparser.NoSectionError, configparser.NoOptionError, AttributeError):
        config["Accounts"]["Bluesky"] = ""
        username = inquirer.text(message="Enter your Bluesky username").execute()
        config["Accounts"]["Bluesky"] = username
        return config["Accounts"]["Bluesky"].split(',') 
    
def fix_bluesky(current):
    return current.replace("@", "").strip()

def add_user(config):
    users = get_users(config)
    new_user = inquirer.text(message="Enter your Bluesky username",filter=fix_bluesky).execute()
    users.append(new_user)
    config["Accounts"]["Bluesky"] = ",".join(users)
    return new_user

def main(args):
    client = Client()
    console = Console()
    config = base.get_config()
    event_db = base.get_event_db(config["Paths"]["database_dir"])
    Event = Query()
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    users = get_users(config)

    if not args.user:
        user_list = users
        user_list.append("New User")
        args.user = inquirer.select(message="Select a user", choices=user_list).execute()
        if args.user == "New User":
            args.user = add_user(config)
    elif args.user not in users:
        args.user = add_user(args.user)

    if not args.random:
        event_names = [event["event"] for event in event_db.search(Event)]
        if not event_names:
            console.print("[bold red]No events found. Please run photomise first!")
            return
        event_name = inquirer.select(
            message="Choose an event to post", choices=event_names
        ).execute()
    else:
        all_events = event_db.search(Event.posted == [])

        if all_events:
            random_event = random.choice(all_events)
            event_name = random_event["event"]

    if not args.text:
        args.text = inquirer.text(message="Enter the text for the post").execute()

    password = get_password_from_keyring(logger, args.user)
    client.login(args.user, password)

    event = event_db.query(Event.event == event_name)

    image_alts = []
    images = []
    image_aspect_ratios = []
    for path in event["photos"]:

        height, width = get_image_aspect_ratio(path)
        image_aspect_ratios.append(
            models.AppBskyEmbedDefs.AspectRatio(height=height, width=width)
        )

        with open(path, "rb") as f:
            images.append(f.read())

        if args.alts:
            image_alts.append(
                inquirer.text(message=f"Enter image alt text for {path}").execute()
            )

    client.send_images(
        text=args.text,
        images=images,
        image_alts=image_alts,
        image_aspect_ratios=image_aspect_ratios,
    )
    if client:
        console.print(client)

        event_db.update_one(
            {"event": event_name},
            {
                "$push": {
                    "posted": {
                        "where": "Bluesky",
                        "account": base.santitize_text(args.user),
                        "date": pendulum.now().timestamp(),
                    }
                }
            },
        )


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

    parser.add_argument("--text", "-t", help="Text for post")

    parser.add_argument("--alts", "-a", action="store_true", help="Ask for alt text")

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
