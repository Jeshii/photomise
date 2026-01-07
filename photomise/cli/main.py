#!/usr/bin/env python3

import os

import typer

from photomise.cli import database, post, process, settings
from photomise.utilities.logging import setup_logging
import logging as _logging
from photomise.utilities.project import fix_dir, get_project_db, sanitize_text

app = typer.Typer(help="Photomise - Photo processing for social media posting")
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

# Basic initialization with default console level
logger = setup_logging()


@app.command()
def init(
    project: str = typer.Argument(..., help="Project name"),
    project_path: str = typer.Option(None, "--path", "-p", prompt="Path to project"),
    description: bool = typer.Option(
        False,
        "--description",
        "-d",
        prompt="Provide alt text",
    ),
    flavor: bool = typer.Option(
        False, "--flavor", "-f", prompt="Provide flavor text for assets"
    ),
    tags: bool = typer.Option(
        False,
        "--tags",
        "-t",
        prompt="Provide tags for assets",
    ),
    event_radius_meters: int = typer.Option(
        500, "--radius", "-r", help="Event radius in meters for grouping photos"
    ),
    event_time_delta_hours: int = typer.Option(
        8,
        "--time-delta",
        "-D",
        help="Max hours between photos to consider them part of the same event",
    ),
):
    """Initialize a new project."""
    settings = {}
    try:
        gdb = database.SharedDB()
    except Exception as e:
        logger.fatal(e)
        typer.Exit(1)

    projects = gdb.projects

    if project in projects.keys():
        logger.error(f"Project {project} already exists in global database.")
        typer.Exit(1)

    logger.info(f"Adding {project} to global database.")

    if not project_path:
        logger.fatal("Project path not provided. Please provide a path to the project.")
        typer.exit(1)

    project_path = fix_dir(project_path)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
    if not os.path.exists(f"{project_path}/db"):
        os.makedirs(f"{project_path}/db")
    if not os.path.exists(f"{project_path}/assets"):
        os.makedirs(f"{project_path}/assets")
    project = sanitize_text(project.lower())
    projects[project] = project_path
    # Shared DB should only contain minimal project info for portability.
    shared_params = {"name": project, "path": project_path}
    gdb.upsert_project(shared_params)

    pdb = get_project_db(project, project_path)

    settings = {
        "name": project,
        "path": projects[project],
        "description": description,
        "flavor": flavor,
        "tags": tags,
        "event_time_delta_hours": event_time_delta_hours,
        # Store event radius in project DB for portability - keep consistent
        # with the project-local settings design.
        "event_radius_meters": event_radius_meters,
    }
    # Store per-project settings (time delta etc.).
    pdb.insert_settings(settings)

    # If the shared upsert contained extra keys previously, ensure any
    # leftover keys are migrated into the project DB for consistency.
    try:
        gdb.migrate_project_settings(
            project,
            {
                "event_radius_meters": event_radius_meters,
                "event_time_delta_hours": event_time_delta_hours,
            },
        )
    except Exception:
        # Non-fatal: ignore migration errors
        pass

    logger.info(f"Project {project} initialized at {project_path}.")


@app.callback()
def main(
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Console log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
):
    """Photomise - Photo processing for social media posting."""
    # Map provided log level to logging constant and reconfigure console handler
    level_name = (log_level or "INFO").upper()
    level = getattr(_logging, level_name, None)
    if level is None or not isinstance(level, int):
        raise typer.BadParameter(f"Invalid log level: {log_level}")
    # Re-initialize logging with chosen console level
    setup_logging(console_level=level)


if __name__ == "__main__":
    app()
