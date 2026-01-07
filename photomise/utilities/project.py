import os

import pendulum
import typer
from typer import prompt, confirm
from InquirerPy import inquirer

from photomise.database.project import ProjectDB
from photomise.database.shared import SharedDB
from photomise.utilities.event import Event
from photomise.utilities.location import sanitize_text
from photomise.utilities.logging import setup_logging

logger = setup_logging()


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


def item_duplicate(pdb, gdb, date_object, lat, lon):
    return pdb.is_event(date_object) and gdb.is_location(lat, lon)


def fix_dir(current):
    return os.path.normpath(current).strip()


def set_project(
    project: str,
):
    """Get project information from global DB and return project database and path."""

    if os.path.exists(project):
        pdb = ProjectDB(project_path=project)
        main_path = project
    else:
        try:
            gdb = SharedDB()
        except Exception as e:
            logger.fatal(e)
            typer.Exit(1)

        projects = gdb.projects

        if not projects:
            logger.fatal(
                "No projects found in global database - please run photomise init."
            )
            exit(1)

        sanitized_project_name = sanitize_text(project.lower())
        if sanitized_project_name not in projects:
            logger.fatal(
                f"Project '{project}' not found in global database - please run photomise init."
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

    settings["max_dimension"] = prompt(
        "Set maximum dimension for images",
        default=str(settings.get("max_dimension")),
    )
    settings["quality"] = prompt(
        "Set the quality level for compressed images",
        default=str(settings.get("quality")),
    )
    settings["description"] = confirm(
        "Would you like to provide alt text?",
        default=bool(settings.get("description")),
    )
    settings["flavor"] = confirm(
        "Would you like to provide flavor text for the images?",
        default=bool(settings.get("flavor")),
    )

    updated = pdb.upsert_settings(
        {
            "max_dimension": settings.get("max_dimension"),
            "quality": settings.get("quality"),
            "description": settings.get("description"),
            "flavor": settings.get("flavor"),
        },
        document=setting_doc,
    )
    logger.debug(f"Updated: {updated}")
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


def handle_duplicate_events(
    pdb: ProjectDB, events: list[Event], photo_path: str
) -> None:
    """
    Handle events that contain the same photo.

    Args:
        pdb (ProjectDB): The project database instance.
        events (list): A list of events containing the photo.
        photo_path (str): The path to the photo that appears in multiple events.

    Returns:
        None
    """
    all_same = True
    for idx, event in enumerate(events, 1):
        if event.name == events[0].name:
            continue
        else:
            all_same = False

    if all_same:
        # If all events are the same, merge them
        master_event = events[0]
        for event in events[1:]:
            # prevent duplicate photos
            for photo in event.photos:
                if photo not in master_event.photos:
                    master_event.photos.append(photo)
            pdb.remove_event(event)
        pdb.upsert_event(master_event)
        logger.warning(
            f"Photo {photo_path} appeared in multiple events and thus the events were merged."
        )
    else:
        logger.warning(
            f"Photo {photo_path} appears in multiple events..."
        )
        for idx, event in enumerate(events, 1):
            local_date = (
                pendulum.from_timestamp(event.date)
                .in_tz(pendulum.local_timezone())
                .format("YYYY-MM-DD")
            )
            logger.info(f"{idx}. {event.name} ({local_date})")

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
            logger.error("Invalid selection. No event will be updated.")
            return

        keep_event = events[int(keep_idx) - 1]
        for event in events:
            if event.name != keep_event.name:
                pdb.remove_photo_from_event(event, photo_path)
