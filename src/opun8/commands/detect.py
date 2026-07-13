"""
Detect command - Detect project type and guide user.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from opun8.core.detector import ProjectDetector
from opun8.core.templates import ProjectTemplates
from opun8.services import navigation as nav
from opun8.services.recent_projects import get_recent_projects, add_recent_project
from opun8.ui import messages as msg

console = Console()


# ──────────────────────────────────────────────────────────────
# SAFE PROMPT (handles Ctrl+C / Ctrl+Z)
# ──────────────────────────────────────────────────────────────

def _safe_prompt(
    message: str,
    choices: Optional[list] = None,
    default: str = "1",
    show_choices: bool = False,
) -> Optional[str]:
    """
    Prompt the user with graceful handling of Ctrl+C and Ctrl+Z.
    Returns None if the user cancels.
    """
    try:
        if choices:
            return Prompt.ask(
                message,
                choices=choices,
                default=default,
                show_choices=show_choices,
            )
        else:
            return Prompt.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        return None


def detect(silent: bool = False) -> Optional[Dict[str, Any]]:
    """
    Detect project type and guide user.
    
    Args:
        silent: If True, suppress UI output and just return the detection result.
                Used when called from deploy command to avoid duplicate UI.
    
    Returns:
        Detection result dict if silent=True, None otherwise.
    """
    detector = ProjectDetector()
    
    if not silent:
        msg.detection_start()
    
    with msg.scanning_spinner():
        result = detector.detect()
    
    if not result["is_detected"]:
        if not silent:
            msg.no_project_detected()
            show_no_project_menu()
        return None
    
    # Add to recent projects
    add_recent_project(str(Path.cwd()))
    
    if not silent:
        msg.detection_complete(result)
        _post_detection_menu(result)
        return None
    
    # Silent mode: just return the result
    return result


def _post_detection_menu(result: dict) -> None:
    """
    Handle the 'what next' menu shown after a successful detection.
    """
    while True:
        console.print()
        console.print("[bold]🎉 Nice! Your project is ready. What would you like to do?[/bold]")
        console.print()
        console.print("  [bold cyan]1[/] 🚀  [white]Deploy this project (with GitHub)[/white]")
        console.print("  [bold cyan]2[/] ⏭️  [white]Deploy without GitHub[/white]")
        console.print("  [bold cyan]3[/] 📂  [white]Select a different project[/white]")
        console.print("  [bold cyan]4[/] 🚪  [white]Exit[/white]")
        console.print()
        
        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2", "3", "4"],
            default="1",
        )

        if choice is None:
            return

        if choice == "1":
            _deploy_with_github(result)
            return None
        elif choice == "2":
            _deploy_without_github(result)
            return None
        elif choice == "3":
            from opun8.commands.detect import go_to_folder
            go_to_folder()
            return None
        else:  # choice == "4"
            msg.goodbye()
            raise typer.Exit()


def _deploy_with_github(result: dict) -> None:
    """Deploy with GitHub push."""
    from opun8.commands.deploy import deploy as deploy_cmd
    # Pass the already detected result so deploy doesn't re-detect
    deploy_cmd(platform_arg=None, skip_github=False, detected_project=result)


def _deploy_without_github(result: dict) -> None:
    """Deploy without GitHub push."""
    from opun8.commands.deploy import deploy as deploy_cmd
    # Pass the already detected result so deploy doesn't re-detect
    deploy_cmd(platform_arg=None, skip_github=True, detected_project=result)


def show_no_project_menu():
    """Show menu when no project is detected with recent projects."""
    console.print()
    console.print("[yellow]⚠️ No project detected in current folder.[/yellow]")
    console.print()
    
    # Show recent projects
    recent = get_recent_projects()
    if recent:
        console.print("[bold]📁 Recent Projects:[/bold]")
        console.print()
        for i, project in enumerate(recent, 1):
            console.print(f"  [bold cyan]{i}[/]  [white]{project['name']}[/white]  [dim]({project['path']})[/dim]")
        console.print()
        console.print(f"  [bold cyan]{len(recent) + 1}[/]  📂  [white]Browse for a different folder[/white]")
        console.print(f"  [bold cyan]{len(recent) + 2}[/]  📁  [white]Create a new project[/white]")
        console.print("  [bold cyan]0[/]  🚪  [white]Exit[/white]")
        console.print()
        
        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            choices=[str(i) for i in range(0, len(recent) + 3)],
            default="1",
        )
        
        if choice is None:
            return
        
        try:
            choice_num = int(choice)
            if choice_num == 0:
                msg.goodbye()
                return
            elif 1 <= choice_num <= len(recent):
                # Navigate to recent project
                project_path = recent[choice_num - 1]["path"]
                if Path(project_path).exists():
                    os.chdir(project_path)
                    console.print(f"[green]✅ Changed to: {project_path}[/green]")
                    detect()
                    return
                else:
                    console.print("[red]❌ Project path no longer exists.[/red]")
                    from opun8.services.recent_projects import remove_recent_project
                    remove_recent_project(project_path)
                    show_no_project_menu()
                    return
            elif choice_num == len(recent) + 1:
                go_to_folder()
                return
            elif choice_num == len(recent) + 2:
                create_new_project()
                return
        except ValueError:
            pass
    
    # If no recent projects or invalid choice
    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] 📁  [white]Create a new project[/white]")
    console.print("  [bold cyan]2[/] 📂  [white]Browse for a different folder[/white]")
    console.print("  [bold cyan]3[/] 🚪  [white]Exit[/white]")
    console.print()

    choice = _safe_prompt(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2", "3"],
        default="1",
    )
    
    if choice is None:
        return
    
    if choice == "1":
        create_new_project()
    elif choice == "2":
        go_to_folder()
    else:
        msg.goodbye()
        return


def create_new_project():
    """Guide user through creating a new project."""
    console.print()
    console.print("[bold cyan]📦 Create a new project[/bold cyan]")
    console.print("[dim]Choose a template to get started:[/dim]")
    console.print()
    console.print("  [bold cyan]1[/] ⚛️  [white]React + Vite[/white]  [dim](Modern React with fast build)[/dim]")
    console.print("  [bold cyan]2[/] 🔷  [white]Next.js[/white]  [dim](Full-stack React framework)[/dim]")
    console.print("  [bold cyan]3[/] 📄  [white]Static HTML + CSS[/white]  [dim](Simple static site)[/dim]")
    console.print("  [bold cyan]4[/] 🖥️  [white]Node.js API[/white]  [dim](Express.js REST API)[/dim]")
    console.print()
    console.print("  [bold cyan]5[/] 🔄  [white]Go back[/white]")
    console.print()
    
    choice = _safe_prompt(
        "[bold cyan]➜[/] Select a template",
        choices=["1", "2", "3", "4", "5"],
        default="1",
    )
    
    if choice is None:
        return
    
    if choice == "5":
        detect()
        return
    
    template_map = {"1": "react", "2": "nextjs", "3": "static", "4": "node"}
    template = template_map.get(choice, "react")
    template_name = {"1": "React", "2": "Next.js", "3": "Static", "4": "Node.js"}.get(choice, "React")
    
    console.print()
    console.print(f"[bold]Creating a new {template_name} project...[/bold]")
    console.print()
    
    console.print("[dim]Where would you like to create the project?[/dim]")
    console.print("  [bold cyan]1[/]  [white]Current folder[/white]")
    console.print("  [bold cyan]2[/]  [white]Choose a location[/white]  [dim](opens file explorer)[/dim]")
    console.print()
    
    location_choice = _safe_prompt(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2"],
        default="1",
    )
    
    if location_choice is None:
        return
    
    target_path = Path.cwd()
    
    if location_choice == "2":
        console.print()
        console.print("[dim]📂 Opening file explorer...[/dim]")
        console.print("[dim]Select a folder where you want to create the project.[/dim]")
        console.print("[dim]⚠️ Close the folder window to continue.[/dim]")
        console.print()
        
        selected_path = msg.prompt_select_folder("Select folder for new project")
        if selected_path:
            target_path = selected_path
            console.print(f"[green]Selected: {target_path}[/green]")
        else:
            console.print("[yellow]No folder selected. Using current folder.[/yellow]")
    
    console.print()
    project_name = _safe_prompt("[bold cyan]➜[/] Project name", default="my-app")
    
    if project_name is None:
        return
    
    project_path = target_path / project_name
    
    if project_path.exists():
        console.print(f"[yellow]Directory '{project_name}' already exists.[/yellow]")
        overwrite = Confirm.ask("Overwrite?", default=False)
        if not overwrite:
            console.print("[dim]Project creation cancelled.[/dim]")
            create_new_project()
            return
        shutil.rmtree(project_path)
    
    console.print()
    console.print(f"[yellow]📦 Creating {template_name} project: {project_name}...[/yellow]")
    console.print("[dim]This may take a moment depending on your internet connection.[/dim]")
    console.print()
    
    success = ProjectTemplates.create_project(template, project_name, target_path)
    
    if success:
        console.print()
        console.print(f"[bold green]✅ Project '{project_name}' created successfully![/bold green]")
        console.print(f"[dim]📁 Path: {project_path}[/dim]")
        console.print()
        
        navigate = Confirm.ask("[bold]Would you like to navigate to the new project?[/bold]", default=True)
        
        if navigate:
            if nav.change_directory(str(project_path)):
                console.print(f"[green]✅ Changed to: {nav.get_current_directory()}[/green]")
                console.print()
                console.print("[bold cyan]📁 Running detection on the new project...[/bold cyan]")
                detect()
            else:
                console.print("[red]❌ Failed to change directory.[/red]")
                create_new_project()
        else:
            console.print("[dim]You can navigate to the project later with:[/dim]")
            console.print(f"  cd {project_path}")
            console.print("  opun8 detect")
            detect()
    else:
        console.print()
        console.print("[red]❌ Failed to create project.[/red]")
        console.print("[dim]Possible reasons:[/dim]")
        console.print("[dim]  • No internet connection[/dim]")
        console.print("[dim]  • npm/node not installed[/dim]")
        console.print("[dim]  • Permission issues[/dim]")
        console.print()
        
        retry = Confirm.ask("Would you like to try again?", default=True)
        if retry:
            create_new_project()
        else:
            detect()


def go_to_folder():
    """Interactive folder browser with file explorer option."""
    current_path = Path.cwd()
    
    while True:
        console.print("\n" * 2)
        console.print(Panel(
            "[bold cyan]📂 Folder Browser[/bold cyan]\n"
            f"[dim]Current: {current_path}[/dim]\n\n"
            "You can browse folders here or open the file explorer.",
            border_style="cyan",
            padding=(1, 2),
            width=70,
        ))
        
        folders, files = nav.list_items(current_path)
        
        console.print()
        console.print("[bold]📁 Folders:[/bold]")
        console.print()
        
        if str(current_path) != current_path.drive + "\\":
            console.print("  ..  📂  Go up")
        
        for i, folder in enumerate(folders, 1):
            console.print(f"  {i}  📂  {folder}")
        
        if not folders:
            console.print("  No folders found")
        
        console.print()
        console.print("[bold]Options:[/bold]")
        console.print()
        console.print("  1  📂  Select a folder by number")
        console.print("  2  📂  Open file explorer to pick a folder")
        console.print("  3  🔍  Enter path manually")
        console.print("  4  💾  Select this folder (run detection)")
        console.print("  5  🔄  Go back")
        console.print()
        
        if str(current_path) != current_path.drive + "\\":
            console.print("  6  ⬆️  Go up one level")
        
        console.print()
        
        valid_choices = ["1", "2", "3", "4", "5"]
        if str(current_path) != current_path.drive + "\\":
            valid_choices.append("6")
        
        choice = _safe_prompt(
            "➜ Select an option",
            choices=valid_choices,
            default="1",
        )
        
        if choice is None:
            return
        
        if choice == "1":
            if not folders:
                console.print("[yellow]No folders to select.[/yellow]")
                continue
            
            console.print()
            folder_num = _safe_prompt("➜ Enter folder number", default="1")
            if folder_num is None:
                return
            
            try:
                idx = int(folder_num) - 1
                if 0 <= idx < len(folders):
                    new_path = current_path / folders[idx]
                    current_path = new_path
                    nav.change_directory(str(current_path))
                    continue
                else:
                    console.print("[red]Invalid number.[/red]")
            except ValueError:
                console.print("[red]Please enter a valid number.[/red]")
        
        elif choice == "2":
            console.print()
            console.print("[dim]📂 Opening file explorer...[/dim]")
            console.print("[dim]Select a folder and close the window to continue.[/dim]")
            console.print()
            
            selected = msg.prompt_select_folder("Select a project folder")
            if selected:
                new_path = Path(selected)
                if new_path.exists() and new_path.is_dir():
                    current_path = new_path
                    nav.change_directory(str(current_path))
                    console.print(f"[green]✅ Selected: {current_path}[/green]")
                    continue
                else:
                    console.print("[red]Invalid path selected.[/red]")
            else:
                console.print("[yellow]No folder selected.[/yellow]")
        
        elif choice == "3":
            console.print()
            console.print("[dim]Enter a full path (e.g., C:\\Projects\\my-app)[/dim]")
            manual_path = _safe_prompt("➜ Path")
            if manual_path is None:
                return
            
            if manual_path:
                new_path = Path(manual_path).resolve()
                if new_path.exists() and new_path.is_dir():
                    current_path = new_path
                    nav.change_directory(str(current_path))
                    console.print(f"[green]✅ Changed to: {current_path}[/green]")
                else:
                    console.print(f"[red]Invalid path: {manual_path}[/red]")
        
        elif choice == "4":
            console.print()
            console.print(f"[green]✅ Selected: {current_path}[/green]")
            console.print("[dim]Running detection on this folder...[/dim]")
            detect()
            return
        
        elif choice == "5":
            detect()
            return
        
        elif choice == "6":
            if nav.go_up():
                current_path = Path.cwd()
            else:
                console.print("[yellow]Already at root.[/yellow]")