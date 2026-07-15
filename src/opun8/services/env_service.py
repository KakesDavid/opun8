"""
Environment variable service for Opun8.

Centralizes environment variable detection, parsing, and prompting across all providers.
This service is used by:
    - Vercel deploy: Detect and prompt for env vars
    - Render deploy: Detect and prompt for env vars
    - Future providers: Netlify, Railway, etc.

Features:
    - Auto-detects .env files in project root
    - Parses .env, .env.local, .env.production, .env.development, .env.test
    - Interactive prompt for selecting which variables to include
    - Interactive prompt for selecting target environments
    - Merging with conflict resolution
    - Secure handling of sensitive values
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()

# Environment file patterns to detect
ENV_FILE_PATTERNS = [
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    ".env.staging",
    ".env.dev",
    ".env.ci",
]

# Regex for parsing env lines (supports export, quotes, comments)
_ENV_LINE_RE = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$"
)


# ──────────────────────────────────────────────────────────────
# DETECTION
# ──────────────────────────────────────────────────────────────

def detect_env_files(project_path: Path) -> List[Path]:
    """
    Detect all environment files in the project root.

    Args:
        project_path: Path to the project root

    Returns:
        List of detected .env file paths
    """
    if not project_path.exists() or not project_path.is_dir():
        return []

    detected = []
    for pattern in ENV_FILE_PATTERNS:
        file_path = project_path / pattern
        if file_path.exists() and file_path.is_file():
            detected.append(file_path)

    return detected


def parse_env_file(file_path: Path) -> Dict[str, str]:
    """
    Parse a .env file into key-value pairs.

    Args:
        file_path: Path to the .env file

    Returns:
        Dictionary of key-value pairs
    """
    if not file_path.exists() or not file_path.is_file():
        return {}

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        console.print(f"[yellow]⚠️ Could not read {file_path.name}: {e}[/yellow]")
        return {}

    return parse_env_content(content, source=file_path.name)


def parse_env_content(content: str, source: str = "unknown") -> Dict[str, str]:
    """
    Parse raw .env content into key-value pairs.

    Supports:
        - KEY=VALUE
        - export KEY=VALUE
        - Single and double quoted values
        - Trailing comments (only for unquoted values)
        - Blank lines and full-line comments

    Args:
        content: Raw .env file content
        source: Source name for debug logging

    Returns:
        Dictionary of key-value pairs
    """
    values: Dict[str, str] = {}
    errors: List[str] = []

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = _ENV_LINE_RE.match(line)
        if not match:
            # Skip malformed lines but track them for debugging
            if not line.strip().startswith("#"):
                errors.append(f"Line {line_num}: {line.strip()}")
            continue

        key, value = match.group(1), match.group(2)

        # Strip quotes
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        elif "#" in value:
            # Trailing comment (only for unquoted values)
            value = value.split("#", 1)[0].rstrip()

        # Handle escaped characters
        value = value.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
        value = value.replace('\\\\', '\\')

        values[key] = value

    if errors:
        console.print(f"[yellow]⚠️ Skipped {len(errors)} malformed line(s) in {source}[/yellow]")

    return values


def merge_env_vars(
    existing: Dict[str, str],
    new: Dict[str, str],
    prefer: str = "new",
) -> Dict[str, str]:
    """
    Merge two environment variable dictionaries with conflict resolution.

    Args:
        existing: Existing environment variables
        new: New environment variables
        prefer: Which to prefer on conflict ('new' or 'existing')

    Returns:
        Merged dictionary
    """
    result = dict(existing)

    for key, value in new.items():
        if key in result:
            if prefer == "new":
                result[key] = value
            # If prefer == 'existing', keep the existing value
        else:
            result[key] = value

    return result


# ──────────────────────────────────────────────────────────────
# PROMPTING
# ──────────────────────────────────────────────────────────────

def prompt_env_vars_detected(
    env_vars: Dict[str, str],
    source: str,
) -> bool:
    """
    Prompt the user whether to use detected environment variables.

    Args:
        env_vars: Detected environment variables
        source: Source description (e.g., ".env.production")

    Returns:
        True if the user wants to use them, False otherwise
    """
    if not env_vars:
        return False

    console.print()
    console.print(f"[cyan]🔐 Detected environment variables from {source}[/cyan]")
    console.print(f"[dim]Found {len(env_vars)} variable(s)[/dim]")

    # Show a preview of the variables (without values for security)
    var_names = list(env_vars.keys())
    preview = ", ".join(var_names[:10])
    if len(var_names) > 10:
        preview += f" and {len(var_names) - 10} more"

    console.print(f"[dim]Keys: {preview}[/dim]")

    return Confirm.ask(
        "[bold cyan]➜[/] Include these environment variables in the deployment?",
        default=True,
    )


def prompt_select_env_vars(
    env_vars: Dict[str, str],
    source: str = "detected environment variables",
) -> Dict[str, str]:
    """
    Allow the user to select which environment variables to include.

    Args:
        env_vars: Dictionary of environment variables
        source: Source description for the prompt

    Returns:
        Selected environment variables
    """
    if not env_vars:
        return {}

    console.print()
    console.print(f"[bold]Select environment variables to include from {source}:[/bold]")

    # Show the variables in a table
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("#", style="dim", width=4)
    table.add_column("Key", style="bold white", width=25)
    table.add_column("Value Preview", style="dim", width=30)

    var_list = list(env_vars.items())
    for i, (key, value) in enumerate(var_list, 1):
        # Show first 20 characters of value, hiding sensitive ones
        if len(value) > 20:
            preview = value[:20] + "..."
        else:
            preview = value

        # Hide long values
        if len(value) > 50:
            preview = "********"

        table.add_row(str(i), key, preview)

    console.print(table)

    console.print()
    console.print("  [bold cyan]a[/] [white]Include all[/white]")
    console.print("  [bold cyan]n[/] [white]Include none[/white]")
    console.print("  [bold cyan]1-9[/] [white]Include specific variables (comma-separated)[/white]")
    console.print()

    choice = Prompt.ask(
        "[bold cyan]➜[/] Select",
        choices=["a", "n"],
        default="a",
        show_choices=False,
    )

    if choice == "a":
        return dict(env_vars)
    elif choice == "n":
        return {}

    # Parse comma-separated indices
    selected: Dict[str, str] = {}
    try:
        indices = [int(x.strip()) for x in choice.split(",") if x.strip().isdigit()]
        for idx in indices:
            if 1 <= idx <= len(var_list):
                key, value = var_list[idx - 1]
                selected[key] = value
    except ValueError:
        console.print("[yellow]Invalid selection. No variables selected.[/yellow]")

    return selected


def prompt_env_targets() -> List[str]:
    """
    Prompt the user to select which environments to target.

    Returns:
        List of target environments (e.g., ['production', 'preview', 'development'])
    """
    console.print()
    console.print("[bold]Which environments should these variables apply to?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] [white]Production only[/white]")
    console.print("  [bold cyan]2[/] [white]Preview only[/white]")
    console.print("  [bold cyan]3[/] [white]Development only[/white]")
    console.print("  [bold cyan]4[/] [white]All environments[/white]  [dim](recommended)[/dim]")
    console.print("  [bold cyan]5[/] [white]Custom selection[/white]")
    console.print()

    choice = Prompt.ask(
        "[bold cyan]➜[/] Select",
        choices=["1", "2", "3", "4", "5"],
        default="4",
        show_choices=False,
    )

    if choice == "1":
        return ["production"]
    elif choice == "2":
        return ["preview"]
    elif choice == "3":
        return ["development"]
    elif choice == "4":
        return ["production", "preview", "development"]
    else:  # choice == "5"
        return _prompt_custom_targets()


def _prompt_custom_targets() -> List[str]:
    """Prompt for custom environment targets."""
    console.print()
    console.print("[dim]Enter comma-separated environments (e.g., production,preview)[/dim]")
    console.print("[dim]Available: production, preview, development[/dim]")

    targets_input = Prompt.ask(
        "[bold cyan]➜[/] Environments",
        default="production",
    )

    targets = [t.strip().lower() for t in targets_input.split(",") if t.strip()]
    valid_targets = {"production", "preview", "development"}

    # Filter valid targets
    selected = [t for t in targets if t in valid_targets]
    if not selected:
        console.print("[yellow]No valid targets selected. Using production only.[/yellow]")
        return ["production"]

    return selected


def prompt_env_files_selection(
    project_path: Path,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Full interactive flow for detecting and selecting environment variables.

    Args:
        project_path: Path to the project root

    Returns:
        Tuple of (selected_env_vars, target_environments)
    """
    # Detect environment files
    env_files = detect_env_files(project_path)

    if not env_files:
        console.print("[dim]ℹ️ No .env files found in project root.[/dim]")
        return {}, []

    # Parse all env files
    all_vars: Dict[str, str] = {}
    for env_file in env_files:
        vars_from_file = parse_env_file(env_file)
        if vars_from_file:
            all_vars = merge_env_vars(all_vars, vars_from_file, prefer="new")

    if not all_vars:
        console.print("[dim]ℹ️ No valid environment variables found in .env files.[/dim]")
        return {}, []

    # Prompt user
    console.print()
    console.print("[bold cyan]🔐 Environment Variables Detected[/bold cyan]")

    # Show which files were found
    file_names = ", ".join(f.name for f in env_files)
    console.print(f"[dim]Found in: {file_names}[/dim]")

    # Ask if they want to use them
    if not prompt_env_vars_detected(all_vars, file_names):
        console.print("[yellow]Skipping environment variables.[/yellow]")
        return {}, []

    # Ask which variables to include
    selected = prompt_select_env_vars(all_vars, "detected environment variables")

    if not selected:
        console.print("[yellow]No variables selected.[/yellow]")
        return {}, []

    # Ask which environments to target
    targets = prompt_env_targets()

    console.print()
    console.print(f"[green]✅ Including {len(selected)} environment variable(s)[/green]")
    console.print(f"[dim]Targets: {', '.join(targets)}[/dim]")

    return selected, targets


