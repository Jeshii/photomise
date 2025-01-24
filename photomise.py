#!/usr/bin/env python3

import argparse
import piexif
from tinydb import TinyDB, Query, where
from geopy.distance import great_circle
import pendulum
import os
from InquirerPy import inquirer
from rich.console import Console
from urllib.parse import quote
import configparser
import logging
from PIL import Image, ImageEnhance
from io import BytesIO
import json

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


def deg_to_dms_rational(deg):
    d = int(deg)
    m = int((deg - d) * 60)
    s = (deg - d - m / 60) * 3600
    return [(d, 1), (m, 1), (int(s * 100), 100)]


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


def compress_image(
    image_path: str,
    quality: int = 85,
    max_dimension: int = 1200,
    rotation_angle: int = 0,
    show: bool = False,
):
    try:
        image = Image.open(image_path)
        img_io = BytesIO()

        if rotation_angle:
            image = image.rotate(float(rotation_angle), expand=True)

        width, height = image.size

        if width > max_dimension or height > max_dimension:
            if width > height:
                scale_factor = max_dimension / width
            else:
                scale_factor = max_dimension / height

            new_width = int(width * scale_factor)
            new_height = int(height * scale_factor)
            image = image.resize((new_width, new_height), Image.LANCZOS)

        image.save(img_io, format="JPEG", optimize=True, quality=quality)
        if show:
            image.show()

        img_io.seek(0)

        return img_io
    except Exception as e:
        print(f"Error compressing image: {e}")

def enhance_image(
        image: Image.Image,
        brightness: float = 1.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        sharpness: float = 1.0
        ) -> Image.Image:

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(brightness)

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(contrast)

    enhancer = ImageEnhance.Color(image)
    image = enhancer.enhance(saturation)

    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(sharpness)

    return image



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
    found_non_hidden_files = False
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            if not filename.startswith(".") and not filename.startswith("~"):
                found_non_hidden_files = True
                yield dirpath, filename
    if not found_non_hidden_files:
        yield None, None


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


def get_project_db(project: str, project_dir: str) -> TinyDB:
    return TinyDB(f"{project_dir}{project}.json")


def get_location_table(database: str) -> TinyDB:
    return database.table("locations")


def get_events_table(database: str) -> TinyDB:
    return database.table("events")


def get_posts_table(database: str) -> TinyDB:
    return database.table("posts")


def get_project_table(database: str) -> TinyDB:
    return database.table("project")


def get_photos_table(database: str) -> TinyDB:
    return database.table("photos")

def get_accounts_table(database: str) -> TinyDB:
    return database.table("accounts")


def get_settings(database: str, args: argparse.Namespace) -> TinyDB:
    settings_table = database.table("settings")
    settings = settings_table.all()
    logging.debug(f"Settings: {settings}")
    if not args.description:
        args.description = settings[0].get("description")
    if not args.flavor:
        args.flavor = settings[0].get("flavor")
    return args


def get_image_aspect_ratio(image_path: str) -> tuple:
    try:
        exif_dict = piexif.load(image_path)
        image_width = exif_dict["0th"][piexif.ImageIFD.ImageWidth]
        image_height = exif_dict["0th"][piexif.ImageIFD.ImageLength]
        return (image_width, image_height)
    except (piexif.InvalidImageDataError, KeyError, TypeError):
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                return (width, height)
        except (OSError, IOError):
            return None, None


