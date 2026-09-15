"""`flask import-existing`: the one-time normalisation of the original 21 Cafes."""

import click
from flask import current_app
from flask.cli import with_appcontext

from .catalogue import AlreadyImported, UnrecognisedOriginalData, import_original_cafes


@click.command("import-existing")
@with_appcontext
def import_existing():
    """Normalise the original Cafes in place, positioning those whose links allow it."""
    google = current_app.extensions["google"]

    def position_from_link(url: str):
        click.echo(f"  following {url}")
        resolved = google.resolve_link(url)
        if resolved is None or resolved.coordinates is None:
            return None
        return (resolved.coordinates.latitude, resolved.coordinates.longitude)

    try:
        report = import_original_cafes(
            current_app.extensions["catalogue"], position_from_link
        )
    except AlreadyImported as error:
        raise click.ClickException(str(error))
    except UnrecognisedOriginalData as error:
        raise click.ClickException(f"Nothing was changed.\n{error}")

    click.echo(
        f"Imported {report.imported} Cafes; {report.positioned} got a Position. "
        "Match the rest to a Google place in the admin area."
    )
