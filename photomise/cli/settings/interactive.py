from cli import settings_app
from InquirerPy import inquirer
from settings import filters, locations

from ...database.shared import SharedDB
from ...utilities.logging import setup_logging

logging, console = setup_logging()


@settings_app.command()
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
