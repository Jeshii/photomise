#!/usr/bin/env python3

import configparser
import logging
import os

from InquirerPy import inquirer
from typer import Argument, Option, Typer

from ..utilities.constants import CONFIG_FILE
from ..utilities.logging import setup_logging
from ..utilities.project import fix_dir, get_project_db, sanitize_text
from . import database, post, process, settings

app = Typer(help="Photomise - Photo processing for social media posting")
app.add_typer(settings.app, name="settings", help="Change global settings.")
app.add_typer(
    post.app, name="post", help="Post photos/videos to various social media platforms."
)
app.add_typer(database.app, name="database", help="Tools for the database.")
app.add_typer(
    process.app,
    name="process",
    help="Pre-process the photos in preparation for posting.",
)

# Basic initialization
config = configparser.ConfigParser()
logger, console = setup_logging()


@app.command()
def init(
    project: str = Argument(..., help="Project name"),
    project_path: str = Option(None, "--path", "-p", help="Path to project"),
    description: bool = Option(
        False,
        "--description",
        "-d",
        help="Provide descriptions for visually impaired users",
    ),
    flavor: bool = Option(
        False, "--flavor", "-f", help="Provide flavor text for assets"
    ),
):
    """Initialize a new project."""
    settings = {}

    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)

    if not config.has_section("Projects"):
        config["Projects"] = {}

    config_dict = {
        section: dict(config.items(section)) for section in config.sections()
    }

    projects = config_dict.get("Projects", {})

    if project in projects.keys():
        logger.error(f"Project {project} already exists in config.ini")
        return
    logger.info(f"Adding {project} to config.ini")

    if not project_path:
        project_path = inquirer.text("Please the path for the project").execute()
    if description:
        settings["description"] = True
    else:
        settings["description"] = inquirer.confirm(
            "Would you like to provide descriptions for visually impaired users?"
        ).execute()
    if flavor:
        settings["flavor"] = True
    else:
        settings["flavor"] = inquirer.confirm(
            "Would you like to provide flavor text for the assets?"
        ).execute()

    project_path = fix_dir(project_path)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
    if not os.path.exists(f"{project_path}/db"):
        os.makedirs(f"{project_path}/db")
    if not os.path.exists(f"{project_path}/assets"):
        os.makedirs(f"{project_path}/assets")
    project = sanitize_text(project.lower())
    projects[project] = project_path
    try:
        config["Projects"] = projects
    except Exception as e:
        logger.debug(
            "Error updating config file", exc_info=True
        )  # Full traceback in debug log
        console.print(f"[red]Error updating config file: {e}")  # User-friendly message
        return
    with open(CONFIG_FILE, "w", encoding="utf-8") as configfile:
        try:
            config.write(configfile)
        except IOError as e:
            logging.exception(f"Error writing to config file: {e}")
    pdb = get_project_db(project, project_path)

    settings = {
        "project_name": project,
        "project_path": projects[project],
        "description": settings.get("description"),
        "flavor": settings.get("flavor"),
    }
    pdb.upsert_settings(settings)

    return pdb, projects[project]


@app.callback()
def main():
    """
    Photomise - Photo processing for social media posting.
    """


if __name__ == "__main__":
    app()
