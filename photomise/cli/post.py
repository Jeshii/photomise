import os
import plistlib
import random as rand
import sys
import xml.etree.ElementTree as ET
from enum import Enum
from xml.dom import minidom

import pendulum
import typer
from atproto import Client, models
from InquirerPy import inquirer

from photomise.database.shared import SharedDB
from photomise.utilities import logging
from photomise.utilities.photo import (
    Photo,
    extract_datetime,
    extract_exif_info,
    extract_gps,
    get_image_aspect_ratio,
)
from photomise.utilities.post import get_bluesky_user, get_password_from_keyring
from photomise.utilities.project import (
    convert_to_absolute_path,
    sanitize_text,
    set_project,
)

app = typer.Typer()

logger, console = logging.setup_logging()


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
        event_name = random_event.name
        logger.debug(f"[{project}] Random event chosen: {event_name}")

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
    event_to_post = events[event_name]
    if len(event_to_post.photos) > 4:
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
        photo_list = event_to_post.photos

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
            if not photo_entry:
                logger.debug(f"[{project}] Photo {path} not found in database")
                photo_entry = Photo(path, quality=pdb.settings.get("quality", 80))
            max_dimension = pdb.settings.get("max_dimension", 1200)
            if not photo_entry.description:
                photo_entry.description = f"{event_name}-{path}"
            try:
                compressed_image, e = photo_entry.compress_image(
                    project_path=main_path,
                    show=view,
                    max_dimension=max_dimension,
                )
                if not e:
                    images.append(compressed_image)
                    image_alts.append(photo_entry.description)
                    flavors.append(photo_entry.flavor)
                else:
                    logger.fatal(f"Error compressing image: {e}")
                    return
            except Exception as e:
                logger.fatal(f"Error compressing image: {e}")
                return

    if not text:
        flavor_text = "\n\n".join(filter(None, flavors))
        text = f"{event_to_post.location} ({pendulum.from_timestamp(event_to_post.date).format('YYYY-MMM-DD')})"
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
    project: str = typer.Argument(..., help="Project name or path"),
    output_path: str = typer.Option(..., "-o", "--output", prompt="Output path"),
    platform: SupportedProtocols = typer.Option(
        SupportedProtocols.atprotocol, "-p", "--protocol", case_sensitive=False
    ),
    schedule: str = typer.Option(
        ...,
        "-s",
        "--schedule",
        prompt="Cron-like schedule in mm hh format (e.g. '15 11,23')",
    ),
):
    """Export a plist file for use with launchd for scheduled posting."""

    try:
        gdb = SharedDB()
        projects = gdb.projects
        if project not in projects:
            logger.fatal(f"Project {project} not found in global database.")
            typer.Exit(1)

        project_path = projects[project]
    except ValueError:
        project_path = project
        if os.path.exists(project_path):
            logger.debug(f"Project path: {project_path}")
        else:
            logger.fatal(f"Project path {project_path} not found.")
            typer.Exit(1)
    except Exception as e:
        logger.fatal(f"Error: {e}")
        typer.Exit(1)

    log_dir = logging.get_log_dir()

    executable_path = sys.executable

    # Parse cron string
    try:
        minute, hours, *_ = schedule.split()
        calendar_intervals = []
        for hour in hours.split(","):
            calendar_intervals.append({"Hour": int(hour), "Minute": int(minute)})
    except ValueError as e:
        logger.fatal(f"Invalid cron string format: {e}")
        typer.Exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    plist_data = {
        "Label": f"click.blueribbon.photomise.{project}",
        "ProgramArguments": [
            "/bin/sh",
            "-c",
            f'"{executable_path}" "{script_dir}" post {platform.value} {project_path} -r',  # "{executable_path}" "{script_dir}" init {project} -p "{project_path}" &&
        ],
        "StartCalendarInterval": calendar_intervals,
        "StandardOutPath": f"{log_dir}/photomise-{project}.out",
        "StandardErrorPath": f"{log_dir}/photomise-{project}.err",
        "WorkingDirectory": project_path,
    }

    output_file_path = f"{output_path}/click.blueribbon.photomise.{project}.plist"

    with open(output_file_path, "wb") as plist_file:
        plistlib.dump(plist_data, plist_file)

    console.print(
        f"""Plist file exported to {output_path}.
Run [bold]launchctl load {output_file_path}[/bold] to schedule the task.
Run [bold]launchctl unload {output_file_path}[/bold] to remove the schedule.
Run [bold]launchctl list | grep {project}[/bold] to check the status of the scheduled task."""
    )


@app.command()
def gpx(
    project: str = typer.Argument(..., help="Project name or path"),
    event: str = typer.Option(None, "--event", "-e", help="Event name to export"),
    output: str = typer.Option(
        ".", "--output", "-o", help="Output GPX file or directory"
    ),
):
    """Export a GPX track for an event using photo timestamps and GPS data."""

    # Set project
    pdb, main_path = set_project(project)

    events = pdb.get_events()
    if not events:
        logger.fatal("No events found. Please run photomise first.")
        return

    if not event:
        event_name = inquirer.select(
            message="Choose an event to export", choices=events.keys()
        ).execute()
    else:
        event_name = event

    if event_name not in events:
        logger.fatal(f"Event {event_name} not found")
        return

    ev = events[event_name]

    # Collect photo GPS/timestamps
    trackpoints = []
    for rel_path in ev.photos:
        full_path = convert_to_absolute_path(rel_path, main_path)
        if not os.path.exists(full_path):
            logger.warning(f"Photo not found: {full_path}")
            continue
        try:
            tags = extract_exif_info(full_path)
            lat, lon = extract_gps(tags)
            dt = extract_datetime(tags)
            if lat is None or lon is None or dt is None:
                logger.debug(f"Skipping photo without GPS or timestamp: {full_path}")
                continue
            trackpoints.append((dt, lat, lon))
        except Exception as e:
            logger.warning(f"Error reading EXIF from {full_path}: {e}")

    if not trackpoints:
        logger.fatal("No usable photo GPS/timestamp data found for event.")
        return

    # Sort by time
    trackpoints.sort(key=lambda x: x[0])

    # Build GPX with a single track
    gpx = ET.Element("gpx", version="1.1", creator="photomise")
    trk = ET.SubElement(gpx, "trk")
    name_el = ET.SubElement(trk, "name")
    name_el.text = ev.name
    trkseg = ET.SubElement(trk, "trkseg")

    for dt, lat, lon in trackpoints:
        trkpt = ET.SubElement(trkseg, "trkpt", lat=str(lat), lon=str(lon))
        time_el = ET.SubElement(trkpt, "time")
        try:
            time_el.text = dt.to_iso8601_string()
        except Exception:
            time_el.text = str(dt)

    rough_string = ET.tostring(gpx, "utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty = reparsed.toprettyxml(indent="  ")

    if output.endswith(".gpx") or output.endswith(".GPX"):
        out_file = output
    else:
        out_file = (
            f"{output.rstrip('/')}/{pdb.project_name}-{sanitize_text(ev.name)}.gpx"
        )

    with open(out_file, "w", encoding="utf-8") as fh:
        fh.write(pretty)

    console.print(f"Exported {len(trackpoints)} trackpoints to {out_file}")
