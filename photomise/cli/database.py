import os
import xml.etree.ElementTree as ET
from json import dumps
from xml.dom import minidom

import pendulum
import typer
from rich.table import Table

from photomise.database.shared import SharedDB
from photomise.utilities.constants import LOG_DIR
from photomise.utilities.event import Event
from photomise.utilities.logging import setup_logging
from photomise.utilities.project import convert_to_absolute_path, set_project
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
        log_size = sum(
            os.path.getsize(os.path.join(dirpath, filename))
            for dirpath, _, filenames in os.walk(LOG_DIR)
            for filename in filenames
        )
        data["shared"] = {
            "db_path": os.path.abspath(gdb.path),
            "db_size": (
                os.path.getsize(gdb.path)
                if json
                else format_file_size(os.path.getsize(gdb.path))
            ),
            "log_path": os.path.abspath(LOG_DIR),
            "log_size": log_size if json else format_file_size(log_size),
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


@app.command("export-gpx")
def export_gpx(
    project: str = typer.Argument(..., help="Project name or path"),
    event: str = typer.Option(
        None, "--event", "-e", help="Specific event name to export"
    ),
    output: str = typer.Option(
        ".", "--output", "-o", help="Output GPX file or directory"
    ),
):
    """Export events as a GPX file. If `--event` is provided, export only that event."""

    try:
        pdb, project_path = set_project(project)
    except Exception as e:
        logger.fatal(f"Error: {e}")
        raise typer.Exit(1)

    # Gather events
    if event:
        ev = pdb.get_event(event)
        if not ev:
            logger.fatal(f"Event {event} not found in project {pdb.project_name}")
            raise typer.Exit(1)
        events = {ev.name: ev}
    else:
        events = pdb.get_events()

    if not events:
        logger.fatal("No events found to export.")
        raise typer.Exit(1)

    # Build GPX
    gpx = ET.Element("gpx", version="1.1", creator="photomise")

    for name, ev in events.items():
        # Use waypoint for event
        if ev.latitude and ev.longitude:
            wpt = ET.SubElement(gpx, "wpt", lat=str(ev.latitude), lon=str(ev.longitude))
            name_el = ET.SubElement(wpt, "name")
            name_el.text = ev.name
            time_el = ET.SubElement(wpt, "time")
            try:
                time_el.text = pendulum.from_timestamp(ev.date).to_iso8601_string()
            except Exception:
                time_el.text = str(ev.date)
            desc_el = ET.SubElement(wpt, "desc")
            desc_el.text = ev.location or ""

    # Pretty print
    rough_string = ET.tostring(gpx, "utf-8")
    reparsed = minidom.parseString(rough_string)
    pretty = reparsed.toprettyxml(indent="  ")

    # Determine output path
    if output.endswith(".gpx") or output.endswith(".GPX"):
        out_file = output
    else:
        out_file = f"{output.rstrip('/')}/{pdb.project_name}.gpx"

    with open(out_file, "w", encoding="utf-8") as fh:
        fh.write(pretty)

    console.print(f"Exported {len(events)} event(s) to {out_file}")
