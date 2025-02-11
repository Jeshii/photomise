#!/usr/bin/env python3

import logging
import os

import pendulum
import piexif
import typer
from InquirerPy import inquirer

from photomise.database.shared import SharedDB
from photomise.utilities.exif import (
    compress_image,
    convert_to_degrees,
    deg_to_dms_rational,
    extract_datetime,
    extract_exif_info,
    extract_gps,
)
from photomise.utilities.logging import setup_logging
from photomise.utilities.project import (
    convert_to_absolute_path,
    convert_to_relative_path,
    get_non_hidden_files,
    handle_duplicate_events,
    item_duplicate,
    sanitize_text,
    set_project,
)
from photomise.utilities.shared import make_min_max_prompt

app = typer.Typer()
logger, console = setup_logging()


@app.command()
def images(
    project: str = typer.Argument(..., help="Project name"),
    view: bool = typer.Option(
        False, "--view", "-v", help="View files before processing"
    ),
    all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Process all files whether they've been processed previously or not",
    ),
):
    """Process image by rotating, scaling, changing quality, or apply filters."""

    # Project initialization
    pdb, main_path = set_project(project)
    logging.debug(f"Project: {project}, Path: {main_path}, Settings: {pdb.settings}")
    gdb = SharedDB()
    photos_path = f"{main_path}/assets"

    non_hidden_files = list(get_non_hidden_files(photos_path))

    if non_hidden_files == [(None, None)]:
        logging.fatal(
            "No files found in the project folder's assets directory, please add photos before running."
        )
        typer.Exit(1)

    for dir, file in non_hidden_files:

        file_path = f"{dir}/{file}"
        relative_path = convert_to_relative_path(file_path, main_path)

        console.print()
        console.print(f"[bold]Checking {file_path}[/bold]")
        need_to_convert_path = False
        photo_record = pdb.get_photo(relative_path)
        if not photo_record:
            photo_record = pdb.get_photo(file_path)
            need_to_convert_path = True
        if photo_record:
            rotation_angle = photo_record.get("rotation", 0)
            quality = photo_record.get("quality", pdb.settings.get("quality"))
            description = photo_record.get("description", "")
            flavor = photo_record.get("flavor", "")
            brightness = photo_record.get("brightness", 1.0)
            contrast = photo_record.get("contrast", 1.0)
            color = photo_record.get("color", 1.0)
            sharpness = photo_record.get("sharpness", 1.0)
        else:
            rotation_angle = 0
            quality = pdb.settings.get("quality")
            description = ""
            flavor = ""
            brightness = 1.0
            contrast = 1.0
            color = 1.0
            sharpness = 1.0
        if view or all:
            while True:
                _ = compress_image(
                    image_path=file_path,
                    rotation_angle=rotation_angle,
                    quality=quality,
                    brightness=brightness,
                    contrast=contrast,
                    color=color,
                    sharpness=sharpness,
                    show=True,
                )
                if inquirer.confirm(message="Does the image look okay?").execute():
                    break
                else:
                    quality = inquirer.select(
                        message="Choose a quality level",
                        choices=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
                        default=quality,
                    ).execute()

                    rotation_angle = inquirer.select(
                        message="Choose a rotation angle",
                        choices=[0, 90, 180, 270],
                        default=rotation_angle,
                    ).execute()

                    filter_choices = ["None"] + [
                        filter["name"] for filter in gdb.get_filters_all()
                    ]
                    filter_choices.append("Custom")

                    filter_search_params = {
                        "brightness": brightness,
                        "contrast": contrast,
                        "color": color,
                        "sharpness": sharpness,
                    }

                    filter_to_apply = inquirer.select(
                        message="Choose a filter",
                        choices=filter_choices,
                        default=gdb.get_filter_from_values(filter_search_params),
                    ).execute()

                    match filter_to_apply:
                        case "Custom":
                            brightness = make_min_max_prompt(
                                "Adjust brightness", brightness
                            )
                            contrast = make_min_max_prompt("Adjust contrast", contrast)
                            color = make_min_max_prompt("Adjust color", color)
                            sharpness = make_min_max_prompt(
                                "Adjust sharpness", sharpness
                            )
                        case "None":
                            brightness = 1.0
                            contrast = 1.0
                            color = 1.0
                            sharpness = 1.0
                        case _:
                            filter = gdb.get_filter(filter_to_apply)
                            brightness = filter.get("brightness", 1.0)
                            contrast = filter.get("contrast", 1.0)
                            color = filter.get("color", 1.0)
                            sharpness = filter.get("sharpness", 1.0)

        if (pdb.settings.get("description") and not description) or all:
            description = inquirer.text(
                message="Enter a description for visually impaired users about this image:",
                default=description,
            ).execute()
        if (pdb.settings.get("flavor") and not flavor) or all:
            flavor = inquirer.text(
                message="Enter flavor text for this image:",
                default=flavor,
            ).execute()

        if need_to_convert_path:
            photo_path = file_path
        else:
            photo_path = relative_path

        photo = {
            "path": photo_path,
            "description": description,
            "flavor": flavor,
            "rotation": rotation_angle,
            "quality": quality,
            "brightness": brightness,
            "contrast": contrast,
            "color": color,
            "sharpness": sharpness,
        }

        updated = pdb.upsert_photo(photo)

        logging.debug(f"Updated Photo: {updated}")

    pdb.close()
    gdb.close()


