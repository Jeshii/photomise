import pendulum
import piexif
from InquirerPy import inquirer
from typer import Argument, Option, Typer

from ..database.shared import SharedDB
from ..utilities.exif import (
    compress_image,
    convert_to_degrees,
    deg_to_dms_rational,
    extract_datetime,
    extract_exif_info,
    extract_gps,
)
from ..utilities.logging import setup_logging
from ..utilities.project import (
    convert_to_relative_path,
    get_non_hidden_files,
    handle_duplicate_events,
    item_duplicate,
    sanitize_text,
    set_project,
)
from ..utilities.shared import make_min_max_prompt

logging, console = setup_logging()

app = Typer()


@app.command()
def photos(
    project: str = Argument(..., help="Project name"),
    view: bool = Option(False, "--view", "-v", help="View files before processing"),
    all: bool = Option(
        False,
        "--all",
        "-a",
        help="Process all files whether they've been processed previously or not",
    ),
    link: str = Option(
        None,
        "--link",
        "-l",
        help="Helper link to append to latitude and longitude to help find location",
    ),
):
    """Process photos by grouping into locations, events, and apply filters."""

    # Project initialization
    pdb, main_path = set_project(project)
    logging.debug(f"Project: {project}, Path: {main_path}, Settings: {pdb.settings}")
    gdb = SharedDB()
    photos_path = f"{main_path}/assets"

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
            relative_path = convert_to_relative_path(file_path, main_path)

            # Check for duplicates
            duplicate_events = pdb.find_events_with_photo(relative_path)
            if len(duplicate_events) > 1:
                handle_duplicate_events(pdb, duplicate_events, relative_path)

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
            if (view and not photo_record) or all:
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
                location_name = gdb.find_location(lat, lon)
                if location_name:
                    console.print(f"Location: {location_name}")
                else:
                    if link:
                        console.print(f"[link={link}{lat},{lon}]Helper link[/link]")
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
                        location_name = gdb.get_location_coord(lat, lon)
                        if location_name:
                            console.print(f"Location: {location_name}")
                        else:
                            if link:
                                console.print(
                                    f"[link={link}{lat},{lon}]Helper link[/link]"
                                )
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
                    except Exception:
                        console.print("Error adding GPS info")
                        logging.exception("Error adding GPS info")
                        continue
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
                logging.debug(
                    "This item appears to be a duplicate and will be skipped."
                )
                continue

            if pdb.settings.get("auto_event"):
                location_name_sanitized = sanitize_text(location_name)
                event_name = (
                    f"{event_date.format('YYYYMMDD')}-{location_name_sanitized}"
                )
            else:
                event_name = inquirer.text(
                    f"Please name this event from {event_date.format('YYYY-MM-DD')} at {location_name}"
                ).execute()

            if event_same:
                logging.debug(
                    "This event appears to be a duplicate and will be skipped."
                )
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
def videos():
    """Process videos by grouping into locations, events, and apply filters."""
    console.print("To be implemented")
