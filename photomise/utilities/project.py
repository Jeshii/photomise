import configparser
import os
from urllib.parse import quote

import pendulum
from InquirerPy import inquirer
from photomise.utilities.constants import CONFIG_FILE
from photomise.utilities.logging import setup_logging

from photomise.database.project import ProjectDB

config = configparser.ConfigParser()
logging, console = setup_logging()


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


def sanitize_text(text: str = "") -> str:
    return quote(text.strip().replace(" ", "_"))


def item_duplicate(pdb, gdb, date_object, lat, lon):
    return pdb.is_event(date_object) and gdb.is_location(lat, lon)


def fix_dir(current):
    return os.path.normpath(current).strip()


def set_project(
    project: str,
):
    """Get project information from config.ini and return project database and path."""
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)

    if not config.has_section("Projects"):
        config["Projects"] = {}

    config_dict = {
        section: dict(config.items(section)) for section in config.sections()
    }

    projects = config_dict.get("Projects", {})

    if not projects:
        logging.fatal("No projects found in config.ini - please run photomise init.")
        exit(1)

    sanitized_project_name = sanitize_text(project.lower())
    if sanitized_project_name not in projects:
        logging.fatal(
            f"Project '{project}' not found in config.ini - please run photomise init."
        )
        exit(1)
    main_path = projects[sanitized_project_name]
    pdb = get_project_db(project, main_path)

    return pdb, main_path


def get_project_db(project_name: str, project_path: str) -> ProjectDB:
    return ProjectDB(project_name, project_path)


def set_project_settings(pdb: ProjectDB) -> None:
    settings = {}
    setting_doc = pdb.settings

    settings["max_dimension"] = setting_doc.get("max_dimension")
    settings["quality"] = setting_doc.get("quality")
    settings["description"] = setting_doc.get("description")
    settings["flavor"] = setting_doc.get("flavor")

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

    updated = pdb.upsert_settings(
        {
            "max_dimension": settings.get("max_dimension"),
            "quality": settings.get("quality"),
            "description": settings.get("description"),
            "flavor": settings.get("flavor"),
        },
        document=setting_doc,
    )
    logging.debug(f"Updated: {updated}")
    return settings


def get_non_hidden_files(directory: str):
    found_non_hidden_files = False
    for entry in os.scandir(directory):
        if (
            entry.is_file()
            and not entry.name.startswith(".")
            and not entry.name.startswith("~")
        ):
            found_non_hidden_files = True
            yield directory, entry.name
        elif entry.is_dir():
            yield from get_non_hidden_files(entry.path)
    if not found_non_hidden_files:
        yield None, None


def handle_duplicate_events(pdb: ProjectDB, events: list, photo_path: str) -> None:
    """
    Handle events that contain the same photo.

    Args:
        pdb (ProjectDB): The project database instance.
        events (list): A list of events containing the photo.
        photo_path (str): The path to the photo that appears in multiple events.

    Returns:
        None
    """

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

    if (
        keep_idx is None
        or not keep_idx.isdigit()
        or int(keep_idx) < 1
        or int(keep_idx) > len(events)
    ):
        logging.error("Invalid selection. No event will be updated.")
        return

    pdb.remove_photo_from_event(events, photo_path, int(keep_idx))
