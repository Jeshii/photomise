import InquirerPy as inquirer
import typer

from photomise.database.shared import SharedDB
from photomise.utilities.logging import setup_logging
from photomise.utilities.shared import make_min_max_prompt, min_max_check

logging, console = setup_logging()
app = typer.Typer()


@app.command()
def edit(
    filter_name: str = typer.Argument(..., help="Filter name"),
    brightness: float = typer.Option(None, "--brightness", "-b", help="Brightness"),
    contrast: float = typer.Option(None, "--contrast", "-con", help="Contrast"),
    color: float = typer.Option(None, "--color", "-col", help="Color"),
    sharpness: float = typer.Option(None, "--sharpness", "-s", help="Sharpness"),
    rename: bool = typer.Option(False, "--rename", "-r", help="Rename filter"),
    delete: bool = typer.Option(False, "--delete", "-d", help="Delete filter"),
):
    """Edit filter settings."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logging.fatal(f"Error: {e}")
        typer.Exit(1)
    filter = gdb.get_filter(filter_name)
    logging.debug(f"Filter: {filter}")
    if not filter:
        filter = {
            "brightness": 1.0,
            "contrast": 1.0,
            "color": 1.0,
            "sharpness": 1.0,
        }

    if not min_max_check(brightness):
        brightness = make_min_max_prompt(
            "Adjust brightness:",
            filter.get("brightness", 1.0),
        )
    if not min_max_check(contrast):
        contrast = make_min_max_prompt("Adjust contrast:", filter.get("contrast", 1.0))
    if not min_max_check(color):
        color = make_min_max_prompt("Adjust color:", filter.get("color", 1.0))
    if not min_max_check(sharpness):
        sharpness = make_min_max_prompt(
            "Adjust sharpness:", filter.get("sharpness", 1.0)
        )
    params = {
        "name": filter_name,
        "brightness": brightness,
        "contrast": contrast,
        "color": color,
        "sharpness": sharpness,
    }
    updated = gdb.upsert_filter(params)

    return updated


@app.command()
def delete(
    filter_name: str = typer.Argument(None, help="Filter name"),
):
    try:
        gdb = SharedDB()
    except Exception as e:
        logging.fatal(f"Error: {e}")
        return
    if not filter_name:
        filter_name = inquirer.select(
            message="Select a filter to delete:",
            choices=[filter["name"] for filter in gdb.get_filters_all()],
        ).execute()
    gdb.delete_filter(filter_name)
    return


@app.command()
def list():
    """List all filters."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logging.fatal(f"Error: {e}")
        return
    filters = gdb.get_filters_all()
    for filter in filters:
        console.print(f"[bold]{filter['name']}:[/bold]")
        console.print(f"\tBrightness: {filter['brightness']}")
        console.print(f"\tContrast: {filter['contrast']}")
        console.print(f"\tColor: {filter['color']}")
        console.print(f"\tSharpness: {filter['sharpness']}")
