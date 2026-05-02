#!/usr/bin/env python3

import logging
import os
import time

import pendulum
import piexif
import typer
from typer import prompt, confirm
from InquirerPy import inquirer
from rich.progress import Progress

from photomise.database.shared import SharedDB
from photomise.utilities.event import Event
from photomise.utilities.location import Location
from photomise.utilities.logging import setup_logging
from photomise.utilities.photo import (
    Photo,
    convert_to_degrees,
    deg_to_dms_rational,
    extract_datetime,
    extract_exif_info,
    extract_gps,
)
from photomise.utilities.project import (
    convert_to_absolute_path,
    convert_to_relative_path,
    get_non_hidden_files,
    handle_duplicate_events,
    item_duplicate,
    set_project,
)
from photomise.utilities.shared import make_min_max_prompt

app = typer.Typer()
logger = setup_logging()


@app.command()
def images(
    project: str = typer.Argument(..., help="Project name"),
    view: bool = typer.Option(
        False, "--view", "-v", help="View files during processing"
    ),
    all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Process and view all files whether they've been processed previously or not",
    ),
    file: str = typer.Option(
        None,
        "--file",
        "-f",
        help="Process a specific file",
    ),
):
    """Process image by rotating, scaling, changing quality, or apply filters."""

    # Project initialization
    pdb, main_path = set_project(project)
    logging.debug(f"Project: {project}, Path: {main_path}, Settings: {pdb.settings}")
    gdb = SharedDB()
    photos_path = f"{main_path}/assets"

    if file:
        non_hidden_files = [
            (
                os.path.dirname(f"{photos_path}/{file}"),
                os.path.basename(f"{photos_path}/{file}"),
            )
        ]
    else:
        non_hidden_files = list(get_non_hidden_files(photos_path))

    if non_hidden_files == [(None, None)]:
        logging.fatal(
            "No files found in the project folder's assets directory, please add photos before running."
        )
        typer.Exit(1)

    logger.info(f"Found {len(non_hidden_files)} files in {photos_path} to process.")

    progress = Progress(
        "[progress.description]{task.description}",
        "[progress.bar]{task.completed}/{task.total}",
        transient=False,
    )
    progress.start()
    task = progress.add_task(
        description="Processing images...", total=len(non_hidden_files)
    )
    for dir, file in non_hidden_files:
        error = None
        file_path = f"{dir}/{file}"
        progress.update(task, advance=1)
        progress.update(task, description=f"Processing [bold]{file_path}")
        relative_path = convert_to_relative_path(file_path, main_path)

        photo_record = pdb.get_photo(relative_path)

        logger.debug(f"[{project}] Photo Record: {photo_record}")
        logger.debug(f"[{project}] View flag: {view}")
        logger.debug(f"[{project}] All flag: {all}")
        if not photo_record:
            photo_record = Photo(
                path=file_path, quality=pdb.settings.get("quality", 80)
            )

        if all or (
            (
                not photo_record.has_modifications(
                    default_quality=pdb.settings.get("quality", 80),
                )
                or len(non_hidden_files) == 1
            )
            and view
        ):
            while True:
                try:
                    result, error = photo_record.compress_image(
                        show=True,
                        project_path=main_path,
                    )
                    if error is not None or not result:
                        logging.error(f"Error: {error}")
                        break
                except Exception as e:
                    logging.error(f"Error: {e}")
                    error = e
                    break
                progress.stop()
                if confirm(message="Does the image look okay?"):
                    progress.start()
                    break
                else:
                    photo_record.quality = inquirer.select(
                        message="Choose a quality level",
                        choices=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
                        default=photo_record.quality,
                    ).execute()

                    photo_record.rotation = inquirer.select(
                        message="Choose a rotation angle",
                        choices=[0, 90, 180, 270],
                        default=photo_record.rotation,
                    ).execute()

                    filter_choices = ["None"] + [
                        filter["name"] for filter in gdb.get_filters_all()
                    ]
                    filter_choices.append("Custom")

                    filter_search_params = {
                        "brightness": photo_record.brightness,
                        "contrast": photo_record.contrast,
                        "color": photo_record.color,
                        "sharpness": photo_record.sharpness,
                    }

                    filter_to_apply = inquirer.select(
                        message="Choose a filter",
                        choices=filter_choices,
                        default=gdb.get_filter_from_values(filter_search_params),
                    ).execute()

                    match filter_to_apply:
                        case "Custom":
                            photo_record.brightness = make_min_max_prompt(
                                "Adjust brightness",
                                photo_record.brightness,
                            )
                            photo_record.contrast = make_min_max_prompt(
                                "Adjust contrast",
                                photo_record.contrast,
                            )
                            photo_record.color = make_min_max_prompt(
                                "Adjust color",
                                photo_record.color,
                            )
                            photo_record.sharpness = make_min_max_prompt(
                                "Adjust sharpness",
                                photo_record.sharpness,
                            )
                        case "None":
                            photo_record.brightness = 1.0
                            photo_record.contrast = 1.0
                            photo_record.color = 1.0
                            photo_record.sharpness = 1.0
                        case _:
                            filter = gdb.get_filter(filter_to_apply)
                            photo_record.brightness = filter.get("brightness", 1.0)
                            photo_record.contrast = filter.get("contrast", 1.0)
                            photo_record.color = filter.get("color", 1.0)
                            photo_record.sharpness = filter.get("sharpness", 1.0)
                progress.start()
                logger.debug(f"[{project}] Photo info: {photo_record}")

        if error:
            progress.start()
            progress.update(task, description=f"Error processing [bold]{file_path}")
            logger.error(f"Error processing {file_path}: {error}")
            time.sleep(5)
            continue

        default_description = photo_record.description
        default_flavor = photo_record.flavor

        if pdb.settings.get("description") and (not default_description or all):
            progress.stop()
            description = inquirer.text(
                message="Enter alt text describing this image:",
                default="" if default_description is None else str(default_description),
            ).execute()

            progress.start()
            photo_record.description = description

        if pdb.settings.get("flavor") and (not default_flavor or all):
            progress.stop()
            flavor = inquirer.text(
                message="Enter flavor text for this image:",
                default="" if default_flavor is None else str(default_flavor),
            ).execute()

            progress.start()
            photo_record.flavor = flavor

        photo_record.path = relative_path

        progress.update(task, description=f"Saving [bold]{file_path}")
        logger.debug(f"[{project}] Saving photo record: {photo_record}")
        updated = pdb.upsert_photo(photo_record)

        progress.update(task, description=f"Saved [bold]{file_path}")
        logging.debug(f"[{project}] Photo info saved: {updated}")

    progress.stop()
    pdb.close()
    gdb.close()


