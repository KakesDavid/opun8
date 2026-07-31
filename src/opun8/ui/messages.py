"""
UI messages for Opun8.
All user-facing messages in one place with a warm, friendly "partner" tone.

Navigation between screens runs through a single iterative dispatcher
(`_menu_loop`) instead of screens calling each other directly, so
bouncing between menus doesn't grow the call stack.

Version: 0.1.6
"""

import os
import shutil
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Tuple, Union

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box
from rich.markup import escape

console = Console()

# ──────────────────────────────────────────────────────────────
# EMOJI / SYMBOL HANDLING
# ──────────────────────────────────────────────────────────────

_NO_EMOJI = os.environ.get("OPUN8_NO_EMOJI", "").lower() in ("1", "true", "yes")

_SYMBOLS = {
    # Status
    "success": "✅" if not _NO_EMOJI else "[OK]",
    "info": "ℹ️" if not _NO_EMOJI else "[i]",
    "warning": "⚠️" if not _NO_EMOJI else "[!]",
    "error": "❌" if not _NO_EMOJI else "[ERR]",
    # Actions
    "rocket": "🚀" if not _NO_EMOJI else "",
    "party": "🎉" if not _NO_EMOJI else "",
    "heart": "💙" if not _NO_EMOJI else "",
    "star": "⭐" if not _NO_EMOJI else "*",
    "search": "🔍" if not _NO_EMOJI else "",
    "link": "🔗" if not _NO_EMOJI else "",
    "folder": "📁" if not _NO_EMOJI else "",
    "browse": "📂" if not _NO_EMOJI else "",
    "history": "📜" if not _NO_EMOJI else "",
    "books": "📚" if not _NO_EMOJI else "",
    "door": "🚪" if not _NO_EMOJI else "",
    "back": "🔙" if not _NO_EMOJI else "<",
    "arrow": "➜" if not _NO_EMOJI else ">",
    "point": "👉" if not _NO_EMOJI else "->",
    "point_down": "👇" if not _NO_EMOJI else "",
    "bulb": "💡" if not _NO_EMOJI else "*",
    "wave": "👋" if not _NO_EMOJI else "",
    "smile": "😊" if not _NO_EMOJI else "",
    "joy": "🤗" if not _NO_EMOJI else "",
    "sparkles": "✨" if not _NO_EMOJI else "",
    "home": "🏠" if not _NO_EMOJI else "",
    "globe": "🌐" if not _NO_EMOJI else "",
    "construction": "🏗️" if not _NO_EMOJI else "",
    "clipboard": "📋" if not _NO_EMOJI else "",
    "hammer": "🔨" if not _NO_EMOJI else "",
    "green_circle": "🟢" if not _NO_EMOJI else "",
    "grin": "😁" if not _NO_EMOJI else "",
    "thinking": "🤔" if not _NO_EMOJI else "",
    "thumbsup": "👍" if not _NO_EMOJI else "",
    "handshake": "🤝" if not _NO_EMOJI else "",
    "shield": "🛡️" if not _NO_EMOJI else "",
    "skip": "⏭️" if not _NO_EMOJI else ">>",
    "verify": "🔑" if not _NO_EMOJI else "",
    "lock": "🔐" if not _NO_EMOJI else "",
    "hooray": "🥳" if not _NO_EMOJI else "",
    "spy": "🕵️" if not _NO_EMOJI else "",
    "badge": "🏅" if not _NO_EMOJI else "",
    "crown": "🏆" if not _NO_EMOJI else "",
    # Platforms
    "triangle": "▲" if not _NO_EMOJI else "",
    "box": "📦" if not _NO_EMOJI else "",
    "cloud": "☁️" if not _NO_EMOJI else "",
    # Misc
    "clone": "📦" if not _NO_EMOJI else "",
    "upgrade": "⬆️" if not _NO_EMOJI else "",
    "chart": "📊" if not _NO_EMOJI else "",
    "cycle": "🔄" if not _NO_EMOJI else "",
    "question": "❓" if not _NO_EMOJI else "?",
    # ✅ FIX 12: Added 'pencil' symbol for rename URL flow
    "pencil": "✏️" if not _NO_EMOJI else "",
}

_KEYCAPS = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}


def _sym(key: str) -> str:
    """Get symbol by key."""
    return _SYMBOLS.get(key, "")


def _emoji_or_empty(key: str) -> str:
    """Return 'emoji ' with trailing space, or '' if empty."""
    emoji = _sym(key)
    return f"{emoji} " if emoji else ""


def _keycap(n: int) -> str:
    """Return keycap emoji or plain fallback in no-emoji mode."""
    if _NO_EMOJI:
        return f"{n})"
    return _KEYCAPS.get(n, f"{n}.")


def _escape_text(value) -> str:
    """Escape rich markup in dynamic values."""
    return escape(str(value))


def _safe_str(value) -> str:
    """
    Safely convert a value to string, handling None.
    
    ✅ FIX 3: Protects against None values in dict.get()
    """
    return str(value) if value is not None else ""


def _safe_capitalize(value) -> str:
    """
    Safely capitalize a value, handling None.
    
    ✅ FIX 3: Protects against None values in .capitalize()
    """
    if value is None:
        return "Unknown"
    return str(value).capitalize()


def _truncate(value, length: int) -> str:
    """Truncate string with ellipsis."""
    text = str(value) if value is not None else ""
    if len(text) > length:
        return text[: max(length - 1, 0)] + "…"
    return text