@app.command()
def location(
    project: str = typer.Argument(..., help="Project name"),
    link: str = typer.Option(
        None,
        "--link",
        "-l",
        help="Helper link to append to latitude and longitude to help find location",
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
            "No files found in the project folder's photos directory, please add photos before running."
        )
        typer.Exit(1)

    for dir, file in get_non_hidden_files(photos_path):
        date_object = None
        lat = None
        lon = None
        file_path = f"{dir}/{file}"
        relative_path = convert_to_relative_path(file_path, main_path)

        # Check for duplicates
        duplicate_events = pdb.find_events_with_photo(relative_path)
        if len(duplicate_events) > 1:
            handle_duplicate_events(pdb, duplicate_events, relative_path)

        try:
            exif_tags = extract_exif_info(file_path)

            lat, lon = extract_gps(exif_tags)

            date_object = extract_datetime(exif_tags)
        except piexif.InvalidImageDataError:
            logging.warning("Invalid image data")
            continue
        except Exception as e:
            logging.info(f"Error extracting exif info: {e}")

        console.print()
        if not date_object:
            date_object = pendulum.parse(
                inquirer.text("Please enter a date for this photo").execute()
            )

        if lat and lon:
            location_name = gdb.find_location(lat, lon)
            if location_name:
                console.print(f"Location: {location_name}")
                console.print(f"Latitude: {lat}, Longitude: {lon}")
            else:
                if link:
                    from urllib.parse import quote

                    encoded_lat = quote(str(lat))
                    encoded_lon = quote(str(lon))
                    console.print(
                        f"[link={link}{encoded_lat},{encoded_lon}]Helper link[/link]"
                    )
                location_name = inquirer.text(
                    f"Please enter a location name for {lat},{lon}"
                ).execute()
                params = {"name": location_name, "latitude": lat, "longitude": lon}
                gdb.upsert_location(params)
        else:
            if inquirer.confirm(
                "No GPS info found - would you like to add some?"
            ).execute():
                try:
                    if "°" in lat or "S" in lat or "N" in lat:
                        if "S" in lat:
                            lat = -convert_to_degrees(lat)
                        else:
                            lat = convert_to_degrees(lat)
                    else:
                        lat = float(lat)
                except ValueError:
                    console.print("Invalid latitude format.")
                    continue

                lon = inquirer.text("Longitude").execute()
                try:
                    if "°" in lon or "W" in lon or "E" in lon:
                        if "W" in lon:
                            lon = -convert_to_degrees(lon)
                        lon = convert_to_degrees(lon)
                    else:
                        lon = float(lon)
                except ValueError:
                    console.print("Invalid longitude format.")
                    continue

                location_name = gdb.get_location_coord(lat, lon)
                if location_name:
                    console.print(f"Location: {location_name}")
                else:
                    if link:
                        console.print(f"[link={link}{lat},{lon}]Helper link[/link]")
                    location_name = inquirer.text(
                        f"Please enter a location name for {lat},{lon}"
                    ).execute()
                    params = {
                        "name": location_name,
                        "latitude": lat,
                        "longitude": lon,
                    }
                    gdb.upsert_location(params)
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
                console.print("Skipping...")
                continue

        if date_object:
            console.print(f"Taken: {date_object.format('YYYY-MM-DD HH:MM')}")
            event_date, event_name, event_same = pdb.same_event(
                date_object, location_name
            )
        else:
            event_date = date_object
            event_same = False
            event_name = None

        if item_duplicate(pdb, gdb, date_object, lat, lon):
            logging.debug("This item appears to be a duplicate and will be skipped.")
            continue

        if pdb.settings.get("auto_event"):
            location_name_sanitized = sanitize_text(location_name)
            event_name = f"{event_date.format('YYYYMMDD')}-{location_name_sanitized}"
        else:
            event_name = inquirer.text(
                f"Please name this event from {event_date.format('YYYY-MM-DD')} at {location_name}"
            ).execute()

        if event_same:
            logging.debug("This event appears to be a duplicate and will be skipped.")
            logging.debug(f"Event Name: {event_name}")
            event = pdb.get_event(event_name)
            logging.debug(f"Event: {event}")
            if relative_path not in event.get("photos", []):
                pdb.upsert_event(event, relative_path)
            else:
                console.print("This photo has already been added to this event.")
        else:
            pdb.upsert_event(
                {
                    "event": event_name,
                    "latitude": lat,
                    "longitude": lon,
                    "location": location_name,
                    "date": date_object.timestamp(),
                    "photos": [relative_path],
                }
            )

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
            photos = event["photos"]
        except KeyError:
            logging.fatal("Event not found.")
            typer.Exit(1)
        if len(photos) <= greater_than:
            continue
        console.print(f"There are {len(photos)} photos in {event_name}.")
        if view:
            for photo_path in photos:
                photo = pdb.get_photo(photo_path)
                absolute_path = convert_to_absolute_path(photo_path, main_path)
                compress_image(
                    image_path=absolute_path,
                    rotation_angle=photo["rotation"],
                    quality=photo["quality"],
                    brightness=photo["brightness"],
                    contrast=photo["contrast"],
                    color=photo["color"],
                    sharpness=photo["sharpness"],
                    show=True,
                )
        for photo in photos:
            previous_rank = pdb.get_rank_by_photo(photo)
            if unranked and previous_rank:
                continue
            logging.debug(f"[{project}] Previous Rank for {photo}: {previous_rank}")
            rank = inquirer.text(
                message=f"Enter a rank for this photo - {convert_to_absolute_path(photo, main_path)}:",
                default=str(previous_rank),
            ).execute()
            events_with_photo = pdb.find_events_with_photo(photo)
            if len(events_with_photo) > 1:
                handle_duplicate_events(pdb, events_with_photo, photo)
                events_with_photo = pdb.find_events_with_photo(photo)
            event_to_update = events_with_photo[0]
            ranking = {
                "rank": rank,
                "event": event_to_update["event"],
                "path": photo,
            }
            pdb.upsert_rankings(ranking)

        if inquirer.confirm(message="Would you like to review the rankings?").execute():

            rankings = pdb.get_rankings_by_event(event_name)
            logging.debug(f"[{project}] Rankings for {event_name}: {rankings}")
            console.print(f"Rankings for {event_name}:")
            for rank in rankings:
                absolute_path_rank = convert_to_absolute_path(rank["path"], main_path)
                console.print(f"\tRank {rank['rank']}: {absolute_path_rank}")
                if view:
                    photo = pdb.get_photo(photo_path)
                    compress_image(
                        image_path=absolute_path_rank,
                        rotation_angle=photo["rotation"],
                        quality=photo["quality"],
                        brightness=photo["brightness"],
                        contrast=photo["contrast"],
                        color=photo["color"],
                        sharpness=photo["sharpness"],
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
):
    """Remove assets from events."""

    # Project initialization
    pdb, main_path = set_project(project)
    logging.debug(f"Project: {project}, Path: {main_path}, Settings: {pdb.settings}")
    events = pdb.get_events()
    if not events:
        logging.fatal("No events found. Please run photomise first.")
        typer.Exit(1)
    if not all and not event_name:
        event_name = inquirer.select(
            message="Choose an event to rank", choices=events.keys()
        ).execute()

    if not all:
        try:
            events = [events[event_name]]
        except KeyError:
            logging.fatal("Event not found.")
            typer.Exit(1)
    for event_name, event in events.items():
        logging.debug(f"[{project}] Event: {event}")
        try:
            photos = event["photos"]
        except KeyError:
            logging.fatal("Event not found.")
            typer.Exit(1)
        console.print(f"There are {len(photos)} photos in this event.")
        if view:
            for photo_path in photos:
                photo = pdb.get_photo(photo_path)
                absolute_path = convert_to_absolute_path(photo_path, main_path)
                compress_image(
                    image_path=absolute_path,
                    rotation_angle=photo["rotation"],
                    quality=photo["quality"],
                    brightness=photo["brightness"],
                    contrast=photo["contrast"],
                    color=photo["color"],
                    sharpness=photo["sharpness"],
                    show=True,
                )
        for photo in photos:
            if inquirer.confirm(
                message=f"Would you like to remove this photo - {convert_to_absolute_path(photo, main_path)}:"
            ).execute():

                if inquirer.confirm(
                    message="Would you like to delete the file as well?"
                ).execute():
                    pdb.remove_photo_from_event(events, photo)
                    pdb.remove_photo(photo)
                    os.remove(convert_to_absolute_path(photo, main_path))
                else:
                    pdb.remove_photo_from_event(events, photo, event_name)

    pdb.close()