@app.command()
def locations(
    project: str = typer.Argument(..., help="Project name"),
    link: str = typer.Option(
        None,
        "--link",
        "-l",
        help="Helper link to append to latitude and longitude to help find location",
    ),
    view: bool = typer.Option(
        False, "--view", "-v", help="View files before processing"
    ),
):
    """Associate photos with an event by location."""

    # Project initialization
    pdb, main_path = set_project(project)
    logging.debug(f"Project: {project}, Path: {main_path}, Settings: {pdb.settings}")
    try:
        gdb = SharedDB()
    except Exception as e:
        logging.fatal(f"Error: {e}")
        typer.Exit(1)
    photos_path = f"{main_path}/assets"

    non_hidden_files = list(get_non_hidden_files(photos_path))

    if non_hidden_files == [(None, None)]:
        logging.fatal(
            f"No files found in the project folder's photos directory ({photos_path}), please add photos before running."
        )
        typer.Exit(1)

    for dir, file in get_non_hidden_files(photos_path):
        date_object = None
        lat = None
        lon = None
        file_path = f"{dir}/{file}"
        relative_path = convert_to_relative_path(file_path, main_path)

        logger.info("")
        logger.info(f"Checking {file_path}")

        # Check for duplicates
        duplicate_events = pdb.find_events_with_photo(relative_path)
        if len(duplicate_events) > 1:
            handle_duplicate_events(pdb, duplicate_events, relative_path)

        try:
            exif_tags = extract_exif_info(file_path)

            lat, lon = extract_gps(exif_tags)

            date_object = extract_datetime(exif_tags)
        except piexif.InvalidImageDataError:
            logger.warning(f"Invalid image data in file: {file_path}")
            continue
        except Exception as e:
            logger.error(f"Error extracting exif info: {e}")

        photo_record = pdb.get_photo(relative_path)

        if view:
            _ = photo_record.compress_image(
                show=True,
                project_path=main_path,
            )

        if not date_object:
            if confirm("No date found in EXIF data. Would you like to add one?"):
                entered_date = prompt("Please enter a date for this photo")
                if entered_date:
                    date_object = pendulum.parse(entered_date, strict=False)
                    if confirm(
                        f"Save {date_object.format('YYYY-MM-DD HH:mm:ss')} to the exif data?"
                    ):
                        # Save to exif data
                        exif_dict = piexif.load(file_path)
                        exif_dict["Exif"] = {
                            piexif.ExifIFD.DateTimeOriginal: date_object.format(
                                "YYYY:MM:DD HH:mm:ss"
                            )
                        }
                        exif_bytes = piexif.dump(exif_dict)
                        piexif.insert(exif_bytes, file_path)
                        logger.info("Date saved to exif data.")
                    else:
                        logger.info("Only using for location finding...")
                else:
                    logger.info("Skipping...")

        if not date_object:
            logging.warning("No date found for this photo. Skipping...")
            continue

        if lat and lon:
            # Prefer per-project radius (portable). Fall back to shared DB if missing.
            proj_settings = pdb.settings or {}
            event_radius_meters = proj_settings.get("event_radius_meters")
            radius_source = "project"
            if event_radius_meters is None:
                try:
                    shared_proj = gdb.get_project(pdb.project_name)
                    event_radius_meters = (
                        shared_proj.get("event_radius_meters") if shared_proj else 500
                    )
                    radius_source = "shared"
                except Exception:
                    event_radius_meters = 500
                    radius_source = "default"
            event_radius_km = event_radius_meters / 1000.0
            logger.debug(
                f"Using event_radius_meters={event_radius_meters} (source={radius_source})"
            )
            location = gdb.find_location(lat, lon, max_distance_km=event_radius_km)
            if location:
                logger.info(f"Location Name: {location.name}")
                logger.info(f"Photo Geodata: Latitude: {lat}, Longitude: {lon}")
                logger.info(
                    f"Location Geodata: Latitude: {location.latitude}, Longitude: {location.longitude}"
                )
            else:
                if link:
                    from urllib.parse import quote

                    encoded_lat = quote(str(lat))
                    encoded_lon = quote(str(lon))
                    from photomise.utilities.logging import log_link

                    log_link(logger, f"{link}{encoded_lat},{encoded_lon}")
                location_name = inquirer.text(
                    f"Please enter a location name for {lat},{lon}",
                    validate=lambda x: len(x.strip()) > 0,
                    invalid_message="Location name cannot be empty",
                ).execute()
                location = Location(latitude=lat, longitude=lon)
                location.name = location_name
                result = gdb.upsert_location(location)
                logger.info(f"Location upserted: {result}")
        else:
            if confirm("No GPS info found - would you like to add some?"):
                lat = prompt("Latitude")
                try:
                    if "°" in lat or "S" in lat or "N" in lat:
                        if "S" in lat:
                            lat = -convert_to_degrees(lat)
                        else:
                            lat = convert_to_degrees(lat)
                    else:
                        lat = float(lat)
                except ValueError:
                    logger.warning("Invalid latitude format.")
                    continue

                lon = prompt("Longitude")
                try:
                    if "°" in lon or "W" in lon or "E" in lon:
                        if "W" in lon:
                            lon = -convert_to_degrees(lon)
                        lon = convert_to_degrees(lon)
                    else:
                        lon = float(lon)
                except ValueError:
                    logger.warning("Invalid longitude format.")
                    continue

                proj_settings = pdb.settings or {}
                event_radius_meters = proj_settings.get("event_radius_meters")
                radius_source = "project"
                if event_radius_meters is None:
                    try:
                        shared_proj = gdb.get_project(pdb.project_name)
                        event_radius_meters = (
                            shared_proj.get("event_radius_meters")
                            if shared_proj
                            else 500
                        )
                        radius_source = "shared"
                    except Exception:
                        event_radius_meters = 500
                        radius_source = "default"
                event_radius_km = event_radius_meters / 1000.0
                logger.info(
                    f"Using event_radius_meters={event_radius_meters} (source={radius_source})"
                )
                location = gdb.find_location(lat, lon, max_distance_km=event_radius_km)
                if location:
                    logger.info(f"Location: {location.name}")
                else:
                    if link:
                        from photomise.utilities.logging import log_link

                        log_link(logger, f"{link}{lat},{lon}")
                    location = Location(
                        latitude=lat,
                        longitude=lon,
                    )
                    location_name = inquirer.text(
                        f"Please enter a location name for {lat},{lon}",
                        validate=lambda x: len(x.strip()) > 0,
                        invalid_message="Location name cannot be empty",
                    ).execute()
                    location.name = location_name
                    result = gdb.upsert_location(location)
                    logger.info(f"Location upserted: {result}")
                # add exif info to file
                exif_dict = piexif.load(file_path)
                exif_dict["GPS"] = {
                    piexif.GPSIFD.GPSLatitude: deg_to_dms_rational(lat),
                    piexif.GPSIFD.GPSLatitudeRef: b"N" if lat > 0 else b"S",
                    piexif.GPSIFD.GPSLongitude: deg_to_dms_rational(lon),
                    piexif.GPSIFD.GPSLongitudeRef: b"E" if lon > 0 else b"W",
                }
                exif_bytes = piexif.dump(exif_dict)
                piexif.insert(exif_bytes, file_path)
            else:
                logger.info("Skipping...")
                continue

        logger.info(f"Taken: {date_object.format('YYYY-MM-DD HH:mm:ss')}")
        event, event_same = pdb.same_event(date_object, location)
        logger.debug(f"[{project}] Event: {event}")
        logger.debug(f"[{project}] Event Same? {event_same}")
        if not event_same:
            event = Event(
                date=date_object.timestamp(),
            )

        if item_duplicate(pdb, gdb, date_object, lat, lon):
            logging.info(f"[{project}] Skipping duplicate: {date_object}")
            logger.info("This item appears to be a duplicate and will be skipped.")
            continue

        if not event_same:
            if pdb.settings.get("auto_event"):
                event_name_date = (
                    pendulum.from_timestamp(event.date)
                    .in_tz(pendulum.local_timezone())
                    .format("YYYYMMDD")
                )
                event.name = f"{event_name_date}-{location._name}"
            else:
                event_name_date = (
                    pendulum.from_timestamp(event.date)
                    .in_tz(pendulum.local_timezone())
                    .format("YYYYMMDD")
                )
                event.name = inquirer.text(
                    f"Please name this event from {event_name_date} at {location.name}"
                ).execute()

        if event_same:
            logging.info(f"This event appears to be {event.name}.")
            event = pdb.get_event(event.name)
            logging.debug(f"Event: {event}")
            if relative_path not in event.photos:
                pdb.upsert_event(event, relative_path)
            else:
                logger.info("This photo has already been added to this event.")
        else:
            event.photos = [relative_path]
            event.longitude = lon
            event.latitude = lat
            event.location = location.name
            event.date = date_object.timestamp()
            pdb.upsert_event(event)

    pdb.close()
    gdb.close()


