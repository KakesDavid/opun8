"""
Opun8 CLI - Command Line Interface for the Universal Deployment Platform.
"""

import typer
from rich.console import Console

from opun8 import __version__
from opun8.ui.messages import welcome

app = typer.Typer(
    name="opun8",
    help="Developer-first deployment platform.",
    add_completion=False,
    no_args_is_help=False,
)

console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show Opun8 version.",
    ),
):
    if version:
        console.print(f"Opun8 v{__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        welcome()


@app.command()
def doctor():
    """Check your environment and project."""
    from opun8.commands.doctor import doctor as doctor_cmd
    doctor_cmd()