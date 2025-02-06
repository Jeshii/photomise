from typer import Option, Typer

from photomise.database.shared import SharedDB
from photomise.utilities.project import set_project

app = Typer()


@app.command()
def prettify(
    project: str = Option(None, "--project", "-p", help="Project name"),
):
    """Reformat JSON data to be more human-readable."""
    gdb = SharedDB()
    if project:
        pdb, _ = set_project(project)

    if project:
        pdb.close()
    else:
        gdb.close()
