import os
import random as rand

import pendulum
from atproto import Client, models
from InquirerPy import inquirer
from typer import Argument, Exit, Option, Typer

from photomise.utilities.exif import compress_image, get_image_aspect_ratio
from photomise.utilities.logging import setup_logging
from photomise.utilities.post import get_bluesky_user, get_password_from_keyring
from photomise.utilities.project import (
    convert_to_absolute_path,
    sanitize_text,
    set_project,
)

app = Typer()

logging, console = setup_logging()


@app.command()
def atprotocol(
    project: str = Argument(..., help="Project name"),
    user: str = Option(None, "--user", "-u", help="Bluesky username"),
    allow: bool = Option(False, "--allow", "-a", help="Allow previously posted events"),
    random: bool = Option(False, "--random", "-r", help="Choose a random event"),
    view: bool = Option(False, "--view", "-v", help="View images before posting"),
    text: str = Option(None, "--text", "-t", help="Text to post with images"),
    dryrun: bool = Option(False, "--dryrun", "-d", help="Dry run (no post)"),
):
    """
    Post photos to Bluesky using the atprotocol API.
    """

    # Project initialization
    pdb, main_path = set_project(project)
    client = Client()

    # Check flags
    if not user:
        user = get_bluesky_user(pdb)
        logging.debug(f"Bluesky user: {user}")

    events = pdb.get_events_without_bluesky_posted()
    logging.debug(f"Bluesky events not previously posted: {events}")
    if allow or not events:
        events = pdb.get_events()

    if not events:
        logging.fatal("No events found. Please run photomise first.")
        return

    if not random:
        event_name = inquirer.select(
            message="Choose an event to post", choices=events.keys()
        ).execute()
    else:
        random_event = rand.choice(list(events.values()))
        event_name = random_event["event"]

    password = get_password_from_keyring(logging, user)
    try:
        client.login(user, password)
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
    photo_list = []
    logging.debug(f"Checking for photos in: {events[event_name]}")
    if len(events[event_name]["photos"]) > 4:
        ranking = pdb.get_rankings_by_event(event_name)
        if not ranking:
            logging.fatal("Too many photos to post to Bluesky")
            Exit(1)
        else:
            logging.warning("Too many photos to post to Bluesky, only posting top 4")
        for rank in ranking:
            photo_list.append(rank["path"])
            if len(photo_list) >= 4:
                break
    else:
        photo_list = events[event_name]["photos"]

    for path in photo_list:
        full_path = convert_to_absolute_path(path, main_path)
        if os.path.exists(full_path):
            logging.debug(f"Processing {full_path}")
            height, width = get_image_aspect_ratio(full_path)
            logging.debug(f"Height: {height}, Width: {width}")
            if not height or not width:
                height = 1
                width = 1
            image_aspect_ratios.append(
                models.AppBskyEmbedDefs.AspectRatio(height=height, width=width)
            )

            photo_entry = pdb.get_photo(path)
            if photo_entry:
                rotation_angle = photo_entry.get("rotation", 0)
                quality = photo_entry.get("quality", pdb.settings.get("quality", 80))
                description = photo_entry.get("description", f"{event_name}-{path}")
                flavor = photo_entry.get("flavor", "")
                max_dimension = photo_entry.get(
                    "max_dimension", pdb.settings.get("max_dimension", 1200)
                )
            else:
                rotation_angle = 0
                quality = pdb.settings.get("quality", 80)
                description = ""
                max_dimension = pdb.settings.get("max_dimension", 1200)
            try:
                compressed_image = compress_image(
                    full_path,
                    rotation_angle=rotation_angle,
                    quality=quality,
                    show=view,
                    max_dimension=max_dimension,
                )

                images.append(compressed_image)
                image_alts.append(description)
                flavors.append(flavor)
            except Exception as e:
                logging.fatal(f"Error compressing image: {e}")
                return

    if not text:
        flavor_text = "\n\n".join(filter(None, flavors))
        text = f"{events[event_name]['location']} ({pendulum.from_timestamp(events[event_name]['date']).format('YYYY-MMM-DD')})"
        if flavor_text:
            text = f"{text}\n\n{flavor_text}"

    if images:
        try:
            if not dryrun:
                response = client.send_images(
                    text=text,
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

                if not dryrun:
                    pdb.set_post(
                        event_name=event_name,
                        user=sanitize_text(user),
                        platform="Bluesky",
                        uri=(response.uri if hasattr(response, "uri") else None),
                    )
            except Exception as e:
                logging.error(f"Error adding post to database: {e}")
        else:
            logging.error("No response from server")
    else:
        logging.error("No images to upload")