# ──────────────────────────────────────────────────────────────
# SECURE HELPERS
# ──────────────────────────────────────────────────────────────

def redact_env_value(value: str) -> str:
    """
    Redact sensitive environment variable values for display.

    Args:
        value: The environment variable value

    Returns:
        Redacted value
    """
    # If it looks like a secret (long, mixed case, special chars)
    if len(value) > 20:
        return "********"  # nosec
    if re.search(r'[^a-zA-Z0-9_\-\.]', value):
        return "********"  # nosec

    # Show preview for non-sensitive values
    if len(value) > 10:
        return value[:8] + "..."

    return value


def is_sensitive_env_key(key: str) -> bool:
    """
    Check if an environment variable key appears to be sensitive.

    Args:
        key: The environment variable key

    Returns:
        True if the key appears sensitive
    """
    sensitive_patterns = [
        "SECRET", "TOKEN", "KEY", "PASSWORD", "PASS", "AUTH",
        "API", "PRIVATE", "ACCESS", "CLIENT", "CREDENTIAL",
        "SIGNATURE", "CERT", "CERTIFICATE", "ENCRYPT",
    ]

    key_upper = key.upper()
    for pattern in sensitive_patterns:
        if pattern in key_upper:
            return True

    return False


def get_env_var_display_value(key: str, value: str) -> str:
    """
    Get a display-safe version of an environment variable value.

    Args:
        key: The environment variable key
        value: The environment variable value

    Returns:
        Display-safe value
    """
    if is_sensitive_env_key(key):
        return "********"

    return redact_env_value(value)