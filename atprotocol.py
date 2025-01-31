#!/usr/bin/env python3

import argparse
from tinydb import TinyDB, where
import pendulum
from InquirerPy import inquirer
from atproto import Client, models
import keyring
import logging
import photomise as base
import configparser
import random
import getpass
import os

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


def get_bluesky_user(accounts_table: TinyDB):
    try:
        user = accounts_table.get(where("where") == "Bluesky")["user"]
        return user
    except TypeError:
        user = inquirer.text(message="Enter your Bluesky username").execute()
        accounts_table.insert({"where": "Bluesky", "user": user})
        return user


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
    level = getattr(logging, args.log.upper())
    logging.basicConfig(level=level)
    logger = logging.getLogger(__name__)

    # Project initialization
    projects_db, main_path, settings = base.set_project(logger, config, args)
    event_table = base.get_events_table(projects_db)
    posts_table = base.get_posts_table(projects_db)
    photos_table = base.get_photos_table(projects_db)
    accounts_table = base.get_accounts_table(projects_db)
    client = Client()

    # Check flags
    if not args.user:
        args.user = get_bluesky_user(accounts_table)
        logger.debug(f"User: {args.user}")

    events = get_events_without_bluesky_posted(
        post_db=posts_table, event_db=event_table
    )
    logger.debug(f"Events: {events}")
    if args.allow or not events:
        events = base.get_all_events(event_table)

    if not events:
        logging.fatal("No events found. Please run photomise first.")
        return

    if not args.random:
        event_name = inquirer.select(
            message="Choose an event to post", choices=events.keys()
        ).execute()
    else:
        random_event = random.choice(list(events.values()))
        event_name = random_event["event"]

    password = get_password_from_keyring(logger, args.user)
    try:
        client.login(args.user, password)
        if not client.me:
            logging.fatal(f"Login failed: {client.error}")
            return
    except Exception as e:
        logging.fatal(f"Login failed: {e}")
        return

    image_alts = []
    images = []
    flavors = []
    image_aspect_ratios = []
    logging.debug(f"Checking for photos in: {events[event_name]}")
    for path in events[event_name]["photos"]:
        full_path = base.convert_to_absolute_path(path, main_path)
        if os.path.exists(full_path):
            logging.debug(f"Processing {full_path}")
            height, width = base.get_image_aspect_ratio(full_path)
            logging.debug(f"Height: {height}, Width: {width}")
            if not height or not width:
                height = 1
                width = 1
            image_aspect_ratios.append(
                models.AppBskyEmbedDefs.AspectRatio(height=height, width=width)
            )

            photo_entry = photos_table.get(where("path") == path)
            if photo_entry:
                rotation_angle = photo_entry.get("rotation", 0)
                quality = photo_entry.get("quality", 80)
                description = photo_entry.get("description", "")
                flavor = photo_entry.get("flavor", "")
                max_dimension = photo_entry.get(
                    "max_dimension", settings.get("max_dimension", 1200)
                )
            else:
                rotation_angle = 0
                quality = settings.get("quality", settings.get("quality", 80))
                description = ""
                max_dimension = settings.get("max_dimension", 1200)
            try:
                compressed_image = base.compress_image(
                    full_path,
                    rotation_angle=rotation_angle,
                    quality=quality,
                    show=args.view,
                    max_dimension=max_dimension,
                )

                images.append(compressed_image)
                image_alts.append(description)
                flavors.append(flavor)
            except Exception as e:
                logging.fatal(f"Error compressing image: {e}")
                return

    if not args.text:
        args.text = f"{events[event_name]['location']} ({pendulum.from_timestamp(events[event_name]['date']).format('YYYY-MMM-DD')}){'\n\n'.join(flavors)}"

    if images:
        try:
            response = client.send_images(
                text=args.text,
                images=images,
                image_alts=image_alts,
                image_aspect_ratios=image_aspect_ratios,
            )
        except Exception as e:
            logging.fatal(f"Upload failed: {e}")
            return

        if response:
            try:
                logging.debug(f"Response: {response}")
                post_uri = response.uri if hasattr(response, "uri") else None
                post_uri_parts = post_uri.split("/")
                post_url = (
                    f"https://bsky.app/profile/{args.user}/post/{post_uri_parts[-1]}"
                )
                base.update_event_posted(
                    posts_table, event_name, args.user, "Bluesky", post_uri, post_url
                )
            except Exception as e:
                logging.error(f"Error adding post to database: {e}")
        else:
            logging.error("No response from server")
    else:
        logging.error("No images to upload")

    base.make_json_readable(f"{main_path}/db/{args.project}.json")


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
