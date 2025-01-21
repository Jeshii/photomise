#!/usr/bin/env python3

import argparse
import piexif
from tinydb import TinyDB, Query
from geopy.distance import great_circle
import pendulum
import os
from InquirerPy import inquirer
from rich.console import Console
from urllib.parse import quote
import configparser
import logging
from PIL import Image

CONFIG_FILE = "config.ini"


def get_all_events(db):
    events = {}
    for document in db.all():
        events[document["event"]] = document
    return events


def santitize_text(text: str = "") -> str:
    return quote(text.replace(" ", "_"))


def extract_exif_info(image_path: str) -> dict:
    exif_dict = piexif.load(image_path)
    return exif_dict


def convert_to_degrees(value) -> float:
    d = value[0][0] / value[0][1]
    m = value[1][0] / value[1][1]
    s = value[2][0] / value[2][1]
    return d + (m / 60.0) + (s / 3600.0)


def extract_gps(tags: dict) -> tuple:
    gps_info = tags.get("GPS", {})

    gps_latitude = gps_info.get(piexif.GPSIFD.GPSLatitude)
    gps_latitude_ref = gps_info.get(piexif.GPSIFD.GPSLatitudeRef)
    gps_longitude = gps_info.get(piexif.GPSIFD.GPSLongitude)
    gps_longitude_ref = gps_info.get(piexif.GPSIFD.GPSLongitudeRef)

    if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
        lat = convert_to_degrees(gps_latitude)
        if gps_latitude_ref != b"N":
            lat = -lat
        lon = convert_to_degrees(gps_longitude)
        if gps_longitude_ref != b"E":
            lon = -lon
        return lat, lon
    else:
        return None, None


def extract_datetime(tags: dict) -> pendulum:
    exif_info = tags.get("Exif", {})
    date_taken = exif_info.get(piexif.ExifIFD.DateTimeOriginal)

    if date_taken:
        date_taken_str = date_taken.decode("utf-8")
        date_taken_formatted = date_taken_str.replace(":", "-", 2)
        dt = pendulum.parse(date_taken_formatted)

        return dt
    else:
        return None


def same_event(
    event_db: TinyDB, date: pendulum, location: str, max_time_delta_in_hours: int = 8
):
    for item in event_db.all():
        db_date = pendulum.from_timestamp(item["date"])
        time_delta = date.diff(db_date).in_hours()

        if time_delta < max_time_delta_in_hours and location == item["location"]:
            return db_date, item["event"], True
    return date, None, False


def item_duplicate(db, date_object, lat, lon):
    Search = Query()
    result = db.search(
        (Search["date"] == date_object.timestamp())
        & (Search["latitude"] == lat)
        & (Search["longitude"] == lon)
    )
    return len(result) > 0


def get_non_hidden_files(directory):
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            if not filename.startswith(".") and not filename.endswith(
                ".json"
            ):  # Check if filename does not start with a dot
                yield dirpath, filename


def remove_file(console: Console, file_path: str):
    if os.isfile(file_path):
        os.remove(file_path)
        console.print(f"{file_path} has been deleted.")
    else:
        console.print(f"Could not find {file_path}")


def find_location(db, latitude, longitude, max_distance_km=0.5):
    closest_location = None
    closest_distance = max_distance_km

    for item in db.all():
        location_coords = (item["latitude"], item["longitude"])
        distance = great_circle((latitude, longitude), location_coords).kilometers

        if distance < closest_distance:
            closest_location = item["name"]
            closest_distance = distance

    return closest_location


def fix_dir(current):
    return current.replace("\\", "").strip()