def _panel_width(preferred: int = 65, minimum: int = 40) -> int:
    """Calculate safe panel width based on terminal size."""
    term_width = shutil.get_terminal_size(fallback=(preferred, 24)).columns
    return max(minimum, min(preferred, term_width - 4))


# ──────────────────────────────────────────────────────────────
# SAFE PROMPTS
# ──────────────────────────────────────────────────────────────

def _safe_prompt(
    message: str,
    choices: list,
    default: str = "1",
) -> str:
    """Prompt wrapper with Ctrl+C / Ctrl+D handling."""
    try:
        return Prompt.ask(
            message,
            choices=choices,
            default=default,
            show_choices=False,
        )
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n{_sym('wave')} Goodbye, friend!")
        raise typer.Exit(0)


def _safe_prompt_free(
    message: str,
    default: str = "",
) -> Optional[str]:
    """
    Free-text prompt wrapper with Ctrl+C / Ctrl+D handling.
    
    ✅ FIX 6: Used for Render API key prompt and free-text inputs.
    """
    try:
        return Prompt.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n{_sym('wave')} Goodbye, friend!")
        raise typer.Exit(0)


def _safe_confirm(message: str, default: bool = True) -> bool:
    """Confirm wrapper with Ctrl+C / Ctrl+D handling."""
    try:
        return Confirm.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n{_sym('wave')} Goodbye, friend!")
        raise typer.Exit(0)


# ──────────────────────────────────────────────────────────────
# CORE MESSAGES
# ──────────────────────────────────────────────────────────────

def success(message: str) -> None:
    console.print(f"[bold green]{_sym('success')} {_escape_text(message)}[/bold green]")


def info(message: str) -> None:
    console.print(f"[bold blue]{_sym('info')} {_escape_text(message)}[/bold blue]")


def warning(message: str) -> None:
    console.print(f"[bold yellow]{_sym('warning')} {_escape_text(message)}[/bold yellow]")


