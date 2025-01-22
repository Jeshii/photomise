#!/usr/bin/env python3

import argparse
from tinydb import TinyDB, where
import pendulum
from InquirerPy import inquirer
from rich.console import Console
from atproto import Client, models
import keyring
import logging
import photomise as base
import configparser
import random
import os
import getpass

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


def get_events_without_bluesky_posted(post_db: TinyDB, event_db: TinyDB):
    events = {}
    posted_events = []
    for post in post_db.all():
        if post["where"] == "Bluesky":
            posted_events.append(post["event"])
    for event in event_db.all():
        if event["event"] not in posted_events:
            events[event["event"]] = event
    return events


def main(args):
    # Basic initialization
    config = configparser.ConfigParser()
    console = Console()
    level = getattr(logging, args.log.upper())
    logging.basicConfig(level=level)
    logger = logging.getLogger(__name__)

    # Project initialization
    projects_db, _ = base.set_project(console, config, args)
    event_table = base.get_events_table(projects_db)
    posts_table = base.get_posts_table(projects_db)
    photos_table = base.get_photos_table(projects_db)
    client = Client()

    # Check flags
    if not args.user:
        args.user = get_bluesky_user(config)

    events = get_events_without_bluesky_posted(
        post_db=posts_table, event_db=event_table
    )
    logger.debug(f"Events: {events}")
    if args.posted or not events:
        events = base.get_all_events(event_table)

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

        height, width = base.get_image_aspect_ratio(path)
        if not height or not width:
            height = 1
            width = 1
        image_aspect_ratios.append(
            models.AppBskyEmbedDefs.AspectRatio(height=height, width=width)
        )

        if path in photos_table.query(where("path") == path):
            rotation_angle = photos_table.get(where("path") == path)["rotate"]
            quality = photos_table.get(where("path") == path)["quality"]
        else:
            rotation_angle = 0
            quality = 85
        while True:
            compressed_image = base.compress_image(
                path,
                rotation_angle=rotation_angle,
                quality=quality,
                show=args.view,
            )
            if (
                not args.preview
                or inquirer.confirm(message="Does the image look okay?").execute()
            ):
                images.append(compressed_image)
                break
            else:
                quality = inquirer.select(
                    message="Choose a quality level",
                    choices=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
                ).execute()

                rotation_angle = inquirer.select(
                    message="Choose a rotation angle",
                    choices=[0, 90, 180, 270],
                ).execute()

                photos_table.insert(
                    {
                        "path": path,
                        "rotation": rotation_angle,
                        "quality": quality,
                    }
                )

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

        base.update_event_posted(posts_table, event_name, args.user, "Bluesky")


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

    parser.add_argument(
        "--random",
        "-r",
        action="store_true",
        help="Post a random photo",
    )

    parser.add_argument(
        "--allow",
        "-a",
        action="store_true",
        help="Allow previously posted events",
    )

    parser.add_argument(
        "--log",
        help="Set logging level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    parser.add_argument(
        "--view",
        "-v",
        action="store_true",
        help="View the image while processing",
    )

    parser.add_argument(
        "--project",
        "-p",
        help="Provide the name of the project to use",
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