def get_config(config: configparser.ConfigParser) -> configparser.ConfigParser:
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)

    if not config.has_section("Paths"):
        config["Paths"] = {}

    if not config.has_section("Accounts"):
        config["Accounts"] = {}

    try:
        photo_dir = config.get("Paths", "photo_dir")
    except (configparser.NoSectionError, configparser.NoOptionError):
        photo_dir = inquirer.text(
            message="Enter the path to the photo directory", filter=fix_dir
        ).execute()
        config["Paths"]["photo_dir"] = photo_dir

    try:
        database_dir = config.get("Paths", "database_dir")
    except (configparser.NoSectionError, configparser.NoOptionError):
        database_dir = inquirer.text(
            message="Enter the path to the database directory", filter=fix_dir
        ).execute()
        config["Paths"]["database_dir"] = database_dir

    with open(CONFIG_FILE, "w") as configfile:
        config.write(configfile)

    return config


def get_event_db(database_dir: str) -> TinyDB:
    return TinyDB(f"{database_dir}/event.json")


def get_location_db(database_dir: str) -> TinyDB:
    return TinyDB(f"{database_dir}/locations.json")


def main(args):
    console = Console()
    config = configparser.ConfigParser()
    config = get_config(config)
    event_db = get_event_db(config["Paths"]["database_dir"])
    location_db = get_location_db(config["Paths"]["database_dir"])
    level = getattr(logging, args.log.upper())
    logging.basicConfig(level=level)

    for dir, file in get_non_hidden_files(config["Paths"]["photo_dir"]):
        date_object = None
        lat = None
        lon = None

        file_path = f"{dir}/{file}"
        console.print(f"Checking {file}...")
        if args.preview:
            image = Image.open(file_path)
            image.show(title=file_path)

        try:
            exif_tags = extract_exif_info(file_path)

            lat, lon = extract_gps(exif_tags)

            date_object = extract_datetime(exif_tags)
        except Exception:
            console.print_exception()

        if not date_object:
            date_object = pendulum.parse(
                inquirer.text("Please enter a date for this photo").execute()
            )

        if lat and lon:
            console.print(f"Latitude: {lat}, Longitude: {lon}")
            location_name = find_location(location_db, lat, lon)
            if location_name:
                console.print(f"Location: {location_name}")
            else:
                if args.link:
                    console.print(f"[link={args.link}{lat},{lon}]Helper link[/link]")
                location_name = inquirer.text(
                    f"Please enter a location name for {lat},{lon}"
                ).execute()
                location_db.insert(
                    {"name": location_name, "latitude": lat, "longitude": lon}
                )
            if date_object:
                console.print(f"Taken: {date_object.format("YYYY-MM-DD HH:MM")}")
                event_date, event_name, event_same = same_event(
                    event_db, date_object, location_name
                )
            else:
                event_date = date_object
                event_same = False
                event_name = None

            if item_duplicate(event_db, date_object, lat, lon):
                if inquirer.confirm(
                    "This item appears to be a duplicate. Skip?"
                ).execute():
                    continue
            if args.event and not event_name:
                event_name = inquirer.text(
                    f"Please name this event from {event_date.format("YYYY-MM-DD")} at {location_name}"
                ).execute()
            else:
                location_name_sanitized = santitize_text(location_name)
                event_name = (
                    f"{event_date.format("YYYYMMDD")}-{location_name_sanitized}"
                )

            if event_same:
                Event = Query()
                event = event_db.get(Event.event == event_name)
                event_db.update(
                    {"photos": event.get("photos", []) + [file_path]},
                    Event.event == event_name,
                )
            else:
                event_db.insert(
                    {
                        "event": event_name,
                        "latitude": lat,
                        "longitude": lon,
                        "location": location_name,
                        "date": date_object.timestamp(),
                        "photos": [file_path],
                    }
                )

        else:
            console.print("No GPS info found.")


def parse_args():
    description = "A script to find locations that match photo location metadata."

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=description
    )
    parser.add_argument(
        "--event",
        "-e",
        action="store_true",
        help="Ask for event names (default is to name events automatically by date and location)",
    )
    parser.add_argument(
        "--link",
        "-l",
        help="Supply a link to display with lat/lon appended at end to help identify coordinates",
    )
    parser.add_argument(
        "--preview",
        "-p",
        action="store_true",
        help="Show image preview",
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
