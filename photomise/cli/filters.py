import typer
from typer import prompt
from InquirerPy import inquirer

from photomise.database.shared import SharedDB
from photomise.utilities.logging import setup_logging
from photomise.utilities.shared import make_min_max_prompt, min_max_check

logger = setup_logging()
app = typer.Typer()


@app.command()
def edit(
    filter_name: str = typer.Argument(..., help="Filter name"),
    brightness: float | None = typer.Option(None, "--brightness", "-b", help="Brightness"),
    contrast: float | None = typer.Option(None, "--contrast", "-con", help="Contrast"),
    color: float | None = typer.Option(None, "--color", "-col", help="Color"),
    sharpness: float | None = typer.Option(None, "--sharpness", "-s", help="Sharpness"),
    name: str | None = typer.Option(
        None, "--name", "-n", help="Provide a new name for the filter (non-interactive)"
    ),
):
    """Edit filter settings."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(e)
        typer.Exit(1)
    # Handle rename first: prefer --new-name if provided, otherwise prompt when --rename set
    # Only treat new_name as provided when it's a real string (avoid Typer's OptionInfo defaults)
    if isinstance(name, str) and name:
        try:
            rename_result = gdb.rename_filter(filter_name, name)
            if not rename_result:
                logger.error(f"Unable to rename filter {filter_name}.")
                return
            filter_name = rename_result
            logger.info(f"Filter renamed to {filter_name}")
        except Exception as e:
            logger.error(f"Rename failed: {e}")
            return

    filter = gdb.get_filter(filter_name)
    logger.debug(f"Filter: {filter}")
    if not filter:
        filter = {
            "brightness": 1.0,
            "contrast": 1.0,
            "color": 1.0,
            "sharpness": 1.0,
        }

    if isinstance(brightness, (int, float)) and not min_max_check(brightness):
        brightness = make_min_max_prompt(
            "Adjust brightness:",
            filter.get("brightness", 1.0),
        )
    if isinstance(contrast, (int, float)) and not min_max_check(contrast):
        contrast = make_min_max_prompt("Adjust contrast:", filter.get("contrast", 1.0))
    if isinstance(color, (int, float)) and not min_max_check(color):
        color = make_min_max_prompt("Adjust color:", filter.get("color", 1.0))
    if isinstance(sharpness, (int, float)) and not min_max_check(sharpness):
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
        logger.fatal(e)
        return
    if not filter_name:
        filter_name = inquirer.select(
            message="Select a filter to delete:",
            choices=[filter["name"] for filter in gdb.get_filters_all()],
        ).execute()
    gdb.delete_filter(filter_name)
    return


@app.command()
def rename(
    old_name: str = typer.Argument(None, help="Old filter name"),
    new_name: str = typer.Argument(None, help="New filter name"),
):
    """Rename a filter."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(e)
        return
    if not old_name:
        old_name = inquirer.select(
            message="Select a filter to rename:",
            choices=[filter["name"] for filter in gdb.get_filters_all()],
        ).execute()
    if not new_name:
        new_name = prompt("Enter new name:")
    new_name_confirmation = gdb.rename_filter(old_name, new_name)
    if not new_name_confirmation:
        logger.error(f"Unable to rename filter {old_name}.")
    else:
        logger.info(f"Filter {old_name} renamed to {new_name_confirmation}.")


@app.command()
def list():
    """List all filters."""
    try:
        gdb = SharedDB()
    except Exception as e:
        logger.fatal(e)
        return
    filters = gdb.get_filters_all()
    for filter in filters:
        logger.info(f"[bold]{filter['name']}:[/bold]")
        logger.info(f"\tBrightness: {filter['brightness']}")
        logger.info(f"\tContrast: {filter['contrast']}")
        logger.info(f"\tColor: {filter['color']}")
        logger.info(f"\tSharpness: {filter['sharpness']}")
