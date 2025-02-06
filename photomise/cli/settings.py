from InquirerPy import inquirer
from typer import Typer

from photomise import filters, locations
from photomise.database.shared import SharedDB
from photomise.utilities.logging import setup_logging

app = Typer()
app.add_typer(filters.app, name="filters", help="Filter settings")
app.add_typer(locations.app, name="locations", help="Location settings")

logging, console = setup_logging()


@app.command()
def interactive():
    """Edit global settings via an interactive menu."""
    gdb = SharedDB()
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
