import configparser
import os
import plistlib
import random as rand
import sys
from enum import Enum

import pendulum
import typer
from atproto import Client, models
from InquirerPy import inquirer

from photomise.utilities import logging
from photomise.utilities.constants import CONFIG_FILE
from photomise.utilities.exif import compress_image, get_image_aspect_ratio
from photomise.utilities.post import get_bluesky_user, get_password_from_keyring
from photomise.utilities.project import (
    convert_to_absolute_path,
    sanitize_text,
    set_project,
)

app = typer.Typer()

logger, console = logging.setup_logging()
config = configparser.ConfigParser()


@app.command()
def atprotocol(
    project: str = typer.Argument(..., help="Project name"),
    user: str = typer.Option(None, "--user", "-u", help="Bluesky username"),
    allow: bool = typer.Option(
        False, "--allow", "-a", help="Allow previously posted events"
    ),
    random: bool = typer.Option(False, "--random", "-r", help="Choose a random event"),
    view: bool = typer.Option(False, "--view", "-v", help="View images before posting"),
    text: str = typer.Option(None, "--text", "-t", help="Text to post with images"),
    dryrun: bool = typer.Option(False, "--dryrun", "-d", help="Dry run (no post)"),
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
        logger.debug(f"Bluesky user: {user}")

    events = pdb.get_events_without_bluesky_posted()
    logger.debug(f"Bluesky events not previously posted: {events}")
    if allow or not events:
        events = pdb.get_events()

    if not events:
        logger.fatal("No events found. Please run photomise first.")
        return

    if not random:
        event_name = inquirer.select(
            message="Choose an event to post", choices=events.keys()
        ).execute()
    else:
        random_event = rand.choice(list(events.values()))
        event_name = random_event["event"]

    password = get_password_from_keyring(logger, user)
    try:
        client.login(user, password)
        if not client.me:
            logger.fatal(f"Login failed: {client.error}")
            return
    except Exception as e:
        logger.fatal(f"Login failed: {e}")
        return

    image_alts = []
    images = []
    flavors = []
    image_aspect_ratios = []
    photo_list = []
    logger.debug(f"Checking for photos in: {events[event_name]}")
    if len(events[event_name]["photos"]) > 4:
        ranking = pdb.get_rankings_by_event(event_name)
        if not ranking:
            logger.fatal("Too many photos to post to Bluesky")
            typer.Exit(1)
        else:
            logger.warning("Too many photos to post to Bluesky, only posting top 4")
        for rank in ranking:
            photo_list.append(rank["path"])
            if len(photo_list) >= 4:
                break
    else:
        photo_list = events[event_name]["photos"]

    for path in photo_list:
        full_path = convert_to_absolute_path(path, main_path)
        if os.path.exists(full_path):
            logger.debug(f"Processing {full_path}")
            height, width = get_image_aspect_ratio(full_path)
            logger.debug(f"Height: {height}, Width: {width}")
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
                logger.fatal(f"Error compressing image: {e}")
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
            logger.fatal(f"Upload failed: {e}")
            return

        if response:
            try:
                logger.debug(f"Response: {response}")

                if not dryrun:
                    pdb.set_post(
                        event_name=event_name,
                        user=sanitize_text(user),
                        platform="Bluesky",
                        uri=(response.uri if hasattr(response, "uri") else None),
                    )
            except Exception as e:
                logger.error(f"Error adding post to database: {e}")
        else:
            logger.error("No response from server")
    else:
        logger.error("No images to upload")


class SupportedProtocols(str, Enum):
    atprotocol = "atprotocol"


@app.command()
def plist(
    project: str = typer.Argument(..., help="Project name"),
    output_path: str = typer.Option(..., "-o","--output", prompt="Output path"),
    platform: SupportedProtocols = typer.Option(SupportedProtocols.atprotocol, "-p","--protocol",case_sensitive=False),
    schedule: str = typer.Option("15 11,23", "-s","--schedule",help="Cron-lik schedule in mm hh format (e.g. '15 11,23')"),
):
    """Export project configuration to a plist file."""
    if not os.path.exists(CONFIG_FILE):
        logger.fatal("Config file not found.")
        typer.Exit(1)

    config.read(CONFIG_FILE)
    if not config.has_section("Projects"):
        logger.fatal("No projects found in config file.")
        typer.Exit(1)

    projects = dict(config.items("Projects"))
    if project not in projects:
        logger.fatal(f"Project {project} not found in config file.")
        typer.Exit(1)

    log_dir = logging.get_log_dir()
    project_path = projects[project]
    executable_path = sys.executable

    # Parse cron string
    try:
        minute, hours, *_ = schedule.split()
        calendar_intervals = []
        for hour in hours.split(','):
            calendar_intervals.append({
                "Hour": int(hour),
                "Minute": int(minute)
            })
    except ValueError as e:
        logger.fatal(f"Invalid cron string format: {e}")
        typer.Exit(1)

    plist_data = {
        "Label": f"click.blueribbon.{project}",
        "ProgramArguments": [
            "/bin/sh",
            "-c",
            f'{executable_path} photomise init {project} -p "{project_path}" && {executable_path} photomise post {platform} {project} -r',
        ],
        "StartCalendarInterval": calendar_intervals,
        "StandardOutPath": f"{log_dir}/photomise.out",
        "StandardErrorPath": f"{log_dir}/photomise.err",
        "WorkingDirectory": project_path,
    }

    output_file_path = f"{output_path}/click.blueribbon.photomise.{project}.plist"

    with open(output_file_path, "wb") as plist_file:
        plistlib.dump(plist_data, plist_file)

    logger.info(f"Plist file exported to {output_path}")
