"""
Doctor command - Check if environment is ready.
"""

from pathlib import Path
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich import box

from opun8.core.environment import EnvironmentChecker

console = Console()


def doctor():
    """Check the user's environment and project."""
    console.print()
    console.print(Panel(
        "[bold cyan]🔍 Opun8 Doctor[/bold cyan]\n"
        "[dim]Checking your environment and project...[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))

    # Run all checks
    checker = EnvironmentChecker()
    results = checker.check_all()

    # Display results
    table = Table(
        title="Environment Status",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
    )
    table.add_column("Component", style="bold white", width=14)
    table.add_column("Status", style="bold", width=10)
    table.add_column("Details", style="dim", width=30)

    for key, result in results.items():
        status_icon = "✅" if result["passed"] else "❌"
        status_text = "[green]OK[/green]" if result["passed"] else "[red]Missing[/red]"
        table.add_row(result["name"], status_text, result["details"])

    console.print(table)

    # Summary
    all_passed = all(r["passed"] for r in results.values())
    if all_passed:
        console.print()
        console.print(Panel(
            "[bold green]✅ Everything looks good![/bold green]\n"
            "You're ready to use Opun8.",
            border_style="green",
            padding=(1, 2),
            width=60,
        ))
    else:
        console.print()
        console.print(Panel(
            "[bold yellow]⚠️ Some components are missing.[/bold yellow]\n"
            "Install the missing components and try again.",
            border_style="yellow",
            padding=(1, 2),
            width=60,
        ))

    # Show project info if detected
    project_info = results.get("project", {})
    if project_info.get("passed"):
        console.print()
        console.print("[bold cyan]📁 Project Information:[/bold cyan]")
        console.print(f"  Type: {project_info['project_type'] or 'Unknown'}")
        console.print(f"  Path: {Path.cwd()}")

    console.print()