@app.command()
def rank(
    project: str = typer.Argument(..., help="Project name"),
    view: bool = typer.Option(
        False, "--view", "-v", help="View files before processing"
    ),
    event_name: str = typer.Option(None, "--event", "-e", help="Event name"),
    all: bool = typer.Option(False, "--all", "-a", help="Rank all photos"),
    greater_than: int = typer.Option(
        0,
        "--greater",
        "-g",
        help="Only rank events with more than this number of photos",
    ),
    unranked: bool = typer.Option(
        False, "--unranked", "-u", help="Rank only unranked photos"
    ),
):
    """Rank files in order of preference for socials that only allow a certain number of attachments."""

    # Project initialization
    pdb, main_path = set_project(project)
    logging.debug(f"Project: {project}, Path: {main_path}, Settings: {pdb.settings}")
    events = pdb.get_events()
    if all:
        if not events:
            logging.fatal("No events found. Please run photomise first.")
            typer.Exit(1)
    else:
        if not event_name:
            event_name = inquirer.select(
                message="Choose an event to rank", choices=events.keys()
            ).execute()
        events = pdb.get_events(event_name)

    logging.debug(f"[{project}] Events: {events}")
    for event_name, event in events.items():
        logging.debug(f"[{project}] Event: {event}")
        try:
            photos = event.photos
        except KeyError:
            logging.fatal("Event not found.")
            typer.Exit(1)
        if len(photos) <= greater_than:
            continue
        logger.info(f"There are {len(photos)} photos in {event_name}.")
        if view:
            for photo_path in photos:
                photo_record = pdb.get_photo(photo_path)
                photo_record.compress_image(
                    project_path=main_path,
                    show=True,
                )
        for photo_record in photos:
            previous_rank = pdb.get_rank_by_photo(photo_record)
            if unranked and previous_rank:
                continue
            logging.debug(
                f"[{project}] Previous Rank for {photo_record}: {previous_rank}"
            )
            rank = inquirer.text(
                message=f"Enter a rank for this photo - {convert_to_absolute_path(photo_record, main_path)}:",
                default=str(previous_rank),
            ).execute()
            events_with_photo = pdb.find_events_with_photo(photo_record)
            if len(events_with_photo) > 1:
                handle_duplicate_events(pdb, events_with_photo, photo_record)
                events_with_photo = pdb.find_events_with_photo(photo_record)
            event_to_update = events_with_photo[0]
            ranking = {
                "rank": rank,
                "event": event_to_update.name,
                "path": photo_record,
            }
            pdb.upsert_rankings(ranking)

        if inquirer.confirm(message="Would you like to review the rankings?").execute():

            rankings = pdb.get_rankings_by_event(event_name)
            logging.debug(f"[{project}] Rankings for {event_name}: {rankings}")
            logger.info(f"Rankings for {event_name}:")
            for rank in rankings:
                absolute_path_rank = convert_to_absolute_path(rank["path"], main_path)
                logger.info(f"\tRank {rank['rank']}: {absolute_path_rank}")
                if view:
                    photo_record = pdb.get_photo(photo_path)
                    photo_record.compress_image(
                        project_path=main_path,
                        show=True,
                    )
    pdb.close()


