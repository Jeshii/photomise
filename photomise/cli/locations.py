import InquirerPy as inquirer
from typer import Argument, Option, Typer

from photomise.database.shared import SharedDB
from photomise.utilities.logging import setup_logging

app = Typer()
logging, console = setup_logging()


@app.command()
def edit(
    location_name: str = Argument(..., help="Location name"),
    latitude: float = Option(None, "--latitude", "-lat", help="Latitude"),
    longitude: float = Option(None, "--longitude", "-lon", help="Longitude"),
    rename: bool = Option(False, "--rename", "-r", help="Rename location"),
    list: bool = Option(False, "--list", "-l", help="List all locations"),
):
    """Edit location settings."""
    gdb = SharedDB()
    if rename:
        location_name = inquirer.text(
            "Enter a name for this location", default=location_name
        ).execute()
    location = gdb.get_location(location_name)

    # Get all fields except 'name' from first record
    fields = {}
    if location:
        fields = {k: v for k, v in location[0].items() if k != "name"}
    else:
        fields = location.all()[0]

    if not fields:
        raise ValueError("No locations found - please run photomise process first.")

    # Build updated fields dictionary
    updated_fields = {"name": location_name}
    for field_name, default_value in fields.items():
        value = inquirer.text(
            f"Enter the {field_name} for this location",
            default=str(default_value),
        ).execute()
        updated_fields[field_name] = float(value)

    updated = gdb.upsert_location(updated_fields)
    return updated