def set_project(
    console: Console, config: configparser.ConfigParser, args: argparse.Namespace
) -> tuple[TinyDB, str]:
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)

    if not config.has_section("Projects"):
        config["Projects"] = {}

    config_dict = {
        section: dict(config.items(section)) for section in config.sections()
    }

    projects = config_dict.get("Projects", {})
    
    project_set_up = False
    if not projects:
        project_set_up = True
        console.print("No projects found in config.ini")
        args.project = inquirer.text("Please enter a project name").execute()
        project_path = inquirer.text("Please the path for the project").execute()
        args.description = inquirer.confirm(
            "Would you like to provide descriptions for visually impaired users?"
        ).execute()
        args.flavor = inquirer.confirm(
            "Would you like to provide flavor text for the images?"
        ).execute()
        if not os.path.exists(project_path):
            os.makedirs(project_path)
        if not os.path.exists(f"{project_path}/db"):
            os.makedirs(f"{project_path}/db")
        if not os.path.exists(f"{project_path}/photos"):
            os.makedirs(f"{project_path}/photos")
        projects[args.project] = project_path
        config["Projects"] = projects
        with open(CONFIG_FILE, "w", encoding="utf-8") as configfile:
            try:
                config.write(configfile)
            except IOError as e:
                console.print(f"Error writing to config file: {e}")
                logging.exception("Error writing to config file")

    if not args.project:
        args.project = inquirer.select(
            message="Select a project", choices=projects.keys()
        ).execute()
    db_path = f"{projects[args.project]}/db/"
    photos_path = f"{projects[args.project]}/photos/"

    # Read the JSON file
    with open(f"{db_path}{args.project}.json", "r") as file:
        data = json.load(file)

    # Write the formatted JSON file
    with open(f"{db_path}{args.project}.json", "w") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    project_db = get_project_db(args.project, db_path)

    args = get_settings(project_db, args)

    if project_set_up:
        settings_table = project_db.table("settings")
        Settings = Query()
        settings_table.update(
            {
                "project_name": args.project,
                "project_path": projects[args.project],
                "description": args.description, 
                "flavor": args.flavor,
            }, 
            Settings.id == 1
        )

    return project_db, photos_path


def update_event_posted(db, event_name, user, platform):
    db.insert(
        {
            "event": event_name,
            "where": platform,
            "account": santitize_text(user),
            "date": pendulum.now().timestamp(),
        }
    )