@app.command()
def prune(
    project: str = typer.Argument(..., help="Project name"),
    view: bool = typer.Option(
        False, "--view", "-v", help="View files before processing"
    ),
    event_name: str = typer.Option(None, "--event", "-e", help="Event name"),
    all: bool = typer.Option(False, "--all", "-a", help="Review all photos"),
    no_event: bool = typer.Option(
        False, "--no-event", "-n", help="Prune photos not associated with an event"
    ),
):
    """Remove assets from events."""

    # Project initialization
    pdb, main_path = set_project(project)
    logging.debug(f"Project: {project}, Path: {main_path}, Settings: {pdb.settings}")
    events = pdb.get_events(event_name)
    if not events:
        logging.fatal("No events found. Please run photomise first.")
        typer.Exit(1)
    if not all and not event_name and not no_event:
        event_name = inquirer.select(
            message="Choose an event to prune", choices=events.keys()
        ).execute()

    if no_event:
        photos = pdb.get_photos_without_event()

    for event in events.values():
        logging.debug(f"[{project}] Event: {event}")
        if all:
            logger.info(f"{event.name}:")
        if not no_event:
            try:
                photos = event.photos
            except KeyError:
                logging.fatal("Event not found.")
                typer.Exit(1)
        logger.info(f"There are {len(photos)} photos in this event.")
        if view:
            for photo in photos:
                photo_record = pdb.get_photo(photo)
                photo_record.compress_image(
                    project_path=main_path,
                    show=True,
                )
        for photo_record in photos:
            if inquirer.confirm(
                message=f"Would you like to remove this photo - {convert_to_absolute_path(photo_record, main_path)} - from this event"
            ).execute():
                pdb.remove_photo_from_event(event, photo_record)
                logger.info(f"Photo removed from {event.name}.")
                logger.info(f"[{project}] Photo removed from {event.name}.")
                if inquirer.confirm(
                    message="Would you like to remove the file as well?"
                ).execute():
                    pdb.remove_photo(photo_record)
                    trash_folder = os.path.join(main_path, "trash")
                    os.makedirs(trash_folder, exist_ok=True)
                    os.rename(
                        convert_to_absolute_path(photo_record, main_path),
                        os.path.join(trash_folder, os.path.basename(photo_record)),
                    )
                    logger.info(f"Photo removed completely and file moved to {trash_folder}.")

    pdb.close()
