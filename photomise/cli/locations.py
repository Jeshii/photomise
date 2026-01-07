from typer import Argument, Option, Typer, prompt, confirm

from rich.console import Console

from photomise.database.shared import SharedDB
from photomise.utilities.logging import setup_logging
from photomise.utilities.location import Location

app = Typer()
logger = setup_logging()


@app.command()
def edit(
    location_name: str = Argument(..., help="Location name"),
    latitude: float = Option(None, "--latitude", "-lat", help="Latitude"),
    longitude: float = Option(None, "--longitude", "-lon", help="Longitude"),
    rename: bool = Option(False, "--rename", "-r", help="Rename location"),
):
    """Edit location settings interactively."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(e)
        return

    if rename:
        location_name = prompt("Enter a name for this location", default=location_name)

    loc = gdb.get_location(location_name)
    if not loc:
        raise ValueError("Location not found - please run photomise process first.")

    # Prompt for new latitude/longitude (default to existing values)
    latitude = float(prompt("Enter latitude", default=str(loc.latitude)))
    longitude = float(prompt("Enter longitude", default=str(loc.longitude)))

    # Build Location and persist
    updated_location = Location(
        latitude=latitude,
        longitude=longitude,
        _name=location_name,
    )

    updated = gdb.upsert_location(updated_location)
    if updated:
        logger.info(f"Updated location {location_name}")
    else:
        logger.error("Failed to update location")
    return updated


@app.command("list")
def list_locations():
    """List all known locations."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(e)
        return

    records = gdb.get_locations_all()
    console = Console()
    if not records:
        console.print("No locations found.")
        return

    # Simple table output
    from rich.table import Table

    table = Table(title="Locations")
    table.add_column("Name")
    table.add_column("Latitude")
    table.add_column("Longitude")

    for r in records:
        name = r.get("name") or ""
        table.add_row(
            name,
            str(r.get("latitude", "")),
            str(r.get("longitude", "")),
        )

    console.print(table)
