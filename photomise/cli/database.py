import os
from json import dumps

import typer
from rich.table import Table

from photomise.database.shared import SharedDB
from photomise.utilities.logging import setup_logging
from photomise.utilities.project import set_project
from photomise.utilities.shared import format_file_size

app = typer.Typer()
logger, console = setup_logging()


@app.command()
def prettify(
    project: str = typer.Argument(None, help="Project name"),
):
    """Reformat JSON data to be more human-readable."""
    try:
        gdb = SharedDB()
        if project:
            pdb, _ = set_project(project)

        if project:
            pdb.close()
        else:
            gdb.close()

    except Exception as e:
        logger.fatal(f"Error: {e}")
        typer.Exit(1)


@app.command()
def stats(
    project: str = typer.Argument(None, help="Project name"),
    json: bool = typer.Option(False, "--json", help="Output stats as JSON"),
):
    """Print some stats about the database. If no project is specified, only stats for the shared DB are shown."""

    data = {}

    try:
        if project:
            pdb, _ = set_project(project)

        if project:
            folder_size = sum(
                os.path.getsize(os.path.join(dirpath, filename))
                for dirpath, _, filenames in os.walk(pdb.project_path)
                for filename in filenames
            )
            data[pdb.project_name] = {
                "project_path": pdb.project_path,
                "db_path": pdb.path,
                "db_size": (
                    os.path.getsize(pdb.path)
                    if json
                    else format_file_size(os.path.getsize(pdb.path))
                ),
                "project_folder_size": (
                    folder_size if json else format_file_size(folder_size)
                ),
                "photo_count": pdb.count_photos(),
                "event_count": pdb.count_events(),
                "ranking_count": pdb.count_rankings(),
                "post_count": pdb.count_posts(),
            }
            pdb.close()

        # Global stats
        gdb = SharedDB()
        data["shared"] = {
            "db_path": gdb.path,
            "db_size": (
                os.path.getsize(gdb.path)
                if json
                else format_file_size(os.path.getsize(gdb.path))
            ),
            "project_count": len(gdb.projects),
            "location_count": gdb.count_locations(),
            "filter_count": gdb.count_filters(),
        }
        if json:
            console.print(dumps(data, indent=4, ensure_ascii=False))
        else:
            table = Table(title="Database Statistics")

            # Add columns
            table.add_column("Database", style="cyan")
            table.add_column("Metric", style="magenta")
            table.add_column("Value", style="green")

            # Add rows
            for db_name, stats in data.items():
                for metric, value in stats.items():
                    table.add_row(db_name, metric.replace("_", " ").title(), str(value))

            console.print(table)

    except Exception as e:
        logger.fatal(f"Error: {e}")
        typer.Exit(1)
