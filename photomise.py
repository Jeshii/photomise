#!/usr/bin/env python3

import argparse
import exifread
from tinydb import TinyDB, Query
from geopy.distance import great_circle
import pendulum
from os import walk, remove
from os.path import isfile
from InquirerPy import inquirer


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


def item_duplicate(db, date_object, lat, lon):
    for item in db.all():
        if (
            item["date"] == date_object
            and item["latitude"] == lat
            and item["longitude"] == lon
        ):
            return True
    return False


def main(args):
    files = []

    location_db = TinyDB("locations.json")
    items_db = TinyDB("items.json")

    if args.file:
        files.extend(args.file)
    elif args.directory:
        for dirpath, _, filenames in walk(args.directory):
            for file in filenames:
                files.append(f"{dirpath}/{file}")
    else:
        path = inquirer.text(message="Enter a file or a directory").execute()
        if isfile(path):
            files.extend(path)
        else:
            for dirpath, _, filenames in walk(path):
                for file in filenames:
                    files.append(f"{dirpath}/{file}")

    for file in files:
        exif_tags = extract_exif_info(file)

        lat, lon = extract_gps(exif_tags)

        date_object = extract_datetime(exif_tags)

        if date_object:
            print(f"Taken: {date_object}")

        if lat and lon:
            print(f"Latitude: {lat}, Longitude: {lon}")
            location_name = find_location(location_db, lat, lon)
            if location_name:
                print(f"Location: {location_name}")
            else:
                location_name = inquirer.text(
                    f"Please enter a location name for {lat},{lon}"
                ).execute()
                location_db.insert(
                    {"name": location_name, "latitude": lat, "longitude": lon}
                )

            if item_duplicate(file, date_object, lat, lon):
                if inquirer.confirm(
                    "This item appears to be a duplicate. Delete it?"
                ).execute():
                    if isfile(file):
                        remove(file)
                        print(f"{file} has been deleted.")
                    else:
                        print(f"Could not find {file}")
            else:
                if args.item:
                    item_name = inquirer.text(
                        f"Please name this item: {file} - {date_object}"
                    ).execute()
                else:
                    item_name = f"{file}-{date_object}"

                # Save item
                items_db.insert(
                    {
                        "item": item_name, 
                        "latitude": lat, 
                        "longitude": lon, 
                        "date": date_object,
                    }
                )
        else:
            print("No GPS info found.")


def parse_args():
    description = "A script to find locations that match photo location metadata."

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=description
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--file", "-f", help="The file location of a photo to analyze")
    group.add_argument("--directory", "-d", help="A directory of photos to analyze")
    parser.add_argument(
        "--item",
        "-i",
        action="store_true",
        help="Ask for item names",
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
