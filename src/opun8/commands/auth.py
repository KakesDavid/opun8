"""
Authentication Commands
=======================

CLI commands for user authentication with OPUN8.

These commands allow users to:
    - Register a new account
    - Log in to existing account
    - Verify email with OTP
    - Resend OTP verification code
    - Log out of OPUN8
    - Check account status

Author: OPUN8 Team
Version: 1.1.0
"""

import typer
import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box
from typing import Optional

from opun8.services.auth_service import get_auth_service, AuthError
from opun8.services.token_manager import is_authenticated


# =============================================================================
# INITIALIZATION
# =============================================================================

console = Console(legacy_windows=True)
auth_app = typer.Typer(help="🔐 Authentication commands for OPUN8")


# =============================================================================
# CROSS-PLATFORM SECURE INPUT (Permanent Fix)
# =============================================================================

def _secure_input(prompt_text: str) -> str:
    """
    Cross-platform masked password input with visual feedback.
    Works on ALL Windows versions (including old CMD) and ALL Unix terminals.

    Features:
        - Reliable backspace handling
        - Ctrl+R toggles revealing the password as plain text
        - Revealed text auto-hides after 3 seconds of inactivity
        - Windows: uses native Console API (no ANSI dependency)
        - Unix: uses termios/tty with ANSI clear line
    """
    AUTO_HIDE_SECONDS = 3.0
    CTRL_R = "\x12"

    password_chars = []
    revealed = False
    reveal_started_at = None

    # -------------------------------------------------------------------
    # Windows Console API Helpers (Native, works on ALL Windows versions)
    # -------------------------------------------------------------------
    if sys.platform == "win32":
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32

        def get_console_handle():
            return kernel32.GetStdHandle(-11)

        def write_at_cursor(text: str):
            """Write text at current cursor position using Windows Console API."""
            handle = get_console_handle()
            written = ctypes.c_ulong()
            kernel32.WriteConsoleW(handle, text, len(text), ctypes.byref(written), None)

        def set_cursor_position(x: int, y: int):
            """Set cursor position using Windows Console API."""
            coord = ctypes.c_ulong(y * 65536 + x)
            kernel32.SetConsoleCursorPosition(get_console_handle(), coord)

        def get_cursor_position():
            """Get current cursor position using Windows Console API."""
            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [
                    ("dwSize", ctypes.c_ulong),
                    ("dwCursorPosition", ctypes.c_ulong),
                    ("wAttributes", ctypes.c_ushort),
                    ("srWindow", ctypes.c_ulong),
                    ("dwMaximumWindowSize", ctypes.c_ulong)
                ]
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            kernel32.GetConsoleScreenBufferInfo(get_console_handle(), ctypes.byref(csbi))
            x = csbi.dwCursorPosition & 0xFFFF
            y = csbi.dwCursorPosition >> 16
            return x, y

        def get_terminal_width():
            """Get terminal width using Windows Console API."""
            class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
                _fields_ = [
                    ("dwSize", ctypes.c_ulong),
                    ("dwCursorPosition", ctypes.c_ulong),
                    ("wAttributes", ctypes.c_ushort),
                    ("srWindow", ctypes.c_ulong),
                    ("dwMaximumWindowSize", ctypes.c_ulong)
                ]
            csbi = CONSOLE_SCREEN_BUFFER_INFO()
            kernel32.GetConsoleScreenBufferInfo(get_console_handle(), ctypes.byref(csbi))
            return csbi.dwSize & 0xFFFF

        def render_line():
            """Clear current line and redraw using Windows Console API."""
            x, y = get_cursor_position()
            width = get_terminal_width()
            # Move to start of line
            set_cursor_position(0, y)
            state_label = "[VISIBLE]" if revealed else "[HIDDEN]"
            content = "".join(password_chars) if revealed else "*" * len(password_chars)
            line = f"{prompt_text} {state_label}: {content}"
            # Write the line and clear the rest
            write_at_cursor(line + " " * (width - len(line)))
            # Move back to start and rewrite
            set_cursor_position(0, y)
            write_at_cursor(line)

    # -------------------------------------------------------------------
    # Unix/Linux/macOS Helpers
    # -------------------------------------------------------------------
    else:
        # ANSI clear line sequence - works on all Unix terminals
        CLEAR_LINE = "\x1b[2K\r"

        def render_line():
            """Clear current line and redraw using ANSI."""
            state_label = "[VISIBLE]" if revealed else "[HIDDEN]"
            content = "".join(password_chars) if revealed else "*" * len(password_chars)
            line = f"{prompt_text} {state_label}: {content}"
            sys.stdout.write(CLEAR_LINE + line)
            sys.stdout.flush()

    # Print the hint once before entering raw mode
    console.print("[dim]Tip: press Ctrl+R to reveal/hide what you've typed[/dim]")

    # -------------------------------------------------------------------
    # Windows
    # -------------------------------------------------------------------
    if sys.platform == "win32":
        import msvcrt

        render_line()
        while True:
            if msvcrt.kbhit():
                char = msvcrt.getch()

                if char in (b'\r', b'\n'):
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    break

                elif char == b'\x08':  # Backspace
                    if password_chars:
                        password_chars.pop()
                    render_line()

                elif char == b'\x12':  # Ctrl+R
                    revealed = not revealed
                    reveal_started_at = time.monotonic() if revealed else None
                    render_line()

                elif char in (b'\x00', b'\xe0'):
                    # Extended-key prefix (arrows, F-keys, etc.)
                    msvcrt.getch()

                else:
                    try:
                        decoded = char.decode('utf-8')
                        password_chars.append(decoded)
                        render_line()
                    except UnicodeDecodeError:
                        continue
            else:
                # Check auto-hide timeout
                if revealed and reveal_started_at is not None:
                    if time.monotonic() - reveal_started_at >= AUTO_HIDE_SECONDS:
                        revealed = False
                        reveal_started_at = None
                        render_line()
                time.sleep(0.05)

        return "".join(password_chars)

    # -------------------------------------------------------------------
    # Unix/Linux/macOS
    # -------------------------------------------------------------------
    try:
        import termios
        import tty
        import select

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            render_line()

            while True:
                if revealed and reveal_started_at is not None:
                    remaining = AUTO_HIDE_SECONDS - (time.monotonic() - reveal_started_at)
                    timeout = max(0.0, min(remaining, 0.1))
                else:
                    timeout = 0.2

                ready, _, _ = select.select([sys.stdin], [], [], timeout)

                if ready:
                    char = sys.stdin.read(1)

                    if char in ('\r', '\n'):
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        break

                    elif char == '\x7f':  # Backspace
                        if password_chars:
                            password_chars.pop()
                        render_line()

                    elif char == CTRL_R:
                        revealed = not revealed
                        reveal_started_at = time.monotonic() if revealed else None
                        render_line()

                    else:
                        password_chars.append(char)
                        render_line()
                else:
                    # Timed out - check auto-hide deadline
                    if revealed and reveal_started_at is not None:
                        if time.monotonic() - reveal_started_at >= AUTO_HIDE_SECONDS:
                            revealed = False
                            reveal_started_at = None
                            render_line()

            return "".join(password_chars)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    except Exception:
        # Fallback to getpass
        import getpass
        console.print()
        return getpass.getpass(f"{prompt_text}: ")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _prompt_for_email() -> str:
    """Prompt the user for their email address with validation."""
    while True:
        email = Prompt.ask("📧 Enter your email address")
        if "@" in email and "." in email:
            return email
        console.print("[red]❌ Please enter a valid email address (e.g., user@example.com)[/red]")