def error(message: str, suggestion: str = "") -> None:
    console.print()
    console.print(Panel(
        f"[bold red]{_sym('error')} {_escape_text(message)}[/bold red]\n\n"
        f"[dim]{_sym('bulb')} {_escape_text(suggestion or 'Try again, or run opun8 --help to see all commands.')}[/dim]",
        border_style="red",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()


def goodbye() -> None:
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('wave')} Thanks for stopping by, friend![/bold cyan]\n\n"
        "[dim]Come back anytime — I'll be right here when you're ready to ship.[/dim]\n"
        f"[dim]{_sym('heart')} Built with love by the Kakes David Team[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()


# ──────────────────────────────────────────────────────────────
# NAVIGATION DISPATCHER
# ──────────────────────────────────────────────────────────────

def _run_action(action: str) -> None:
    """
    Execute a terminal action.
    
    ✅ FIX 11: Returns to welcome after actions complete.
    """
    if action == "deploy":
        from opun8.commands.deploy import deploy
        deploy()
    elif action == "doctor":
        from opun8.commands.doctor import doctor
        doctor()
    elif action == "github":
        from opun8.cli import github
        github()
    elif action == "go_to_folder":
        from opun8.commands.detect import go_to_folder
        go_to_folder()
    elif action == "exit":
        goodbye()
        raise typer.Exit()
    
    # ✅ FIX 11: After action completes, show welcome again
    if action not in ("exit", "deploy"):  # deploy handles its own flow
        show_welcome()


def _menu_loop(start_screen: str) -> None:
    """Iterative screen dispatcher — no recursion."""
    screen = start_screen
    while True:
        if screen == "welcome":
            next_screen, action = _screen_welcome()
        elif screen == "help":
            next_screen, action = _screen_help()
        elif screen == "detect_menu":
            next_screen, action = _screen_detect_menu()
        elif screen == "no_project_menu":
            next_screen, action = _screen_no_project_menu()
        else:
            return

        if action is not None:
            _run_action(action)
            return
        if next_screen is None:
            return
        screen = next_screen


# ──────────────────────────────────────────────────────────────
# WELCOME SCREEN
# ──────────────────────────────────────────────────────────────

def _get_github_username() -> Optional[str]:
    """Get GitHub username if authenticated."""
    try:
        from opun8.auth import is_authenticated, get_authenticated_user
        if is_authenticated():
            return get_authenticated_user()
    except Exception:
        return None
    return None


def show_welcome() -> None:
    """Display the warm, friendly welcome screen."""
    _menu_loop("welcome")


def _screen_welcome() -> Tuple[Optional[str], Optional[str]]:
    """Render welcome screen."""
    console.print("\n")

    github_user = _get_github_username()
    is_github_connected = github_user is not None

    if is_github_connected:
        greeting = (
            f"{_emoji_or_empty('wave')}{_emoji_or_empty('smile')}"
            f"HELLO, {_escape_text(github_user.upper())}! I am Opun8, your Deployment Partner!"
        )
    else:
        greeting = (
            f"{_emoji_or_empty('wave')}{_emoji_or_empty('smile')}"
            "HELLO FRIEND! I am Opun8, your Deployment Assistant!"
        )

    console.print(Panel(
        f"[bold cyan]{greeting}[/bold cyan]\n"
        f"[dim]Built with {_sym('heart')} by the Kakes David Team to launch your site![/dim]\n\n"
        f"[white]{_emoji_or_empty('heart')}I am your partner! Let's launch your website together![/white]\n"
        f"[dim]{_emoji_or_empty('point_down')}Look at the big numbers below and pick one![/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    from opun8.services.recent_projects import get_recent_projects
    recent = get_recent_projects()
    if recent:
        last_project = recent[0]
        console.print(f"[bold]{_sym('folder')} YOUR LAST WORKED PROJECT:[/bold]")
        console.print(f"   {_emoji_or_empty('point')}[cyan]{_escape_text(last_project.get('name', 'Unknown'))}[/cyan]")
        console.print()

    if not is_github_connected:
        console.print(f"[bold red]{_sym('error')} GITHUB IS NOT CONNECTED YET! {_sym('heart')}[/bold red]")
        console.print(f"[dim]{_emoji_or_empty('point')}Press button number {_keycap(3)} below to connect it with me![/dim]")
    else:
        console.print(f"[bold green]{_sym('success')} GITHUB IS CONNECTED! Welcome back, {_escape_text(github_user)}! {_sym('party')}[/bold green]")
    console.print()

    console.print(f"[bold]{_emoji_or_empty('sparkles')}CHOOSE A BUTTON FOR ME TO HELP YOU:[/bold]")
    console.print()
    console.print(f"  [bold cyan]{_keycap(1)}[/] {_sym('rocket')} [white]LAUNCH MY WEBSITE NOW![/white] [dim](Recommended)[/dim]")
    console.print(f"  [bold cyan]{_keycap(2)}[/] {_sym('search')} [white]Check my system health[/white]")
    if not is_github_connected:
        console.print(f"  [bold cyan]{_keycap(3)}[/] {_sym('lock')} [bold yellow]CONNECT MY GITHUB PROFILE NOW! {_sym('verify')}[/bold yellow]")
    else:
        console.print(f"  [bold cyan]{_keycap(3)}[/] {_sym('link')} [white]Manage GitHub connection[/white]")
    console.print(f"  [bold cyan]{_keycap(4)}[/] {_sym('books')} [white]See all options[/white]")
    console.print(f"  [bold cyan]{_keycap(5)}[/] {_sym('door')} [white]Close app[/white]")
    console.print()

    console.print(f"[green]{_sym('success')} STUCK OR NOT SURE? Just smash the ENTER key on your keyboard! {_sym('joy')}[/green]")
    console.print(f"[dim]   I will automatically handle everything and make it live for you! {_sym('party')}[/dim]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Press a number or Enter",
        choices=["1", "2", "3", "4", "5"],
        default="1",
    )

    # ✅ FIX 8: Removed dead code, all choices handled directly
    if choice == "1":
        return None, "deploy"
    elif choice == "2":
        return None, "doctor"
    elif choice == "3":
        return None, "github"
    elif choice == "4":
        return "help", None
    else:
        return None, "exit"


# ──────────────────────────────────────────────────────────────
# HELP SCREEN
# ──────────────────────────────────────────────────────────────

_COMMANDS = [
    ("opun8", "Show welcome screen"),
    ("opun8 --version", "Show version"),
    ("opun8 doctor", "Check environment"),
    ("opun8 detect", "Detect project type"),
    ("opun8 deploy", "Deploy your project"),
    ("opun8 register", "Create an OPUN8 account"),
    ("opun8 login", "Log in to your account"),
    ("opun8 verify", "Verify email with OTP"),
    ("opun8 resend-otp", "Resend verification code"),
    ("opun8 status", "Check account status"),
    ("opun8 logout", "Logout from all services"),
    ("opun8 github", "Connect to GitHub"),
    ("opun8 vercel", "Connect to Vercel"),
    ("opun8 netlify", "Connect to Netlify"),
    ("opun8 render", "Connect to Render"),
    ("opun8 clone", "Clone any website"),
    ("opun8 upgrade", "Upgrade subscription plan"),
    ("opun8 history", "View deployment history"),
    ("opun8 badges", "View badge progress"),
    ("opun8 help", "Show this help"),
]


def show_help() -> None:
    """Display all commands."""
    _menu_loop("help")


def _screen_help() -> Tuple[Optional[str], Optional[str]]:
    """Render help screen."""
    console.print("\n")

    console.print(Panel(
        f"[bold cyan]{_sym('books')} Opun8 Commands[/bold cyan]\n"
        "[dim]Everything you can do, all in one place.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()

    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Command", style="bold green", width=22)
    table.add_column("Description", style="white", width=42)

    for cmd, desc in _COMMANDS:
        table.add_row(cmd, desc)

    console.print(table)
    console.print()
    console.print(f"[dim]{_sym('bulb')} For more details, visit: [cyan]https://opun8.dev/docs[/cyan][/dim]")
    console.print()

    console.print("[bold]What would you like to do next?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_sym('back')}  [white]Go back to main menu[/white]")
    console.print(f"  [bold cyan]2[/] {_sym('door')}  [white]Exit[/white]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=["1", "2"],
        default="1",
    )

    if choice == "1":
        return "welcome", None
    return None, "exit"


# ──────────────────────────────────────────────────────────────
# DETECTION UI
# ──────────────────────────────────────────────────────────────

def detection_start() -> None:
    """Show detection start with partner tone."""
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('spy')} PROJECT SCOUTED! I found your files![/bold cyan]\n"
        f"[dim]Built with {_sym('heart')} by the Kakes David Team to help you![/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))


@contextmanager
def scanning_spinner(message: str = "Scanning your current folder..."):
    with console.status(f"[dim]{message}[/dim]", spinner="dots"):
        yield


def detection_complete(result: dict) -> None:
    """Show detection results with partner tone."""
    console.print()
    console.print(Panel(
        f"[bold green]{_sym('hooray')} HOORAY! Everything looks perfect and healthy! {_sym('heart')}[/bold green]\n"
        f"[dim]{_emoji_or_empty('point_down')}Here is the structural data I found for us, partner:[/dim]",
        border_style="green",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()

    # ✅ FIX 3: Use _safe_str() and _safe_capitalize() to handle None values
    table = Table(
        title=f"{_emoji_or_empty('clipboard')}Project Details",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        width=_panel_width(60),
    )
    table.add_column("Field", style="bold white", width=20)
    table.add_column("Value", style="white", width=35)

    project_name = _safe_str(result.get("name", Path.cwd().name))
    framework = result.get("framework", "Unknown")
    package_manager = _safe_str(result.get("package_manager", "Unknown"))
    project_type = result.get("type", "Unknown")

    framework_display = {
        "react": "React", "nextjs": "Next.js", "vue": "Vue",
        "angular": "Angular", "vite": "Vite", "nodejs": "Node.js",
        "django": "Django", "flask": "Flask", "fastapi": "FastAPI",
        "python": "Python", "static": "Static HTML",
    }.get(framework, _safe_capitalize(framework))

    table.add_row(f"{_sym('folder')} Project Name", _escape_text(project_name))
    table.add_row(f"{_sym('box')} Framework", _escape_text(framework_display))
    table.add_row(f"{_sym('box')} Package Manager", _escape_text(package_manager))
    table.add_row(f"{_emoji_or_empty('clipboard')}Type", _escape_text(_safe_capitalize(project_type)))

    console.print(table)

    console.print()
    table2 = Table(
        title=f"{_emoji_or_empty('hammer')}Build Configuration",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        width=_panel_width(60),
    )
    table2.add_column("Field", style="bold white", width=20)
    table2.add_column("Value", style="white", width=35)

    needs_build = result.get("needs_build", False)
    build_command = _safe_str(result.get("build_command", "None"))
    output_dir = _safe_str(result.get("output_dir", "."))

    table2.add_row(f"{_emoji_or_empty('hammer')}Needs Build", f"{_sym('success')} Yes" if needs_build else f"{_sym('error')} No (static)")
    table2.add_row(f"{_emoji_or_empty('clipboard')}Build Command", _escape_text(build_command))
    table2.add_row(f"{_sym('folder')} Output Directory", _escape_text(output_dir))

    build_folder_exists = f"{_sym('success')} Exists" if Path(output_dir).exists() else f"{_sym('error')} Not found"
    table2.add_row(f"{_sym('browse')} Build Folder", build_folder_exists)

    console.print(table2)
    console.print()

    _menu_loop("detect_menu")


def _screen_detect_menu() -> Tuple[Optional[str], Optional[str]]:
    """Render post-detection menu."""
    console.print(f"[bold green]{_sym('point')} WHAT SHOULD WE DO NEXT, PARTNER? {_sym('smile')}[/bold green]")
    console.print()
    console.print(f"  [bold cyan]{_keycap(1)}[/] {_sym('rocket')} [white]LAUNCH THIS WEBSITE TO THE INTERNET NOW![/white] [dim](Recommended)[/dim]")
    console.print(f"  [bold cyan]{_keycap(2)}[/] {_sym('folder')} [white]Go back to the main menu[/white]")
    console.print(f"  [bold cyan]{_keycap(3)}[/] {_sym('door')} [white]Close app[/white]")
    console.print()
    console.print(f"[green]{_sym('success')} STUCK OR NOT SURE? Just smash the ENTER key! {_sym('joy')}[/green]")
    console.print(f"[dim]   I will automatically choose {_keycap(1)} and put your site live! {_sym('party')}[/dim]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Press a number or Enter",
        choices=["1", "2", "3"],
        default="1",
    )

    if choice == "1":
        return None, "deploy"
    elif choice == "2":
        return "welcome", None
    return None, "exit"


def no_project_detected() -> None:
    """Show no project detected message with follow-up menu."""
    console.print()
    _menu_loop("no_project_menu")


def _screen_no_project_menu() -> Tuple[Optional[str], Optional[str]]:
    """Render no-project menu."""
    console.print(Panel(
        f"[bold yellow]{_sym('warning')} Hmm, I couldn't find a project here, partner! {_sym('thinking')}[/bold yellow]\n\n"
        "[dim]I'm looking for one of these in your current folder:[/dim]\n"
        "[dim]  • package.json (Node.js/React/Next.js)[/dim]\n"
        "[dim]  • index.html (Static HTML)[/dim]\n"
        "[dim]  • requirements.txt (Python)[/dim]\n\n"
        f"[dim]{_emoji_or_empty('bulb')}Not in the right folder? I can help you navigate![/dim]",
        border_style="yellow",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()

    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_sym('folder')}  [white]Select a different folder[/white]")
    console.print(f"  [bold cyan]2[/] {_sym('back')}  [white]Go back to main menu[/white]")
    console.print(f"  [bold cyan]3[/] {_sym('door')}  [white]Exit[/white]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=["1", "2", "3"],
        default="1",
    )

    if choice == "1":
        return None, "go_to_folder"
    elif choice == "2":
        return "welcome", None
    return None, "exit"


# ──────────────────────────────────────────────────────────────
# DEPLOY PLATFORM UI (NEW 4-Option Menu)
# ──────────────────────────────────────────────────────────────

def deploy_platform_start(platform: str) -> None:
    """
    Show platform-specific welcome with partner tone.

    ✅ FIX 5: Now uses _sym() for emoji, respecting OPUN8_NO_EMOJI.
    ✅ FIX 10: Fixed incorrect docstring example.

    Example:
        >>> deploy_platform_start("netlify")
        (prints) "📦 Alright friend, let's get your project deployed to Netlify!"
    """
    # ✅ FIX 5: Use _sym() instead of hardcoded emoji
    emoji_map = {
        "vercel": "triangle",
        "netlify": "box",
        "render": "cloud",
    }
    emoji_key = emoji_map.get(platform.lower(), "rocket")
    emoji = _sym(emoji_key)
    
    console.print()
    console.print(Panel(
        f"[bold cyan]{emoji} Alright friend, let's get your project deployed to [bold]{_escape_text(platform.capitalize())}[/bold]![/bold cyan]\n"
        f"[dim]{_emoji_or_empty('heart')} I'm here to help you launch, partner![/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()


def deploy_platform_menu() -> Optional[str]:
    """
    Show the 4-option deploy menu and capture user input.

    ✅ FIX 1: Now captures user input and returns the choice.

    Returns:
        "1" for Deploy Now, "2" for Select Different Project,
        "3" for Deploy GitHub Repo, "4" for Exit, or None if cancelled.

    Example:
        >>> choice = deploy_platform_menu()
        >>> if choice == "1":
        ...     print("Deploying...")
    """
    console.print(f"[bold]{_emoji_or_empty('sparkles')} What would you like to do?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_emoji_or_empty('rocket')}  [white]Deploy Now[/white]  [dim](Deploy this project)[/dim]")
    console.print(f"  [bold cyan]2[/] {_emoji_or_empty('folder')}  [white]Select Different Project[/white]")
    console.print(f"  [bold cyan]3[/] {_emoji_or_empty('clone')}  [white]Deploy GitHub Repo[/white]")
    console.print(f"  [bold cyan]4[/] {_emoji_or_empty('door')}  [white]Exit[/white]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=["1", "2", "3", "4"],
        default="1",
    )

    return choice


# ──────────────────────────────────────────────────────────────
# DEPLOY MENU (DEPRECATED — Kept for backward compatibility)
# ──────────────────────────────────────────────────────────────

def show_deploy_menu() -> None:
    """
    Show menu after detection with partner tone.

    ⚠️ DEPRECATED: This is the old menu that showed 5 options.
    The new deploy flow uses deploy_platform_start() + deploy_platform_menu().
    Kept for backward compatibility with any remaining old code.
    """
    console.print()
    console.print(f"[bold]{_sym('party')} Nice! Your project is ready. What would you like to do?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_sym('rocket')}  [white]Deploy this project[/white]")
    console.print(f"  [bold cyan]2[/] {_sym('browse')}  [white]Select a different project[/white]")
    console.print(f"  [bold cyan]3[/] {_sym('history')}  [white]View deployment history[/white]")
    console.print(f"  [bold cyan]4[/] {_sym('badge')}  [white]View badges[/white]")
    console.print(f"  [bold cyan]5[/] {_sym('door')}  [white]Exit[/white]")
    console.print()


def show_details(result: dict) -> None:
    """Show project details."""
    console.print()
    console.print(f"[bold cyan]{_sym('chart')} Project Details[/bold cyan]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold white", width=20)
    table.add_column(style="white", width=40)

    fields = ["type", "framework", "package_manager", "build_command", "output_dir", "node_version"]

    for key in fields:
        value = result.get(key)
        if value is not None:
            display_key = key.replace("_", " ").title()
            if isinstance(value, list):
                value = ", ".join(value[:5]) + ("..." if len(value) > 5 else "")
            table.add_row(display_key, _escape_text(str(value)))

    # ✅ FIX 2: Dependencies are now escaped
    deps = result.get("dependencies", [])
    if deps and isinstance(deps, list):
        escaped_deps = [_escape_text(str(d)) for d in deps[:5]]
        deps_str = ", ".join(escaped_deps)
        if len(deps) > 5:
            deps_str += "..."
        table.add_row("Dependencies", deps_str)

    console.print(table)
    console.print()


# ──────────────────────────────────────────────────────────────
# HISTORY UI
# ──────────────────────────────────────────────────────────────

def history_header(deployment_count: int, badge_name: str, badge_emoji: str) -> None:
    """Show history header with partner tone."""
    console.print("\n")

    console.print(Panel(
        f"[bold cyan]{_sym('history')}{_sym('crown')} DEPLOYMENT HISTORY LOG[/bold cyan]\n"
        f"[dim]Built with {_sym('heart')} by the Kakes David Team to track your wins![/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    console.print(Panel(
        f"[bold green]{_sym('hooray')} LOOK AT YOU GO, PARTNER! You are building great things! {_sym('heart')}[/bold green]\n"
        f"[dim]{_sym('badge')} Your current rank badge: {_escape_text(badge_emoji)} {_escape_text(badge_name)} ({deployment_count} deployments)[/dim]",
        border_style="green",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()


def history_list(deployments: list) -> None:
    """Show history list with partner tone."""
    if not deployments:
        console.print(f"[yellow]No deployments found yet, partner! {_sym('smile')}[/yellow]")
        console.print(f"[dim]Let's fix that — run 'opun8 deploy' to launch your first site! {_sym('rocket')}[/dim]")
        return

    table = Table(
        title=f"Deployments ({len(deployments)})",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        width=_panel_width(70),
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Project", style="bold white", width=18)
    table.add_column("Platform", style="dim", width=12)
    table.add_column("URL", style="cyan", width=25)
    table.add_column("Date", style="dim", width=12)

    for idx, deploy in enumerate(deployments, 1):
        project = _truncate(deploy.get("project_name") or "Unknown", 18)
        platform = _truncate(deploy.get("platform") or "Unknown", 12)
        url = _truncate(deploy.get("url") or "N/A", 25)
        date = _truncate(deploy.get("date") or "Unknown", 12)

        table.add_row(str(idx), _escape_text(project), _escape_text(platform), _escape_text(url), _escape_text(date))

    console.print(table)
    console.print()


def history_detail(deployment: dict, badge_name: str, badge_emoji: str, next_badge: str) -> None:
    """Show history detail with partner tone."""
    project = deployment.get("project_name") or "Unknown"
    platform = deployment.get("platform") or "Unknown"
    url = deployment.get("url") or "N/A"
    deploy_id = deployment.get("deploy_id") or "N/A"
    folder = deployment.get("folder") or "Unknown"
    date = deployment.get("date") or "Unknown"
    env_vars = deployment.get("env_vars") or []

    console.print()
    console.print(Panel(
        f"[bold cyan]▲ {_escape_text(project)}[/bold cyan]\n\n"
        f"[dim]Platform:[/dim] {_escape_text(platform)}\n"
        f"[dim]URL:[/dim] [cyan]{_escape_text(url)}[/cyan]\n"
        f"[dim]Deployment ID:[/dim] {_escape_text(deploy_id)}\n"
        f"[dim]Project folder:[/dim] {_escape_text(folder)}\n"
        f"[dim]Date:[/dim] {_escape_text(date)}\n"
        f"[dim]Status:[/dim] [green]{_emoji_or_empty('green_circle')}SUCCESS! {_sym('party')}{_emoji_or_empty('grin')}[/green]\n"
        f"[dim]Environment Variables:[/dim] {', '.join(_escape_text(v) for v in env_vars) if env_vars else 'None'}",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    console.print(Panel(
        f"[bold green]{_sym('crown')} WE ARE DOING GREAT, PARTNER! Here is our record! {_sym('heart')}[/bold green]\n"
        f"[dim]{_sym('badge')} Current Badge: {_escape_text(badge_emoji)} {_escape_text(badge_name)}[/dim]\n"
        f"[dim]{_sym('rocket')} {_escape_text(next_badge)}[/dim]",
        border_style="green",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    console.print(f"[bold green]{_sym('point')} WHAT SHOULD WE DO WITH THIS PROJECT, FRIEND? {_sym('smile')}[/bold green]")
    console.print()
    console.print(f"  [bold cyan]{_keycap(1)}[/] {_sym('rocket')} [white]REDEPLOY NOW![/white] [dim](Update the website live)[/dim]")
    console.print(f"  [bold cyan]{_keycap(2)}[/] {_sym('back')} [white]Go back to the list[/white]")
    console.print()
    console.print(f"[green]{_sym('success')} CLUELESS? Just press the ENTER key on your keyboard! {_sym('joy')}[/green]")
    console.print(f"[dim]   I will automatically choose {_keycap(1)} and safely redeploy it for you![/dim]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=["1", "2"],
        default="1",
    )

    if choice == "1":
        from opun8.commands.deploy import deploy
        # ✅ FIX 7: Specific exception handling
        try:
            deploy(project_folder=folder, platform=platform)
        except TypeError as e:
            if "'project_folder'" in str(e) or "got an unexpected keyword argument" in str(e):
                # Old deploy signature — fall back to no arguments
                deploy()
            else:
                # Real error, re-raise
                raise
    else:
        from opun8.commands.history import history
        history()


# ──────────────────────────────────────────────────────────────
# SHARED AUTH UI HELPERS
# ──────────────────────────────────────────────────────────────

def _auth_screen(platform: str, emoji: str, login_func, skip_message: str) -> bool:
    """
    Generic auth screen for all platforms.

    ✅ FIX 4: Returns True if authenticated, False otherwise.

    Returns:
        bool: True if authentication succeeded, False otherwise.
    """
    console.print("\n")

    console.print(Panel(
        f"[bold cyan]{_sym(emoji)}{_sym('rocket')} PREPARING YOUR {_escape_text(platform.upper())} LAUNCHPAD[/bold cyan]\n"
        f"[dim]Built with {_sym('heart')} by the Kakes David Team to host your site![/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    console.print(Panel(
        f"[bold yellow]{_sym('heart')} WE ARE ALMOST THERE, PARTNER! This is the exciting part! {_sym('party')}[/bold yellow]\n\n"
        f"[white]{_emoji_or_empty('handshake')}I just need a quick handshake with {_escape_text(platform)} so I can:[/white]\n"
        f"   • {_emoji_or_empty('construction')}Build a beautiful platform for your website\n"
        f"   • {_emoji_or_empty('globe')}Put your project live on the internet worldwide\n"
        f"   • {_emoji_or_empty('link')}Grab a clickable web link to share with your friends",
        border_style="yellow",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    console.print(f"[bold]{_emoji_or_empty('sparkles')}CHOOSE A BUTTON BELOW TO START:[/bold]")
    console.print()
    console.print(f"  [bold cyan]{_keycap(1)}[/] {_sym('verify')} [white]LOGIN WITH {_escape_text(platform.upper())} NOW! {_sym('joy')}[/white] [dim](Opens your web browser)[/dim]")
    console.print(f"  [bold cyan]{_keycap(2)}[/] {_sym('skip')} [white]Skip this step for now[/white] [dim](Deploy without {_escape_text(platform)})[/dim]")
    console.print()
    console.print(f"[green]{_sym('success')} READY TO FLY? Just smash the ENTER key to open the login page! {_sym('rocket')}[/green]")
    console.print("[dim]   Go ahead, I am sitting right here waiting for you to get back![/dim]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=["1", "2"],
        default="1",
    )

    if choice == "1":
        login_func()
        return True
    else:
        console.print(f"[dim]{_sym('skip')} {_escape_text(skip_message)}[/dim]")
        return False


# ──────────────────────────────────────────────────────────────
# PLATFORM AUTH UI
# ──────────────────────────────────────────────────────────────

def github_auth_start() -> None:
    """Show GitHub auth start with partner tone."""
    from opun8.auth import login_to_github, is_authenticated, get_authenticated_user
    
    _auth_screen(
        platform="GitHub",
        emoji="lock",
        login_func=login_to_github,
        skip_message="Skipping GitHub for now. You can connect later with 'opun8 github'"
    )
    
    if is_authenticated():
        user = get_authenticated_user()
        if user:
            github_auth_success(user)


def github_auth_success(username: str) -> None:
    """Show GitHub auth success with partner tone."""
    console.print()
    console.print(Panel(
        f"[bold green]{_sym('party')} WELCOME ABOARD, {_escape_text(username.upper())}! {_sym('party')}[/bold green]\n\n"
        f"[white]{_emoji_or_empty('handshake')}Your GitHub profile is now connected! Here's what this means:[/white]\n"
        f"   • {_emoji_or_empty('home')}I can create homes for your code files\n"
        f"   • {_emoji_or_empty('rocket')}I'll launch your updates automatically\n"
        f"   • {_emoji_or_empty('shield')}Your work is locked up securely\n\n"
        f"[dim]{_sym('heart')} Built with love by the Kakes David Team[/dim]",
        border_style="green",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()


def vercel_auth_start() -> None:
    """
    Show Vercel auth start with partner tone.
    
    ✅ FIX 4: Now shows success feedback after authentication.
    """
    from opun8.providers.vercel.auth import login_to_vercel, is_vercel_authenticated
    
    _auth_screen(
        platform="Vercel",
        emoji="triangle",
        login_func=login_to_vercel,
        skip_message="Skipping Vercel for now. You can connect later with 'opun8 vercel'"
    )
    
    # ✅ FIX 4: Show success feedback
    if is_vercel_authenticated():
        console.print()
        console.print(f"[bold green]{_sym('party')} Vercel connected successfully! {_sym('party')}[/bold green]")
        console.print("[dim]I can now deploy your projects to Vercel! 🚀[/dim]\n")


def netlify_auth_start() -> None:
    """
    Show Netlify auth start with partner tone.
    
    ✅ FIX 4: Now shows success feedback after authentication.
    """
    from opun8.providers.netlify.auth import login_to_netlify, is_netlify_authenticated
    
    _auth_screen(
        platform="Netlify",
        emoji="box",
        login_func=login_to_netlify,
        skip_message="Skipping Netlify for now. You can connect later with 'opun8 netlify'"
    )
    
    # ✅ FIX 4: Show success feedback
    if is_netlify_authenticated():
        console.print()
        console.print(f"[bold green]{_sym('party')} Netlify connected successfully! {_sym('party')}[/bold green]")
        console.print("[dim]I can now deploy your projects to Netlify! 🚀[/dim]\n")


def render_auth_start() -> None:
    """Show Render auth start with partner tone."""
    console.print("\n")

    console.print(Panel(
        f"[bold cyan]{_sym('cloud')}{_sym('rocket')} PREPARING YOUR RENDER LAUNCHPAD[/bold cyan]\n"
        f"[dim]Built with {_sym('heart')} by the Kakes David Team to host your site![/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    console.print(Panel(
        f"[bold yellow]{_sym('heart')} WE ARE ALMOST THERE, PARTNER! This is the exciting part! {_sym('party')}[/bold yellow]\n\n"
        f"[white]{_emoji_or_empty('handshake')}I just need a quick handshake with Render so I can:[/white]\n"
        f"   • {_emoji_or_empty('construction')}Build a beautiful platform for your website\n"
        f"   • {_emoji_or_empty('globe')}Put your project live on the internet worldwide\n"
        f"   • {_emoji_or_empty('link')}Grab a clickable web link to share with your friends",
        border_style="yellow",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    console.print(f"[bold]{_emoji_or_empty('sparkles')}CHOOSE A BUTTON BELOW TO START:[/bold]")
    console.print()
    console.print(f"  [bold cyan]{_keycap(1)}[/] {_sym('verify')} [white]USE API KEY! {_sym('joy')}[/white] [dim](Recommended — paste your Render API key)[/dim]")
    console.print(f"  [bold cyan]{_keycap(2)}[/] {_sym('skip')} [white]Skip this step for now[/white] [dim](Deploy without Render)[/dim]")
    console.print()
    console.print(f"[green]{_sym('success')} READY TO FLY? Just smash the ENTER key to paste your API key! {_sym('rocket')}[/green]")
    console.print("[dim]   Go ahead, I am sitting right here waiting for you to get back![/dim]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=["1", "2"],
        default="1",
    )

    if choice == "1":
        _render_api_key_prompt()
    else:
        console.print(f"[dim]{_sym('skip')} Skipping Render for now. You can connect later with 'opun8 render'[/dim]")


def _render_api_key_prompt() -> None:
    """Handle the API key prompt flow with partner tone."""
    from opun8.providers.render.auth import save_api_key, _verify_and_fetch_user

    console.print()
    console.print(Panel(
        f"[bold cyan]{_emoji_or_empty('verify')} Render API Key[/bold cyan]\n\n"
        f"[white]To get your Render API key:[/white]\n"
        f"   • Go to [dim]https://dashboard.render.com/settings/keys[/dim]\n"
        f"   • Click [bold]Create API Key[/bold]\n"
        f"   • Give it a name (e.g., [dim]opun8-cli[/dim])\n"
        f"   • Click [bold]Create API Key[/bold]\n"
        f"   • [bold]Copy the key[/bold] immediately (it's only shown once)\n\n"
        f"[dim]{_emoji_or_empty('globe')}Your browser will open to the API keys page.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()

    webbrowser.open("https://dashboard.render.com/settings/keys")

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        console.print()
        console.print(f"[dim]Attempt {attempt} of {max_attempts}[/dim]")
        
        # ✅ FIX 6: Use _safe_prompt_free() instead of raw Prompt.ask
        api_key = _safe_prompt_free(
            f"[bold cyan]{_emoji_or_empty('arrow')}[/] Paste your Render API key",
            default="",
        )

        if not api_key or not api_key.strip():
            console.print("[yellow]No API key provided. Skipping Render authentication.[/yellow]")
            return

        console.print("[dim]Verifying API key...[/dim]")
        
        user_info, owner_id = _verify_and_fetch_user(api_key.strip())

        if user_info:
            save_api_key(api_key.strip())
            console.print()
            console.print(f"[bold green]{_sym('party')} WELCOME ABOARD, {_escape_text(user_info.get('name', 'Unknown'))}! {_sym('party')}[/bold green]")
            console.print(f"[dim]{_emoji_or_empty('handshake')}Your Render account is now connected![/dim]")
            console.print("[dim]   I can now launch your projects on Render! 🚀[/dim]\n")
            return

        console.print(f"[red]{_sym('error')} Invalid API key or insufficient permissions. (attempt {attempt} of {max_attempts})[/red]")
        if attempt < max_attempts:
            # ✅ FIX 6: Use _safe_confirm instead of raw Prompt.ask
            retry = _safe_confirm(
                f"{_emoji_or_empty('arrow')} Try again?",
                default=True,
            )
            if not retry:
                break

    console.print()
    console.print("[yellow]Skipping Render authentication for now.[/yellow]")
    console.print("[dim]You can connect later with 'opun8 render'[/dim]")


# ──────────────────────────────────────────────────────────────
# DEPLOYMENT SUCCESS
# ──────────────────────────────────────────────────────────────

def deploy_success(url: str, platform: str, project_name: str) -> None:
    """Show deployment success with partner tone."""
    console.print()
    console.print(Panel(
        f"[bold green]{_sym('party')} WE DID IT, PARTNER! {_sym('party')}[/bold green]\n\n"
        f"[white]{_emoji_or_empty('globe')}Your site is now live on [bold]{_escape_text(platform.capitalize())}[/bold]![/white]\n"
        f"[cyan]{_escape_text(url)}[/cyan]\n\n"
        f"[dim]Project: {_escape_text(project_name)}[/dim]\n"
        f"[dim]Share this link with the world! {_sym('rocket')}[/dim]\n\n"
        f"[dim]{_sym('heart')} Built with love by the Kakes David Team[/dim]",
        border_style="green",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()


# ──────────────────────────────────────────────────────────────
# DOCTOR UI (Node.js download)
# ──────────────────────────────────────────────────────────────

def doctor_nodejs_missing() -> None:
    """Show Node.js missing message with partner tone."""
    console.print()
    console.print(Panel(
        f"[bold yellow]{_sym('warning')} Hmm, Node.js is missing, partner! {_sym('thinking')}[/bold yellow]\n\n"
        f"[white]I need Node.js to build and deploy your project.[/white]\n"
        f"[dim]Don't worry — I can download it for you automatically![/dim]",
        border_style="yellow",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()


def doctor_nodejs_download() -> None:
    """Show Node.js download prompt with partner tone."""
    console.print()
    console.print(Panel(
        f"[bold green]{_sym('heart')} LET'S GET YOU SET UP, PARTNER! {_sym('rocket')}[/bold green]\n\n"
        f"[white]I'll download Node.js and put it in:[/white]\n"
        f"[dim]~/.opun8/bin/node[/dim]\n"
        f"[white]This is completely safe and requires no admin rights![/white]",
        border_style="green",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()


def doctor_nodejs_success(version: str) -> None:
    """Show Node.js install success with partner tone."""
    console.print()
    console.print(f"[bold green]{_sym('party')} Node.js {_escape_text(version)} is ready to roll, partner![/bold green]")
    console.print(f"[dim]I've installed it at ~/.opun8/bin/node[/dim]")
    console.print()


# ──────────────────────────────────────────────────────────────
# MODULE EXPORTS
# ──────────────────────────────────────────────────────────────

__all__ = [
    # Core messages
    "success",
    "info",
    "warning",
    "error",
    "goodbye",
    # Screens
    "show_welcome",
    "show_help",
    # Detection
    "detection_start",
    "scanning_spinner",
    "detection_complete",
    "no_project_detected",
    # Deploy (NEW)
    "deploy_platform_start",
    "deploy_platform_menu",
    # Deploy (DEPRECATED — kept for backward compatibility)
    "show_deploy_menu",
    "show_details",
    # History
    "history_header",
    "history_list",
    "history_detail",
    # Auth
    "github_auth_start",
    "github_auth_success",
    "vercel_auth_start",
    "netlify_auth_start",
    "render_auth_start",
    # Deployment
    "deploy_success",
    # Doctor
    "doctor_nodejs_missing",
    "doctor_nodejs_download",
    "doctor_nodejs_success",
    # Safe prompts
    "_safe_prompt",
    "_safe_prompt_free",
    "_safe_confirm",
]