#!/usr/bin/env python3

import os

import typer

from photomise.cli import database, post, process, settings
from photomise.utilities.logging import setup_logging
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

# Basic initialization
logger, console = setup_logging()


@app.command()
def init(
    project: str = typer.Argument(..., help="Project name"),
    project_path: str = typer.Option(None, "--path", "-p", prompt="Path to project"),
    description: bool = typer.Option(
        False,
        "--description",
        "-d",
        prompt="Provide descriptions for visually impaired users",
    ),
    flavor: bool = typer.Option(
        False, "--flavor", "-f", prompt="Provide flavor text for assets"
    ),
):
    """Initialize a new project."""
    settings = {}
    try:
        gdb = database.SharedDB()
    except Exception as e:
        logger.fatal(f"Error: {e}")
        typer.Exit(1)

    projects = gdb.proejcts

    if project in projects.keys():
        logger.error(f"Project {project} already exists in global database.")
        return
    logger.info(f"Adding {project} to global database.")

    project_path = fix_dir(project_path)
    if not os.path.exists(project_path):
        os.makedirs(project_path)
    if not os.path.exists(f"{project_path}/db"):
        os.makedirs(f"{project_path}/db")
    if not os.path.exists(f"{project_path}/assets"):
        os.makedirs(f"{project_path}/assets")
    project = sanitize_text(project.lower())
    projects[project] = project_path
    gdb.upsert_project(project, project_path, description, flavor)
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