def _prompt_for_username() -> str:
    """Prompt the user for a username with validation."""
    while True:
        username = Prompt.ask("👤 Choose a username")
        if len(username) >= 3:
            return username
        console.print("[red]❌ Username must be at least 3 characters[/red]")


def _prompt_for_password() -> str:
    """Prompt the user for a password with validation and confirmation."""
    while True:
        password = _secure_input("🔒 Enter a password (min 8 characters)")
        if len(password) >= 8:
            confirm = _secure_input("🔒 Confirm password")
            if password == confirm:
                return password
            console.print("[red]❌ Passwords do not match![/red]")
        else:
            console.print("[red]❌ Password must be at least 8 characters[/red]")


def _prompt_for_otp() -> str:
    """Prompt the user for a 6-digit OTP code with validation."""
    while True:
        code = Prompt.ask("🔑 Enter 6-digit verification code")
        if len(code) == 6 and code.isdigit():
            return code
        console.print("[red]❌ Please enter exactly 6 digits[/red]")


def _display_success(message: str, emoji: str = "✅"):
    console.print(f"\n{emoji} [bold green]{message}[/bold green]\n")


def _display_error(message: str):
    console.print(f"\n❌ [bold red]{message}[/bold red]\n")


def _display_info(message: str, emoji: str = "ℹ️"):
    console.print(f"\n{emoji} [bold blue]{message}[/bold blue]\n")


