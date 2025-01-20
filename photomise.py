#!/usr/bin/env python3

import argparse
import exifread
from tinydb import TinyDB, Query
from geopy.distance import great_circle
import pendulum
from os import walk, remove, rename
from os.path import isfile, splitext
from InquirerPy import inquirer
from rich.console import Console


def extract_exif_info(image_path: str) -> dict:
    with open(image_path, "rb") as f:
        tags = exifread.process_file(f)

        return tags


def extract_gps(tags: dict) -> tuple:
    gps_latitude = tags.get("GPS GPSLatitude")
    gps_latitude_ref = tags.get("GPS GPSLatitudeRef")
    gps_longitude = tags.get("GPS GPSLongitude")
    gps_longitude_ref = tags.get("GPS GPSLongitudeRef")

    if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
        lat = convert_to_degrees(gps_latitude)
        if gps_latitude_ref.values[0] != "N":
            lat = -lat
        lon = convert_to_degrees(gps_longitude)
        if gps_longitude_ref.values[0] != "E":
            lon = -lon
        return lat, lon
    else:
        return None, None


def extract_datetime(tags: dict) -> pendulum:
    date_taken = tags.get("EXIF DateTimeOriginal")

    if date_taken:
        date_taken_str = str(date_taken)
        date_taken_formatted = date_taken_str.replace(":", "-", 2)
        dt = pendulum.parse(date_taken_formatted)

        return dt
    else:
        return None


def convert_to_degrees(value):
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)
    return d + (m / 60.0) + (s / 3600.0)


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


def same_event(db: TinyDB, date: pendulum, max_time_delta_in_hours: int = 1):
    for item in db.all():
        db_date = pendulum.from_timestamp(item["date"])
        time_delta = date.diff(db_date).in_hours()

        if time_delta < max_time_delta_in_hours:
            return True

    return False


def item_duplicate(db, date_object, lat, lon):
    Search = Query()
    result = db.search(
        (Search["date"] == date_object.timestamp())
        & (Search["latitude"] == lat)
        & (Search["longitude"] == lon)
    )
    return len(result) > 0


def get_non_hidden_files(directory):
    for dirpath, _, filenames in walk(directory):
        for filename in filenames:
            if not filename.startswith(".") and not filename.endswith(
                ".json"
            ):  # Check if filename does not start with a dot
                yield dirpath, filename


def remove_file(console: Console, file_path: str):
    if isfile(file_path):
        remove(file_path)
        console.print(f"{file_path} has been deleted.")
    else:
        console.print(f"Could not find {file_path}")


def rename_file(console: Console, dir: str, file: str, new_name: str):
    path = f"{dir}/{file}"
    new_path = f"{dir}/{new_name}"
    if isfile(path):
        rename(path, new_path)
        console.print(f"{path} has been renamed to {new_path}.")
    else:
        console.print(f"Could not find {path}")


def get_image_aspect_ratio(image_path):
    with open(image_path, "rb") as f:
        tags = exifread.process_file(f)

    try:
        image_width = int(tags["Image Width"].values[0])
        image_height = int(tags["Image Height"].values[0])
        return (image_width, image_height)
    except KeyError:
        return None


def main(args):
    console = Console()

    if not args.directory:
        args.directory = inquirer.text(message="Enter a file or a directory").execute()

    if args.same:
        location_db = TinyDB(f"{args.directory}/locations.json")
        item_db = TinyDB(f"{args.directory}/items.json")
    else:
        location_db = TinyDB("locations.json")
        item_db = TinyDB("items.json")

    for dir, file in get_non_hidden_files(args.directory):
        file_path = f"{dir}/{file}"
        console.print(f"Checking {file}...")
        try:
            exif_tags = extract_exif_info(file_path)

            lat, lon = extract_gps(exif_tags)

            date_object = extract_datetime(exif_tags)
        except Exception:
            console.print_exception()

        if date_object:
            console.print(f"Taken: {date_object}")
            if same_event(item_db, date_object):
                if inquirer.confirm(
                    "This item appears to be from an already registered event. Delete it?"
                ).execute():
                    remove_file(console, file_path)

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

            if item_duplicate(item_db, date_object, lat, lon):
                if inquirer.confirm(
                    "This item appears to be a duplicate. Delete it?"
                ).execute():
                    remove_file(console, file_path)
            else:
                if args.item:
                    item_name = inquirer.text(
                        f"Please name this item: {file} - {date_object}"
                    ).execute()
                else:
                    item_name = f"{file.split(".")[0]}-{date_object.format("YYYYMMDD")}"

                # Save item
                item_db.insert(
                    {
                        "item": item_name,
                        "latitude": lat,
                        "longitude": lon,
                        "location": location_name,
                        "date": date_object.timestamp(),
                    }
                )

                if args.rename:
                    extension = splitext(file_path)[1]
                    if "." not in extension:
                        extension = f".{extension}"
                    new_name = (
                        f"{item_name}-{location_name.replace(" ","_")}{extension}"
                    )
                    rename_file(console, dir, file, new_name)

        else:
            console.print("No GPS info found.")


def parse_args():
    description = "A script to find locations that match photo location metadata."

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=description
    )
    parser.add_argument("--directory", "-d", help="A directory of photos to analyze")
    parser.add_argument(
        "--item",
        "-i",
        action="store_true",
        help="Ask for item names",
    )
    parser.add_argument(
        "--link",
        "-l",
        help="Supply a link to display with lat/lon",
    )
    parser.add_argument(
        "--rename",
        "-r",
        action="store_true",
        help="Rename file based on provided info",
    )
    parser.add_argument(
        "--same",
        "-s",
        action="store_true",
        help="Store DB in same folder as photos",
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
