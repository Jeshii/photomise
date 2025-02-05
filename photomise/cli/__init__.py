__all__ = ["app"]

import typer

app = typer.Typer(help="Photomise - Photo processing for social media posting")
settings_app = typer.Typer(help="Application settings")
app.add_typer(settings_app, name="settings", help="Change global settings.")
post_app = typer.Typer()
app.add_typer(
    post_app, name="post", help="Post photos/videos to various social media platforms."
)
database_app = typer.Typer()
app.add_typer(database_app, name="database", help="Tools for the database.")