def _show_welcome_banner():
    console.print()
    console.print("[bold cyan]🚀 Welcome to OPUN8![/bold cyan]")
    console.print("[dim]Build. Deploy. Scale. — One Command. Zero Friction.[/dim]")
    console.print()


# =============================================================================
# REGISTER COMMAND
# =============================================================================

@auth_app.command(name="register")
def register(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Your email address"),
    username: Optional[str] = typer.Option(None, "--username", "-u", help="Desired username"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Your password (will be prompted if not provided)"),
):
    _show_welcome_banner()
    console.print("[bold cyan]📝 Create Your OPUN8 Account[/bold cyan]\n")

    if not email:
        email = _prompt_for_email()
    if not username:
        username = _prompt_for_username()
    if not password:
        password = _prompt_for_password()

    console.print("\n[dim]📋 Account Summary:[/dim]")
    console.print(f"   📧 Email: [bold]{email}[/bold]")
    console.print(f"   👤 Username: [bold]{username}[/bold]")
    console.print(f"   🔒 Password: [bold]{'•' * 8}[/bold]")

    if not Confirm.ask("\n✨ Create account?"):
        _display_info("Registration cancelled")
        return

    with console.status("[bold yellow]Creating account..."):
        try:
            auth = get_auth_service()
            result = auth.register(email, username, password)
            console.print()
            _display_success("Account created successfully! 🎉")
            _display_info(f"Verification code sent to {email}")
            console.print("\n[dim]Next step: Verify your email with:[/dim]")
            console.print("[bold cyan]  opun8 verify[/bold cyan]")
        except AuthError as e:
            _display_error(f"Registration failed: {str(e)}")


# =============================================================================
# LOGIN COMMAND
# =============================================================================

@auth_app.command(name="login")
def login(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Your email address"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Your password (will be prompted if not provided)"),
):
    _show_welcome_banner()

    if is_authenticated():
        console.print("[yellow]⚠️  You are already logged in![/yellow]")
        if not Confirm.ask("Log in again?"):
            return

    console.print("[bold cyan]🔑 Log In to OPUN8[/bold cyan]\n")

    if not email:
        email = _prompt_for_email()
    if not password:
        password = _secure_input("🔒 Enter your password")

    with console.status("[bold yellow]Logging in..."):
        try:
            auth = get_auth_service()
            result = auth.login(email, password)
            console.print()
            _display_success("Login successful! 🎉")

            user = result.get("user", {})
            plan = user.get("plan") or "free"
            clones_remaining = user.get("clones_remaining", 3)

            console.print("\n[dim]📊 Account Status:[/dim]")
            console.print(f"   👤 User: [bold]{user.get('username', email)}[/bold]")
            console.print(f"   📊 Plan: [bold]{plan.upper()}[/bold]")
            console.print(f"   📦 Clones remaining: [bold]{clones_remaining}[/bold]")

            if plan == "free":
                console.print("\n[dim]💡 Upgrade to clone React apps:[/dim]")
                console.print("[bold cyan]  opun8 upgrade starter[/bold cyan]")
        except AuthError as e:
            _display_error(f"Login failed: {str(e)}")


# =============================================================================
# VERIFY OTP COMMAND
# =============================================================================

@auth_app.command(name="verify")
def verify(
    code: Optional[str] = typer.Option(None, "--code", "-c", help="6-digit verification code"),
):
    _show_welcome_banner()
    console.print("[bold cyan]📧 Email Verification[/bold cyan]\n")

    email = _prompt_for_email()

    if not code:
        console.print("[dim]Enter the 6-digit verification code sent to your email[/dim]")
        code = _prompt_for_otp()

    with console.status("[bold yellow]Verifying..."):
        try:
            auth = get_auth_service()
            result = auth.verify_otp(email, code)
            console.print()
            _display_success("Email verified successfully! 🎉")
            _display_info("Your account is now active. You can start cloning websites!")
            console.print("\n[dim]🚀 Ready to deploy?[/dim]")
            console.print("[bold cyan]  opun8 clone https://example.com[/bold cyan]")
        except AuthError as e:
            _display_error(f"Verification failed: {str(e)}")
            console.print("\n[dim]💡 Need a new code?[/dim]")
            console.print("[bold cyan]  opun8 resend-otp[/bold cyan]")


