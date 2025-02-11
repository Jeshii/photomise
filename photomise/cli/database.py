import typer

from photomise.database.shared import SharedDB
from photomise.utilities.project import set_project
from photomise.utilities.logging import setup_logging

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
        
