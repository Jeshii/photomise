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
    quality: int = 80,
    max_dimension: int = 1200,
    rotation_angle: int = 0,
    brightness: float = 1.0,
    contrast: float = 1.0,
    color: float = 1.0,
    sharpness: float = 1.0,
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

        image = enhance_image(
            image,
            brightness,
            contrast,
            color,
            sharpness,
        )

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
    color: float = 1.0,
    sharpness: float = 1.0,
) -> Image.Image:

    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(brightness)

    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(contrast)

    enhancer = ImageEnhance.Color(image)
    image = enhancer.enhance(color)

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


def get_global_db() -> TinyDB:
    return TinyDB("global.json")


def get_location_table() -> TinyDB:
    global_db = get_global_db()
    return global_db.table("locations")


def get_filter_table() -> TinyDB:
    global_db = get_global_db()
    return global_db.table("filters")


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


def get_settings(database: str) -> TinyDB:
    settings_table = database.table("settings")
    settings = settings_table.all()
    logging.debug(f"Settings from DB: {settings}")
    config = settings[0]
    logging.debug(f"Settings Dictionary: {config}")
    return config


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


def make_min_max_prompt(
    message: str, default: float, min_val: float = 0.0, max_val: float = 2.0
) -> float:
    result = inquirer.text(
        message=f"{message}",
        default=str(default),
        filter=set_min_max,
        invalid_message=f"Please enter a number between {min_val} and {max_val}",
    ).execute()

    return float(result)


def set_min_max(value: float) -> float:
    value = float(value)
    if value < 0:
        return 0
    elif value > 2:
        return 2
    return value


