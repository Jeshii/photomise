import typer
from InquirerPy import inquirer

from photomise.cli import filters, locations
from photomise.database.shared import SharedDB
from photomise.utilities.logging import setup_logging
from photomise.utilities.project import get_project_db

app = typer.Typer()
app.add_typer(filters.app, name="filters", help="Filter settings")
app.add_typer(locations.app, name="locations", help="Location settings")

logger, console = setup_logging()


@app.command()
def project(
    project: str = typer.Argument(..., help="Project name"),
    project_path: str = typer.Option(None, "--path", "-p", help="Path to project"),
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
):
    """Edit settings for an existing project."""
    project_settings = {}
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(f"Error: {e}")
        typer.Exit(1)

    projects = gdb.projects

    if project not in projects.keys():
        logger.error(f"Project {project} not found in global database.")
        typer.Exit(1)

    if not project_path:
        project_path = projects[project]

    if project_path != projects[project]:
        logger.warning(f"Updating project path for {project}.")
        gdb.upsert_project(project, project_path)

    pdb = get_project_db(project, project_path)

    project_settings = {
        "name": project,
        "path": projects[project],
        "description": description,
        "flavor": flavor,
        "tags": tags,
    }
    result = pdb.update_settings(project_settings)

    logger.info(f"Settings for {project}: {result}")

    pdb.close()
    gdb.close()


@app.command()
def interactive():
    """Edit global settings via an interactive menu."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(f"Error: {e}")
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
            console.print(f"""{setting.title()} "{updated}" settings saved.""")
        else:
            console.print(f"""Error saving {setting} settings.""")
