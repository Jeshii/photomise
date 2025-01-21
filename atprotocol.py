#!/usr/bin/env python3

import argparse
from tinydb import TinyDB, Query
import pendulum
from InquirerPy import inquirer
from rich.console import Console
from atproto import Client, models
import keyring
import logging
import piexif
import photomise as base
import configparser
import random
import os
import getpass
from PIL import Image
from io import BytesIO

SERVICE_NAME = "photomise-atprotocol-bluesky"


def get_password_from_keyring(logger, user: str):
    logger.debug(f"Attempting to get password for {user}...")
    password = keyring.get_password(SERVICE_NAME, user)
    if password:
        return password

    logger.debug("Unable to get password...")
    password = getpass.getpass("Enter password: ")
    keyring.set_password(SERVICE_NAME, user, password)
    return password


def get_image_aspect_ratio(image_path: str) -> tuple:
    try:
        exif_dict = piexif.load(image_path)
        image_width = exif_dict["0th"][piexif.ImageIFD.ImageWidth]
        image_height = exif_dict["0th"][piexif.ImageIFD.ImageLength]
        return (image_width, image_height)
    except (piexif.InvalidImageDataError, KeyError, TypeError):
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                return (width, height)
        except (OSError, IOError):
            return None


def get_bluesky_user(config):
    try:
        user = config.get("Accounts", "bluesky")
        return user
    except (configparser.NoSectionError, configparser.NoOptionError, AttributeError):
        if os.path.exists(base.CONFIG_FILE):
            config.read(base.CONFIG_FILE)
            username = inquirer.text(message="Enter your Bluesky username").execute()
            config["Accounts"]["bluesky"] = username
            with open(base.CONFIG_FILE, "w") as configfile:
                config.write(configfile)
            return username
        else:
            return None


def fix_bluesky(current):
    return current.replace("@", "").strip()


def get_events_without_bluesky_posted(db):
    events = {}
    PostedEvent = Query()
    for doc in db.search(PostedEvent.where != "Bluesky"):
        events[doc["event"]] = doc
    return events


def compress_image(image_path, quality=85, max_dimension=1200):
    try:
        image = Image.open(image_path)
        img_io = BytesIO()
        width, height = image.size

        if width > max_dimension or height > max_dimension:
            if width > height:
                scale_factor = max_dimension / width
            else:
                scale_factor = max_dimension / height

            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            resized_image = image.resize((new_width, new_height), Image.LANCZOS)

            resized_image.save(img_io, format="JPEG", optimize=True, quality=quality)
        else:
            image.save(img_io, format="JPEG", optimize=True, quality=quality)
        img_io.seek(0)

        return img_io
    except Exception as e:
        print(f"Error compressing image: {e}")


def update_event_posted(db, event_name, user, platform):
    db.insert(
        {
            "event_name": event_name,
            "where": platform,
            "account": base.santitize_text(user),
            "date": pendulum.now().timestamp(),
        }
    )


def get_post_db(database_dir: str) -> TinyDB:
    return TinyDB(f"{database_dir}/posts.json")


def main(args):
    config = configparser.ConfigParser()
    console = Console()
    config = base.get_config(config)
    event_db = base.get_event_db(config["Paths"]["database_dir"])
    post_db = get_post_db(config["Paths"]["database_dir"])
    level = getattr(logging, args.log.upper())
    logging.basicConfig(level=level)
    logger = logging.getLogger(__name__)
    client = Client()

    if not args.user:
        args.user = get_bluesky_user(config)

    events = get_events_without_bluesky_posted(post_db)
    if args.posted or not events:
        events = base.get_all_events(event_db)

    if not events:
        console.print("[bold red]No events found. Please run photomise first!")
        return

    if not args.random:
        event_name = inquirer.select(
            message="Choose an event to post", choices=events.keys()
        ).execute()
    else:
        random_event = random.choice(events)
        event_name = random_event["event"]

    if not args.text:
        default_text = f"{events[event_name]["location"]} ({pendulum.from_timestamp(events[event_name]["date"]).format("YYYY-MMM-DD")})"
        args.text = inquirer.text(
            message="Enter the text for the post", default=default_text
        ).execute()

    password = get_password_from_keyring(logger, args.user)
    client.login(args.user, password)

    image_alts = []
    images = []
    image_aspect_ratios = []
    for path in events[event_name]["photos"]:

        height, width = get_image_aspect_ratio(path)
        if not height or not width:
            height = 1
            width = 1
        image_aspect_ratios.append(
            models.AppBskyEmbedDefs.AspectRatio(height=height, width=width)
        )

        images.append(compress_image(path))

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

        update_event_posted(post_db, event_name, args.user, "Bluesky")


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

    parser.add_argument(
        "--posted",
        "-p",
        action="store_true",
        help="Show previously posted events",
    )

    parser.add_argument(
        "--log",
        help="Set logging level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
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