def set_project(
    logger: logging, config: configparser.ConfigParser, args: argparse.Namespace
) -> tuple[TinyDB, str, dict]:
    settings = {}

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
        logger.warning("No projects found in config.ini")
        args.project = inquirer.text("Please enter a project name").execute()
        project_path = inquirer.text("Please the path for the project").execute()
        settings["description"] = inquirer.confirm(
            "Would you like to provide descriptions for visually impaired users?"
        ).execute()
        settings["flavor"] = inquirer.confirm(
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
                logging.exception(f"Error writing to config file: {e}")

    while not args.project or args.project == "Settings":
        project_choices = {"Settings": "Settings"}
        for name, path in projects.items():
            project_choices[f"{name} ({path})"] = name
        project_choice = inquirer.select(
            message="Select a project", choices=project_choices.keys()
        ).execute()
        args.project = project_choices[project_choice]
        if args.project == "Settings":
            settings = set_global_settings()
            while True:
                if not inquirer.confirm("Make a filter?").execute():
                    break
                updated = make_filter()
                if updated:
                    logger.info(f"""Filter "{updated}" settings saved.""")

    main_path = projects[args.project]
    db_path = f"{projects[args.project]}/db/"

    make_json_readable(f"{db_path}{args.project}.json")

    project_db = get_project_db(args.project, db_path)

    if not settings:
        settings = get_settings(project_db)

    if project_set_up:
        settings_table = project_db.table("settings")
        Settings = Query()
        settings_table.update(
            {
                "project_name": args.project,
                "project_path": projects[args.project],
                "description": settings.get("description"),
                "flavor": settings.get("flavor"),
            },
            Settings.id == 1,
        )

    return project_db, main_path, settings


def make_json_readable(json_file_path: str) -> str:
    # Read the JSON file
    with open(json_file_path, "r") as file:
        data = json.load(file)

    # Write the formatted JSON file
    with open(json_file_path, "w") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def make_filter():
    filter_name = inquirer.text("Enter a name for this filter").execute()
    global_db = get_global_db()
    filter_table = global_db.table("filters")
    Filter = Query()
    filter = filter_table.search(Filter.name == filter_name)
    logging.debug(f"Filter: {filter}")
    brightness = make_min_max_prompt(
        "Adjust brightness",
        filter[0].get("brightness", 1.0),
    )
    contrast = make_min_max_prompt("Adjust contrast", filter[0].get("contrast", 1.0))
    color = make_min_max_prompt("Adjust color", filter[0].get("color", 1.0))
    sharpness = make_min_max_prompt("Adjust sharpness", filter[0].get("sharpness", 1.0))

    updated = filter_table.upsert(
        {
            "name": filter_name,
            "brightness": brightness,
            "contrast": contrast,
            "color": color,
            "sharpness": sharpness,
        },
        Filter.name == filter_name,
    )

    if updated:
        return filter_name
    else:
        return False


def set_global_settings() -> None:
    settings = {}
    global_db = get_global_db()
    settings_table = global_db.table("settings")
    settings_doc = settings_table.get(doc_id=1)
    for setting in settings_table.all():
        settings["max_dimension"] = setting.get("max_dimension")
        settings["quality"] = setting.get("quality")
        settings["description"] = setting.get("description")
        settings["flavor"] = setting.get("flavor")

    settings["max_dimension"] = inquirer.text(
        message="Set maximum dimension for images",
        default=str(settings.get("max_dimension")),
    ).execute()
    settings["quality"] = inquirer.text(
        message="Set the quality level for compressed images",
        default=str(settings.get("quality")),
    ).execute()
    settings["description"] = inquirer.confirm(
        message="Would you like to provide descriptions for visually impaired users?",
        default=settings.get("description"),
    ).execute()
    settings["flavor"] = inquirer.confirm(
        message="Would you like to provide flavor text for the images?",
        default=settings.get("flavor"),
    ).execute()

    updated = settings_table.upsert(
        settings_doc,
        {
            "max_dimension": settings.get("max_dimension"),
            "quality": settings.get("quality"),
            "description": settings.get("description"),
            "flavor": settings.get("flavor"),
        },
    )
    logging.debug(f"Updated: {updated}")
    return settings


def update_event_posted(db, event_name, user, platform, uri, link):
    db.insert(
        {
            "event": event_name,
            "where": platform,
            "account": santitize_text(user),
            "date": pendulum.now().timestamp(),
            "link": link,
            "uri": uri,
        }
    )


def get_filter_from_values(
    filter_table: TinyDB,
    brightness: float,
    contrast: float,
    color: float,
    sharpness: float,
) -> str:
    for filter in filter_table.all():
        if (
            filter.get("brightness") == brightness
            and filter.get("contrast") == contrast
            and filter.get("color") == color
            and filter.get("sharpness") == sharpness
        ):
            return filter.get("name", "None")
    return "None"


def convert_to_relative_path(file_path: str, project_path: str) -> str:
    """Convert absolute path to relative path based on project directory."""
    try:
        return os.path.relpath(file_path, project_path)
    except ValueError:
        return file_path


def convert_to_absolute_path(relative_path: str, project_path: str) -> str:
    """Convert relative path to absolute path based on project directory."""
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.join(project_path, relative_path)


def find_events_with_photo(events_table: TinyDB, photo_path: str) -> list:
    """Find all events containing a specific photo."""
    events_with_photo = []
    for event in events_table.all():
        if photo_path in event.get("photos", []):
            events_with_photo.append(event)
    return events_with_photo


def handle_duplicate_events(
    events_table: TinyDB, events: list, photo_path: str
) -> None:
    """Handle events that contain the same photo."""
    if len(events) <= 1:
        return

    console = Console()
    console.print(
        f"\n[yellow]Warning:[/yellow] Photo {photo_path} appears in multiple events:"
    )
    for idx, event in enumerate(events, 1):
        console.print(
            f"{idx}. {event['event']} ({pendulum.from_timestamp(event['date']).format('YYYY-MM-DD')})"
        )

    keep_idx = inquirer.select(
        message="Which event should keep this photo?",
        choices=[str(i) for i in range(1, len(events) + 1)],
    ).execute()

    # Remove photo from all other events
    Event = Query()
    keep_event = events[int(keep_idx) - 1]
    for event in events:
        if event["event"] != keep_event["event"]:
            photos = event.get("photos", [])
            photos.remove(photo_path)
            events_table.update({"photos": photos}, Event.event == event["event"])


def main(args):
    # Basic initialization
    config = configparser.ConfigParser()
    console = Console()
    level = getattr(logging, args.log.upper())
    logging.basicConfig(level=level)
    logger = logging.getLogger(__name__)
    location_table = get_location_table()
    filter_table = get_filter_table()

    # Project initialization
    project_db, main_path, settings = set_project(logger, config, args)
    photos_path = f"{main_path}/photos"
    event_table = get_events_table(project_db)
    photos_table = get_photos_table(project_db)
    level = getattr(logging, args.log.upper())
    logging.basicConfig(level=level)

    logging.debug(f"Arguments: {args}")

    project_path = config["Projects"][args.project]
    non_hidden_files = list(get_non_hidden_files(photos_path))

    if non_hidden_files == [(None, None)]:
        logging.fatal(
            "No files found in the project folder's photos directory, please add photos before running."
        )
        return
    else:
        for dir, file in get_non_hidden_files(photos_path):
            date_object = None
            lat = None
            lon = None

            file_path = f"{dir}/{file}"
            relative_path = convert_to_relative_path(file_path, project_path)

            # Check for duplicates
            duplicate_events = find_events_with_photo(event_table, relative_path)
            if len(duplicate_events) > 1:
                handle_duplicate_events(event_table, duplicate_events, relative_path)

            console.print()
            console.print(f"[bold]Checking {file_path}[/bold]")
            need_to_convert_path = False
            photo_record = photos_table.get(where("path") == relative_path)
            if not photo_record:
                photo_record = photos_table.get(where("path") == file_path)
                need_to_convert_path = True
            if photo_record:
                rotation_angle = photo_record.get("rotation", 0)
                quality = photo_record.get("quality", settings.get("quality"))
                description = photo_record.get("description", "")
                flavor = photo_record.get("flavor", "")
                brightness = photo_record.get("brightness", 1.0)
                contrast = photo_record.get("contrast", 1.0)
                color = photo_record.get("color", 1.0)
                sharpness = photo_record.get("sharpness", 1.0)
            else:
                rotation_angle = 0
                quality = settings.get("quality")
                description = ""
                flavor = ""
                brightness = 1.0
                contrast = 1.0
                color = 1.0
                sharpness = 1.0
            if (args.view and not photo_record) or args.all:
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
                            filter["name"] for filter in filter_table.all()
                        ]
                        filter_choices.append("Custom")

                        filter_to_apply = inquirer.select(
                            message="Choose a filter",
                            choices=filter_choices,
                            default=get_filter_from_values(
                                filter_table, brightness, contrast, color, sharpness
                            ),
                        ).execute()

                        match filter_to_apply:
                            case "Custom":
                                brightness = make_min_max_prompt(
                                    "Adjust brightness", brightness
                                )
                                contrast = make_min_max_prompt(
                                    "Adjust contrast", contrast
                                )
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
                                filter = filter_table.get(
                                    where("name") == filter_to_apply
                                )
                                brightness = filter.get("brightness", 1.0)
                                contrast = filter.get("contrast", 1.0)
                                color = filter.get("color", 1.0)
                                sharpness = filter.get("sharpness", 1.0)

            if (settings.get("description") and not description) or args.all:
                description = inquirer.text(
                    message="Enter a description for visually impaired users about this image:",
                    default=description,
                ).execute()
            if (settings.get("flavor") and not flavor) or args.all:
                flavor = inquirer.text(
                    message="Enter flavor text for this image:",
                    default=flavor,
                ).execute()

            Photo = Query()

            if need_to_convert_path:
                photos_table.update(
                    {
                        "path": relative_path,
                        "rotation": rotation_angle,
                        "quality": quality,
                        "description": description,
                        "flavor": flavor,
                        "brightness": brightness,
                        "contrast": contrast,
                        "saturation": color,
                        "sharpness": sharpness,
                    },
                    Photo.path == file_path,
                )
            else:
                photos_table.upsert(
                    {
                        "path": relative_path,
                        "rotation": rotation_angle,
                        "quality": quality,
                        "description": description,
                        "flavor": flavor,
                        "brightness": brightness,
                        "contrast": contrast,
                        "saturation": color,
                        "sharpness": sharpness,
                    },
                    Photo.path == relative_path,
                )

            try:
                exif_tags = extract_exif_info(file_path)

                lat, lon = extract_gps(exif_tags)

                date_object = extract_datetime(exif_tags)
            except piexif.InvalidImageDataError:
                logging.warning("Invalid image data")
                continue
            except Exception as e:
                logging.info(f"Error extracting exif info: {e}")

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
                logging.debug(
                    "This item appears to be a duplicate and will be skipped."
                )
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
                if relative_path not in event.get("photos", []):
                    event_table.update(
                        {"photos": event.get("photos", []) + [relative_path]},
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
                        "photos": [relative_path],
                    }
                )

        make_json_readable(f"{project_path}/db/{args.project}.json")


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

    parser.add_argument(
        "--max_dimension",
        help="Set maximum dimension for images",
        default=1200,
    )

    parser.add_argument(
        "--quality",
        help="Set the quality level for compressed images",
        default=80,
    )

    parser.add_argument(
        "--all",
        "-a",
        help="Process all images in the project directory (default is to process only new ones)",
        action="store_true",
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