def main(args):
    # Basic initialization
    config = configparser.ConfigParser()
    console = Console()
    level = getattr(logging, args.log.upper())
    logging.basicConfig(level=level)

    # Project initialization
    project_db, photos_path = set_project(console, config, args)
    event_table = get_events_table(project_db)
    location_table = get_location_table(project_db)
    photos_table = get_photos_table(project_db)
    args = get_settings(project_db, args)
    level = getattr(logging, args.log.upper())
    logging.basicConfig(level=level)

    logging.debug(f"Arguments: {args}")

    non_hidden_files = list(get_non_hidden_files(photos_path))

    if non_hidden_files == [(None, None)]:
        console.print(
            "No files found in the project folder's photos directory, please add photos before running."
        )
        return
    else:
        for dir, file in get_non_hidden_files(photos_path):
            date_object = None
            lat = None
            lon = None

            file_path = f"{dir}{file}"
            console.print(f"Checking {file}...")
            if photos_table.search(where("path") == file_path):
                rotation_angle = photos_table.get(where("path") == file_path).get(
                    "rotation"
                )
                quality = photos_table.get(where("path") == file_path).get("quality")
                description = photos_table.get(where("path") == file_path).get(
                    "description"
                )
                flavor = photos_table.get(where("path") == file_path).get("flavor")
            else:
                rotation_angle = 0
                quality = 85
                description = ""
                flavor = ""
            if args.view:
                while True:
                    _ = compress_image(
                        file_path,
                        rotation_angle=rotation_angle,
                        quality=quality,
                        show=True,
                    )
                    if inquirer.confirm(message="Does the image look okay?").execute():
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


            if args.description:
                description = inquirer.text(
                    message=f"Enter a description for viewing impaired users for this image: {file_path}",
                    default=description,
                ).execute()

                photos_table
            if args.flavor:
                flavor = inquirer.text(
                    message=f"Enter flavor text for this image: {file_path}",
                    default=flavor,
                ).execute()

            photos_table.insert(
                {
                    "path": file_path,
                    "rotation": rotation_angle,
                    "quality": quality,
                    "description": description,
                    "flavor": flavor,
                }
            )

            try:
                exif_tags = extract_exif_info(file_path)

                lat, lon = extract_gps(exif_tags)

                date_object = extract_datetime(exif_tags)
            except Exception:
                console.print("Error extracting exif info")
                logging.exception("Error extracting exif info")

            if not date_object:
                date_object = pendulum.parse(
                    inquirer.text("Please enter a date for this photo").execute()
                )

            if lat and lon:
                console.print(f"Latitude: {lat}, Longitude: {lon}")
                location_name = find_location(location_table, lat, lon)
                if location_name:
                    console.print(f"Location: {location_name}")
                else:
                    if args.link:
                        console.print(
                            f"[link={args.link}{lat},{lon}]Helper link[/link]"
                        )
                    location_name = inquirer.text(
                        f"Please enter a location name for {lat},{lon}"
                    ).execute()
                    location_table.insert(
                        {"name": location_name, "latitude": lat, "longitude": lon}
                    )
            else:
                if inquirer.confirm(
                    "No GPS info found - would you like to add some?"
                ).execute():
                    try:
                        lat = inquirer.text("Latitude").execute()
                        if "°" in lat or "S" in lat or "N" in lat:
                            if "S" in lat:
                                lat = -convert_to_degrees(lat)
                            else:
                                lat = convert_to_degrees(lat)
                        else:
                            lat = float(lat)
                        lon = inquirer.text("Longitude").execute()
                        if "°" in lon or "W" in lon or "E" in lon:
                            if "W" in lon:
                                lon = -convert_to_degrees(lon)
                            lon = convert_to_degrees(lon)
                        else:
                            lon = float(lon)
                        location_name = find_location(location_table, lat, lon)
                        if location_name:
                            console.print(f"Location: {location_name}")
                        else:
                            if args.link:
                                console.print(
                                    f"[link={args.link}{lat},{lon}]Helper link[/link]"
                                )
                            location_name = inquirer.text(
                                f"Please enter a location name for {lat},{lon}"
                            ).execute()
                            location_table.insert(
                                {
                                    "name": location_name,
                                    "latitude": lat,
                                    "longitude": lon,
                                }
                            )
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
                    except Exception:
                        console.print("Error adding GPS info")
                        logging.exception("Error adding GPS info")
                        continue
                else:
                    console.print("Skipping...")
                    continue

            if date_object:
                console.print(f"Taken: {date_object.format("YYYY-MM-DD HH:MM")}")
                event_date, event_name, event_same = same_event(
                    event_table, date_object, location_name
                )
            else:
                event_date = date_object
                event_same = False
                event_name = None

            if item_duplicate(event_table, date_object, lat, lon):
                console.print("This item appears to be a duplicate. Skipping...")
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
                event = event_table.get(Event.event == event_name)
                if file_path not in event.get("photos", []):
                    event_table.update(
                        {"photos": event.get("photos", []) + [file_path]},
                        Event.event == event_name,
                    )
                else:
                    console.print("This photo has already been added to this event.")
            else:
                event_table.insert(
                    {
                        "event": event_name,
                        "latitude": lat,
                        "longitude": lon,
                        "location": location_name,
                        "date": date_object.timestamp(),
                        "photos": [file_path],
                    }
                )


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
        "--view",
        "-v",
        action="store_true",
        help="View the image while processing",
    )

    parser.add_argument(
        "--flavor",
        "-f",
        action="store_true",
        help="Ask to store flavor text (default is use event name and date)",
    )

    parser.add_argument(
        "--description",
        "-d",
        action="store_true",
        help="Ask to store a description of the photo for viewing impaired users (default is use flavor text)",
    )

    parser.add_argument(
        "--project",
        "-p",
        help="Provide the name of the project to use",
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
