import typer
from InquirerPy import inquirer

from photomise.cli import filters, locations
from photomise.database.shared import SharedDB
from photomise.utilities.logging import setup_logging
from photomise.utilities.project import get_project_db

app = typer.Typer()
app.add_typer(filters.app, name="filters", help="Filter settings")
app.add_typer(locations.app, name="locations", help="Location settings")

logger = setup_logging()


@app.command()
def project(
    project: str = typer.Argument(..., help="Project name"),
    project_path: str = typer.Option(None, "--path", "-p", help="Path to project"),
    base_dir: str = typer.Option(
        None,
        "--base-dir",
        "-b",
        help="Base directory for assets (overrides project path)",
        show_default=False,
    ),
    description: bool = typer.Option(
        False,
        "--description",
        "-d",
        prompt="Provide alt text for assets",
    ),
    flavor: bool = typer.Option(
        False, "--flavor", "-f", prompt="Provide flavor text for assets"
    ),
    tags: bool = typer.Option(
        False,
        "--tags",
        "-t",
        prompt="Provide tags for events",
    ),
    event_radius_meters: int = typer.Option(
        None, "--radius", "-r", help="Event grouping radius in meters"
    ),
    event_time_delta_hours: int = typer.Option(
        None, "--time-delta", "-D", help="Max hours between photos in same event"
    ),
):
    """Edit settings for an existing project."""
    project_settings = {}
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(e)
        typer.Exit(1)

    projects = gdb.projects

    if project not in projects.keys():
        logger.error(f"Project {project} not found in global database.")
        typer.Exit(1)

    if not project_path:
        project_path = projects[project]

    # If base_dir provided, use it as the project path (after normalizing)
    if base_dir:
        project_path = base_dir

    if project_path != projects[project]:
        logger.warning(f"Updating project path for {project}.")
        params = {"name": project, "path": project_path}
        gdb.upsert_project(params)

    pdb = get_project_db(project, project_path)

    project_settings = {
        "name": project,
        "path": projects[project],
        "description": description,
        "flavor": flavor,
        "tags": tags,
    }

    # Only include optional settings if provided
    if event_time_delta_hours is not None:
        project_settings["event_time_delta_hours"] = event_time_delta_hours

    # Store radius and time-delta in the per-project DB for portability.
    if event_radius_meters is not None:
        project_settings["event_radius_meters"] = event_radius_meters

    result = pdb.update_settings(project_settings)

    logger.info(f"Settings for {project}: {result}")

    # Inform the user where to place photos for processing
    assets_path = f"{project_path}/assets"
    logger.info(
        f"\nTo process photos for project '{project}', place images under: [bold]{assets_path}[/bold]"
    )

    pdb.close()
    gdb.close()


@app.command()
def interactive():
    """Edit global settings via an interactive menu."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(e)
        typer.Exit(1)
    setting_choices = {
        "Filters": "filters",
        "Locations": "locations",
        "Exit": "exit",
    }
    items = {}
    setting_select = inquirer.select(
        message="Select a setting to edit:", choices=setting_choices.keys()
    ).execute()
    setting = setting_choices[setting_select]
    while True:
        if setting == "exit":
            gdb.close()
            exit(0)

        items = gdb.get_items(gdb.get_table(setting))
        items["Make New " + setting[:-1].title()] = ""
        items["Exit"] = "exit"

        choice = inquirer.select(
            message=f"Select a {setting[:-1]} to edit:",
            choices=items.keys(),
        ).execute()

        if items.get(choice) == "exit":
            break

        selection = items.get(choice)

        if setting == "filters":
            updated = filters.edit(filter_name=selection, rename=True)
        else:
            updated = locations.edit(location_name=selection, rename=True)

        if updated:
            logger.info(f"{setting.title()} \"{updated}\" settings saved.")
        else:
            logger.error(f"Error saving {setting} settings.")

    @app.command()
    def clean_radius(
        project: str = typer.Argument(..., help="Project name"),
        project_path: str = typer.Option(None, "--path", "-p", help="Path to project"),
    ):
        """Remove event_radius_meters from per-project settings (keep shared-only)."""
        try:
            gdb = SharedDB()
        except Exception as e:
            logger.fatal(e)
            typer.Exit(1)

        projects = gdb.projects

        if project not in projects.keys():
            logger.error(f"Project {project} not found in global database.")
            typer.Exit(1)

        if not project_path:
            project_path = projects[project]

        pdb = get_project_db(project, project_path)

        settings = pdb.settings or {}
        if settings.get("event_radius_meters") is not None:
            settings.pop("event_radius_meters", None)
            pdb.update_settings(settings)
            logger.info(f"Removed event_radius_meters from project settings for {project}")
        else:
            logger.info(f"No event_radius_meters found in project settings for {project}")

        pdb.close()
        gdb.close()

    @app.command()
    def migrate_shared(project: str = typer.Argument(..., help="Project name")):
        """Migrate any project-specific keys from the shared DB into the per-project DB."""
        try:
            gdb = SharedDB()
        except Exception as e:
            logger.fatal(e)
            typer.Exit(1)

        shared_proj = gdb.get_project(project)
        if not shared_proj:
            logger.info(f"No shared project entry found for {project}")
            gdb.close()
            return

        # Copy any keys other than name/path into the project DB
        extras = {k: v for k, v in shared_proj.items() if k not in ("name", "path")}
        if not extras:
            logger.info(f"No project-specific keys present in shared DB for {project}")
            gdb.close()
            return

        try:
            gdb.migrate_project_settings(project, extras)
            logger.info(
                f"Migrated keys into project DB for {project}: {', '.join(extras.keys())}"
            )
        except Exception as e:
            logger.error(f"Migration failed: {e}")

        gdb.close()