# =============================================================================
# RESEND OTP COMMAND
# =============================================================================

@auth_app.command(name="resend-otp")
def resend_otp():
    _show_welcome_banner()
    console.print("[bold cyan]📧 Resend Verification Code[/bold cyan]\n")

    email = _prompt_for_email()

    if not Confirm.ask(f"Send new verification code to [bold]{email}[/bold]?"):
        return

    with console.status("[bold yellow]Sending new code..."):
        try:
            auth = get_auth_service()
            result = auth.resend_otp(email)
            _display_success("New verification code sent! 📨")
            _display_info(f"Check your email at {email}")
            console.print("\n[dim]Enter the code with:[/dim]")
            console.print("[bold cyan]  opun8 verify --code XXXXXX[/bold cyan]")
        except AuthError as e:
            _display_error(f"Failed to resend code: {str(e)}")


# =============================================================================
# LOGOUT COMMAND
# =============================================================================

@auth_app.command(name="logout")
def logout(
    all_services: bool = typer.Option(False, "--all", "-a", help="Logout from ALL services"),
):
    _show_welcome_banner()

    if not is_authenticated():
        _display_info("You are not logged in.")
        return

    if not Confirm.ask("Are you sure you want to log out?"):
        _display_info("Logout cancelled")
        return

    with console.status("[bold yellow]Logging out..."):
        try:
            auth = get_auth_service()
            result = auth.logout()
            _display_success("Logged out of OPUN8")
            if all_services:
                console.print("[dim]Logging out of all services...[/dim]")
                _display_info("Logout from other services coming soon!")
            console.print("\n[dim]💡 To log in again:[/dim]")
            console.print("[bold cyan]  opun8 login[/bold cyan]")
        except AuthError as e:
            _display_error(f"Logout failed: {str(e)}")


# =============================================================================
# STATUS COMMAND
# =============================================================================

@auth_app.command(name="status")
def status():
    _show_welcome_banner()

    if not is_authenticated():
        console.print("[yellow]⚠️  You are not logged in.[/yellow]")
        console.print("\n[dim]💡 To log in:[/dim]")
        console.print("[bold cyan]  opun8 login[/bold cyan]")
        console.print("\n[dim]💡 To create an account:[/dim]")
        console.print("[bold cyan]  opun8 register[/bold cyan]")
        return

    with console.status("[bold yellow]Fetching account info..."):
        try:
            auth = get_auth_service()
            user = auth.get_user_info()

            table = Table(title="Account Details", box=box.ROUNDED, style="dim")
            table.add_column("Field", style="bold cyan", width=20)
            table.add_column("Value", style="bold white")

            plan = user.get("plan") or "free"
            clones_used = user.get("clones_used") or 0
            clones_limit = user.get("clones_limit") or 3
            clones_remaining = max(0, clones_limit - clones_used)

            table.add_row("👤 Username", user.get("username", "N/A"))
            table.add_row("📧 Email", user.get("email", "N/A"))
            table.add_row("📊 Plan", f"[bold]{plan.upper()}[/bold]")
            table.add_row("📦 Clones Used", str(clones_used))
            table.add_row("📦 Clones Remaining", f"[bold green]{clones_remaining}[/bold green]")
            table.add_row("📦 Clone Limit", str(clones_limit))
            table.add_row("🔒 Status", "✅ Active" if user.get("email_verified", True) else "⚠️ Unverified")

            console.print(table)

            if plan == "free" and clones_remaining == 0:
                console.print("\n[yellow]⚠️  You've used all your free clones![/yellow]")
                console.print("[dim]💡 Upgrade to continue cloning:[/dim]")
                console.print("[bold cyan]  opun8 upgrade starter[/bold cyan]")
            elif plan == "free":
                console.print("\n[dim]💡 Upgrade to clone React apps:[/dim]")
                console.print("[bold cyan]  opun8 upgrade starter[/bold cyan]")
        except AuthError as e:
            _display_error(f"Failed to fetch status: {str(e)}")


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "auth_app",
    "register",
    "login",
    "verify",
    "resend_otp",
    "logout",
    "status",
]