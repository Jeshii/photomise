import configparser
import os
from urllib.parse import quote

from InquirerPy import inquirer

from ..database.project import ProjectDB
from .constants import CONFIG_FILE
from .logging import setup_logging

config = configparser.ConfigParser()
logging = setup_logging()


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
    return quote(text.lower().strip().replace(" ", "_"))


def item_duplicate(pdb, gdb, date_object, lat, lon):
    return pdb.is_event(date_object) and gdb.is_location(lat, lon)


def fix_dir(current):
    return current.replace("\\", "").strip()


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

    main_path = projects[sanitize_text(project)]
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
