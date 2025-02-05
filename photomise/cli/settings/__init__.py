from typing import Final

from cli import settings_app

__all__: Final[list[str]] = ["settings_app", "filters_app", "locations_app"]

import typer

filters_app = typer.Typer(help="Filter settings")
locations_app = typer.Typer(help="Location settings")
settings_app.add_typer(filters_app, name="filters", help="Filter settings")
settings_app.add_typer(locations_app, name="locations", help="Location settings")
