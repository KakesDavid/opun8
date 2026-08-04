"""
Environment variable service for Opun8.

Centralizes environment variable detection, parsing, and prompting across all providers.
This service is used by:
    - Vercel deploy: Detect and prompt for env vars
    - Render deploy: Detect and prompt for env vars
    - Netlify deploy: Detect and prompt for env vars
    - Future providers: Railway, etc.

Features:
    - Scans source files for env var usage (process.env, os.getenv, etc.)
    - Detects framework-specific required env vars
    - Parses .env.example and .env files
    - Interactive prompt with context (shows where vars are used)
    - Redacts sensitive values in display
    - Supports selecting specific vars to include
    - Supports target environments (production, preview, development)

✅ FIX: Added clean separation before env var display (rule + panel)
✅ FIX: Clear screen before showing env var table
✅ FIX: Consistent panel styling with the rest of the UI
✅ FIX: No more overlapping with GitHub menu text

Author: OPUN8 Team
Version: 0.1.6
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich import box

console = Console()
logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

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

# File extensions to scan for env var usage
SCAN_EXTENSIONS = {
    ".js", ".ts", ".jsx", ".tsx", ".py", ".rb", ".php",
    ".go", ".rs", ".java", ".kt", ".scala", ".sh", ".bash",
    ".yml", ".yaml", ".json", ".toml", ".ini", ".conf",
}

# Regex patterns for detecting env vars by language
ENV_PATTERNS = {
    # JavaScript / TypeScript
    "javascript": [
        re.compile(r'process\.env\.([A-Z_][A-Z0-9_]*)'),
        re.compile(r'process\.env\[["\']([A-Z_][A-Z0-9_]*)["\']\]'),
        re.compile(r'import\.meta\.env\.([A-Z_][A-Z0-9_]*)'),
        re.compile(r'import\.meta\.env\[["\']([A-Z_][A-Z0-9_]*)["\']\]'),
        re.compile(r'const\s*{\s*([A-Z_][A-Z0-9_]*)\s*}\s*=\s*process\.env'),
    ],
    # Python
    "python": [
        re.compile(r'os\.getenv\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
        re.compile(r'os\.environ\[["\']([A-Z_][A-Z0-9_]*)["\']\]'),
        re.compile(r'os\.environ\.get\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
        re.compile(r'os\.getenv\(["\']([A-Z_][A-Z0-9_]*)["\']\s*,\s*[^)]+\)'),
        re.compile(r'django\.conf\.settings\.([A-Z_][A-Z0-9_]*)'),
        re.compile(r'(?<!django\.conf\.)settings\.([A-Z_][A-Z0-9_]*)'),
    ],
    # PHP
    "php": [
        re.compile(r'getenv\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
        re.compile(r'\$_ENV\[["\']([A-Z_][A-Z0-9_]*)["\']\]'),
        re.compile(r'env\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
        re.compile(r'Config::get\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
    ],
    # Shell
    "shell": [
        re.compile(r'\$([A-Z_][A-Z0-9_]*)'),
        re.compile(r'\${([A-Z_][A-Z0-9_]*)}'),
    ],
    # Ruby
    "ruby": [
        re.compile(r'ENV\[["\']([A-Z_][A-Z0-9_]*)["\']\]'),
        re.compile(r'ENV\.fetch\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
        re.compile(r'ENV\.fetch\(["\']([A-Z_][A-Z0-9_]*)["\']\s*,\s*[^)]+\)'),
    ],
    # Go
    "go": [
        re.compile(r'os\.Getenv\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
        re.compile(r'os\.LookupEnv\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
    ],
    # Rust
    "rust": [
        re.compile(r'std::env::var\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
        re.compile(r'env::var\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
    ],
    # Java
    "java": [
        re.compile(r'System\.getenv\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
        re.compile(r'System\.getenv\(["\']([A-Z_][A-Z0-9_]*)["\']\)'),
    ],
}

# Framework-specific environment variable requirements
FRAMEWORK_ENV_VARS: Dict[str, Dict[str, str]] = {
    "react": {
        "REACT_APP_": "Custom environment variables must start with REACT_APP_",
    },
    "vite": {
        "VITE_": "Custom environment variables must start with VITE_",
    },
    "vue": {
        "VUE_APP_": "Custom environment variables must start with VUE_APP_",
    },
    "nextjs": {
        "NEXT_PUBLIC_": "Public env vars must start with NEXT_PUBLIC_",
        "DATABASE_URL": "Database connection string (required)",
        "API_URL": "Backend API URL",
        "NEXTAUTH_SECRET": "NextAuth.js secret key (required)",
        "NEXTAUTH_URL": "NextAuth.js base URL",
    },
    "django": {
        "SECRET_KEY": "Django secret key (required)",
        "DATABASE_URL": "Database connection string (required)",
        "DEBUG": "Enable debug mode (True/False)",
        "ALLOWED_HOSTS": "Comma-separated list of allowed hosts",
        "DJANGO_SETTINGS_MODULE": "Settings module path",
    },
    "flask": {
        "SECRET_KEY": "Flask secret key (required)",
        "DATABASE_URL": "Database connection string (required)",
        "DEBUG": "Enable debug mode (True/False)",
        "FLASK_APP": "Entry point for Flask application",
        "FLASK_ENV": "Environment (development/production)",
    },
    "fastapi": {
        "SECRET_KEY": "FastAPI secret key (required)",
        "DATABASE_URL": "Database connection string (required)",
        "DEBUG": "Enable debug mode (True/False)",
        "API_KEY": "API key for authentication",
    },
    "nodejs": {
        "PORT": "Port number for the server",
        "DATABASE_URL": "Database connection string (required)",
        "JWT_SECRET": "JWT secret key (required)",
        "API_KEY": "API key for authentication",
        "NODE_ENV": "Node.js environment (development/production)",
    },
    "static": {
        "API_URL": "Backend API URL for static sites",
    },
}

SENSITIVE_PATTERNS = [
    "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL",
    "SIGNATURE", "CERT", "CERTIFICATE", "ENCRYPT",
    "JWT", "SSH", "SSL", "TLS", "PRIV",
    "DATABASE_URL",
    "POSTGRES", "MYSQL", "MONGODB", "REDIS_URL",
]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def is_sensitive_env_key(key: str) -> bool:
    """
    Check if an environment variable key appears to be sensitive.

    Args:
        key: The environment variable key

    Returns:
        True if the key appears sensitive
    """
    key_upper = key.upper()
    for pattern in SENSITIVE_PATTERNS:
        if pattern in key_upper:
            return True
    return False


def redact_env_value(value: str) -> str:
    """
    Redact sensitive environment variable values for display.

    Args:
        value: The environment variable value

    Returns:
        Redacted value
    """
    if not value:
        return "(empty)"

    if "://" in value or "@" in value:
        return "********"

    if len(value) > 20:
        return "********"

    if re.search(r'[^a-zA-Z0-9_\-\.]', value):
        return "********"

    return value


def get_env_display_value(key: str, value: str) -> str:
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


def get_file_extension_language(file_path: Path) -> Optional[str]:
    """
    Determine the programming language from file extension.

    Args:
        file_path: Path to the file

    Returns:
        Language name, or None if unknown
    """
    ext = file_path.suffix.lower()
    ext_to_lang = {
        ".js": "javascript",
        ".ts": "javascript",
        ".jsx": "javascript",
        ".tsx": "javascript",
        ".py": "python",
        ".php": "php",
        ".sh": "shell",
        ".bash": "shell",
        ".rb": "ruby",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".kt": "kotlin",
        ".scala": "scala",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".ini": "ini",
        ".conf": "conf",
    }
    return ext_to_lang.get(ext)


def detect_file_language(file_path: Path) -> str:
    """
    Detect the language of a file for pattern matching.

    Args:
        file_path: Path to the file

    Returns:
        Language name, or "unknown"
    """
    lang = get_file_extension_language(file_path)
    if lang:
        return lang

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            first_line = f.readline()
            if first_line.startswith("#!"):
                if "python" in first_line.lower():
                    return "python"
                if "node" in first_line.lower() or "js" in first_line.lower():
                    return "javascript"
                if "php" in first_line.lower():
                    return "php"
                if "ruby" in first_line.lower():
                    return "ruby"
                if "bash" in first_line.lower() or "sh" in first_line.lower():
                    return "shell"
    except Exception:
        pass

    return "unknown"


# =============================================================================
# DETECTION FUNCTIONS
# =============================================================================

def detect_env_vars_from_source(
    project_path: Path,
    extensions: Optional[List[str]] = None,
) -> Dict[str, List[str]]:
    """
    Scan source files for environment variable usage.

    Args:
        project_path: Path to the project root
        extensions: List of file extensions to scan (default: all supported)

    Returns:
        Dictionary mapping env var names to list of file:line locations
    """
    result: Dict[str, List[str]] = {}

    if not project_path.exists() or not project_path.is_dir():
        return result

    if extensions is None:
        extensions = list(SCAN_EXTENSIONS)

    all_patterns = []
    for patterns in ENV_PATTERNS.values():
        all_patterns.extend(patterns)

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in {
            "node_modules", ".git", "__pycache__", ".venv", "venv",
            ".pytest_cache", ".next", ".netlify", ".vercel",
            "dist", "build", "out", ".cache", "coverage",
            ".idea", ".vscode", "vendor", "target", ".gradle",
        }]

        for file in files:
            file_path = Path(root) / file

            if file_path.suffix.lower() not in extensions:
                continue

            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            lang = detect_file_language(file_path)

            if lang == "shell":
                patterns = ENV_PATTERNS.get("shell", [])
            else:
                patterns = ENV_PATTERNS.get(lang, [])
                if not patterns and lang == "unknown":
                    patterns = all_patterns

            for pattern in patterns:
                for match in pattern.finditer(content):
                    if len(match.groups()) >= 1:
                        var_name = match.group(1)
                        if var_name:
                            rel_path = file_path.relative_to(project_path)
                            location = f"{rel_path}:{content[:match.start()].count(chr(10)) + 1}"
                            if var_name not in result:
                                result[var_name] = []
                            if location not in result[var_name]:
                                result[var_name].append(location)

    return result


def detect_env_vars_from_dotenv_example(project_path: Path) -> Dict[str, str]:
    """
    Parse .env.example, .env.sample, and .env.defaults files.

    Merges all found files instead of stopping at first.

    Args:
        project_path: Path to the project root

    Returns:
        Dictionary mapping env var names to their example/default values
    """
    result: Dict[str, str] = {}
    patterns = [".env.example", ".env.sample", ".env.defaults"]

    for pattern in patterns:
        file_path = project_path / pattern
        if file_path.exists() and file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                parsed = parse_env_content(content, source=pattern)
                result = merge_env_vars(result, parsed, prefer="existing")
            except Exception:
                continue

    return result


def detect_env_vars_from_framework(
    project_path: Path,
    framework: str,
) -> Dict[str, str]:
    """
    Get framework-specific environment variable requirements.

    Args:
        project_path: Path to the project root
        framework: Detected framework name

    Returns:
        Dictionary mapping env var names to their descriptions
    """
    framework_normalized = framework.lower().replace(".", "").replace("-", "")

    framework_vars = FRAMEWORK_ENV_VARS.get(framework_normalized)
    if framework_vars is None:
        for key in FRAMEWORK_ENV_VARS:
            if key in framework_normalized:
                framework_vars = FRAMEWORK_ENV_VARS[key]
                break

    result: Dict[str, str] = {}
    if framework_vars:
        result = dict(framework_vars)

    if "nextjs" in framework_normalized:
        env_files = detect_env_files(project_path)
        for env_file in env_files:
            try:
                content = env_file.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key = line.split("=", 1)[0].strip()
                        if key.startswith("NEXT_PUBLIC_"):
                            result[key] = "Next.js public env var"
            except Exception:
                continue

    if "vite" in framework_normalized:
        env_files = detect_env_files(project_path)
        for env_file in env_files:
            try:
                content = env_file.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key = line.split("=", 1)[0].strip()
                        if key.startswith("VITE_"):
                            result[key] = "Vite env var"
            except Exception:
                continue

    return result


def detect_required_env_vars(
    project_path: Path,
    framework: str,
) -> Dict[str, Dict[str, Any]]:
    """
    Main entry point for detecting required environment variables.

    Combines results from:
        1. Source code scanning
        2. .env.example parsing
        3. Framework-specific detection

    Args:
        project_path: Path to the project root
        framework: Detected framework name

    Returns:
        Dictionary mapping env var names to their metadata:
            {
                "sources": ["file1.py:15", "file2.js:42"],
                "default": "optional default value",
                "description": "What this var is for",
                "sensitive": True/False,
            }
    """
    result: Dict[str, Dict[str, Any]] = {}

    source_vars = detect_env_vars_from_source(project_path)
    for var_name, locations in source_vars.items():
        result[var_name] = {
            "sources": locations,
            "default": None,
            "description": f"Used in {len(locations)} file(s)",
            "sensitive": is_sensitive_env_key(var_name),
            "from_framework": False,
        }

    example_vars = detect_env_vars_from_dotenv_example(project_path)
    for var_name, default_value in example_vars.items():
        if var_name in result:
            result[var_name]["default"] = default_value
            result[var_name]["description"] = "From .env.example"
        else:
            result[var_name] = {
                "sources": [],
                "default": default_value,
                "description": "From .env.example",
                "sensitive": is_sensitive_env_key(var_name),
                "from_framework": False,
            }

    framework_vars = detect_env_vars_from_framework(project_path, framework)
    for var_name, description in framework_vars.items():
        if var_name in result:
            result[var_name]["description"] = description
            result[var_name]["from_framework"] = True
        else:
            result[var_name] = {
                "sources": [],
                "default": None,
                "description": description,
                "sensitive": is_sensitive_env_key(var_name),
                "from_framework": True,
            }

    return result


# =============================================================================
# ENV FILE PARSING
# =============================================================================

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

    line_re = re.compile(
        r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$"
    )

    for line_num, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        match = line_re.match(line)
        if not match:
            errors.append(f"Line {line_num}: {line.strip()}")
            continue

        key, value = match.group(1), match.group(2)

        is_double_quoted = False
        is_single_quoted = False
        if len(value) >= 2:
            if value[0] == '"' and value[-1] == '"':
                is_double_quoted = True
                value = value[1:-1]
            elif value[0] == "'" and value[-1] == "'":
                is_single_quoted = True
                value = value[1:-1]

        if not is_double_quoted and not is_single_quoted:
            if "#" in value:
                for i, char in enumerate(value):
                    if char == "#" and (i == 0 or value[i-1].isspace()):
                        value = value[:i].rstrip()
                        break

        if is_double_quoted:
            value = value.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')
            value = value.replace('\\\\', '\\')
            value = value.replace('\\"', '"')
        elif is_single_quoted:
            value = value.replace("\\'", "'").replace("\\\\", "\\")

        values[key] = value

    if errors:
        logger.debug(f"Skipped {len(errors)} malformed line(s) in {source}")

    return values


def load_env_file(file_path: Path) -> Dict[str, str]:
    """
    Load a .env file into a dictionary.

    Args:
        file_path: Path to the .env file

    Returns:
        Dictionary of key-value pairs
    """
    if not file_path.exists() or not file_path.is_file():
        return {}

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return parse_env_content(content, source=file_path.name)
    except Exception as e:
        logger.warning(f"Could not read {file_path.name}: {e}")
        return {}


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
        if key in result and prefer == "existing":
            continue
        result[key] = value

    return result


# =============================================================================
# INTERACTIVE PROMPTS  ✅ FIXED
# =============================================================================

def display_detected_vars(
    detected_vars: Dict[str, Dict[str, Any]],
    show_sources: bool = True,
) -> Tuple[List[str], List[str]]:
    """
    Display detected environment variables to the user with interactive selection.

    ✅ FIX: Clean separation from other UI elements (rule + panel)
    ✅ FIX: Consistent styling with the rest of the UI

    Args:
        detected_vars: Dictionary of detected vars with metadata
        show_sources: Whether to show source file locations

    Returns:
        Tuple of (selected_vars, all_vars)
    """
    if not detected_vars:
        console.print("[dim]No environment variables detected.[/dim]")
        return [], []

    var_names = sorted(detected_vars.keys())
    selected_vars = list(var_names)

    while True:
        console.clear()
        
        # ✅ FIX: Clean separation with rule and panel
        console.print()
        console.rule("[bold cyan]🔐 Environment Variables[/bold cyan]")
        console.print()
        
        console.print(Panel(
            "[bold]Select environment variables to include.[/bold]\n"
            "[dim]Toggle by number, or use 'a' for all, 'n' for none.[/dim]",
            border_style="cyan",
            padding=(1, 2),
            width=70,
        ))
        console.print()

        table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=4)
        table.add_column("Select", style="dim", width=6)
        table.add_column("Variable", style="bold white")
        table.add_column("Value / Default", style="dim")
        table.add_column("Description", style="dim")

        for idx, var_name in enumerate(var_names, 1):
            meta = detected_vars[var_name]
            is_selected = var_name in selected_vars

            default_value = meta.get("default")
            if default_value is None:
                default_value = ""
            else:
                default_value = str(default_value)

            is_sensitive = meta.get("sensitive", False)
            if is_sensitive:
                display_value = "********"
            else:
                display_value = redact_env_value(default_value)

            source_count = len(meta.get("sources", []))
            if source_count > 0:
                desc = f"Used in {source_count} file(s)"
            else:
                desc = meta.get("description", "")

            checkbox = "[x]" if is_selected else "[ ]"
            table.add_row(
                str(idx),
                checkbox,
                var_name,
                display_value or "(none)",
                desc[:40] + ("..." if len(desc) > 40 else ""),
            )

        console.print(table)

        console.print()
        console.print("[bold]Commands:[/bold]")
        console.print("  [bold cyan]<number>[/]  Toggle selection for that variable")
        console.print("  [bold cyan]a[/]           Select all")
        console.print("  [bold cyan]n[/]           Select none")
        console.print("  [bold cyan]d[/]           Done — proceed with selected")
        console.print("  [bold cyan]q[/]           Cancel")

        choice = Prompt.ask(
            "[bold cyan]➜[/] Enter command",
            default="d",
            show_choices=False,
        )

        if choice.lower() == "q":
            return [], var_names

        if choice.lower() == "d":
            break

        if choice.lower() == "a":
            selected_vars = list(var_names)
            continue

        if choice.lower() == "n":
            selected_vars = []
            continue

        try:
            idx = int(choice)
            if 1 <= idx <= len(var_names):
                var_name = var_names[idx - 1]
                if var_name in selected_vars:
                    selected_vars.remove(var_name)
                else:
                    selected_vars.append(var_name)
                    selected_vars = sorted(selected_vars, key=lambda x: var_names.index(x))
            else:
                console.print("[red]Invalid number.[/red]")
        except ValueError:
            console.print("[red]Invalid command.[/red]")

    if not selected_vars:
        console.print("[yellow]No environment variables selected.[/yellow]")

    return selected_vars, var_names


def prompt_env_var_values(
    selected_vars: List[str],
    detected_vars: Dict[str, Dict[str, Any]],
    existing_values: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Prompt the user for values for selected environment variables.

    Args:
        selected_vars: List of variable names to prompt for
        detected_vars: Dictionary of detected vars with metadata
        existing_values: Existing values from .env file

    Returns:
        Dictionary of env var values entered by the user
    """
    result: Dict[str, str] = {}

    if not selected_vars:
        return result

    if existing_values is None:
        existing_values = {}

    console.print()
    console.print(Panel(
        "[bold cyan]✏️ Enter Environment Variable Values[/bold cyan]\n"
        "[dim]Leave blank to skip (use existing value or skip entirely)[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=70,
    ))
    console.print()

    for var_name in selected_vars:
        meta = detected_vars.get(var_name, {})

        default_value = meta.get("default")
        if default_value is None:
            default_value = ""
        else:
            default_value = str(default_value)

        if var_name in existing_values:
            default_value = existing_values[var_name]

        sources = meta.get("sources", [])
        if sources:
            context = f"used in {', '.join(sources[:3])}"
            if len(sources) > 3:
                context += f" and {len(sources) - 3} more"
        else:
            context = meta.get("description", "")

        is_sensitive = is_sensitive_env_key(var_name)

        prompt_text = f"[bold]{var_name}[/bold]"
        if context:
            prompt_text += f" [dim]({context})[/dim]"

        if is_sensitive and default_value:
            display_default = "********"
        else:
            display_default = default_value[:30] + "..." if len(default_value) > 30 else default_value

        if display_default:
            prompt_text += f" [dim]default: {display_default}[/dim]"

        value = Prompt.ask(
            prompt_text,
            default=default_value if not is_sensitive else "",
            show_default=False,
            password=is_sensitive,
        )

        if value.strip():
            result[var_name] = value.strip()
        elif default_value:
            result[var_name] = default_value

    return result


def interactive_env_prompt(
    project_path: Path,
    framework: str,
    existing_env_vars: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Full interactive flow for environment variable configuration.

    Args:
        project_path: Path to the project root
        framework: Detected framework name
        existing_env_vars: Existing env vars from .env file

    Returns:
        Dictionary of environment variables to deploy
    """
    try:
        detected_vars = detect_required_env_vars(project_path, framework)
    except Exception as e:
        logger.exception(f"Failed to detect env vars: {e}")
        console.print("[yellow]⚠️ Could not detect environment variables.[/yellow]")
        return {}

    if not detected_vars:
        console.print("[dim]No environment variables detected. Deploying without env vars.[/dim]")
        return {}

    selected_vars, all_vars = display_detected_vars(detected_vars)

    if not selected_vars:
        console.print("[yellow]No environment variables selected.[/yellow]")
        return {}

    console.print()
    if not Confirm.ask(
        f"[bold cyan]➜[/] Proceed with {len(selected_vars)} environment variable(s)?",
        default=True,
    ):
        console.print("[yellow]Skipping environment variables.[/yellow]")
        return {}

    env_values = prompt_env_var_values(
        selected_vars,
        detected_vars,
        existing_env_vars,
    )

    if not env_values:
        console.print("[yellow]No values provided. Skipping environment variables.[/yellow]")
        return {}

    console.print()
    console.print(f"[green]✅ Selected {len(env_values)} environment variable(s) for deployment[/green]")

    sensitive_count = sum(1 for k in env_values.keys() if is_sensitive_env_key(k))
    if sensitive_count:
        console.print(f"[dim]🔒 {sensitive_count} sensitive value(s) hidden from display[/dim]")

    return env_values


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def prompt_for_env_vars(
    project_path: Path,
    env_targets: Optional[List[str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Main entry point for environment variable prompting.

    This function is used by all providers (Vercel, Render, Netlify).

    Args:
        project_path: Path to the project root
        env_targets: Optional list of target environments (filtering)
                     Note: Currently this parameter is a no-op as filtering
                     is not yet implemented. It's kept for API compatibility.

    Returns:
        Tuple of (selected_env_vars, target_environments)
    """
    framework = "unknown"
    try:
        from opun8.core.detector import detect_project
        project_info = detect_project(str(project_path))
        framework = project_info.framework
        logger.debug(f"Detected framework: {framework}")
    except Exception as e:
        logger.exception(f"Failed to detect project framework: {e}")

    env_files = detect_env_files(project_path)
    existing_vars: Dict[str, str] = {}
    for env_file in env_files:
        vars_from_file = load_env_file(env_file)
        if vars_from_file:
            existing_vars = merge_env_vars(existing_vars, vars_from_file, prefer="new")

    env_vars = interactive_env_prompt(project_path, framework, existing_vars)

    if not env_vars:
        return {}, env_targets or []

    targets = env_targets or ["production"]

    return env_vars, targets


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

def prompt_env_files_selection(
    project_path: Path,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Legacy function for backward compatibility with existing providers.

    Delegates to prompt_for_env_vars() for the actual logic.

    Args:
        project_path: Path to the project root

    Returns:
        Tuple of (selected_env_vars, target_environments)
    """
    return prompt_for_env_vars(project_path)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Detection
    "detect_env_files",
    "parse_env_content",
    "load_env_file",
    "merge_env_vars",
    "detect_required_env_vars",
    "detect_env_vars_from_source",
    "detect_env_vars_from_dotenv_example",
    "detect_env_vars_from_framework",
    # Prompting
    "prompt_for_env_vars",
    "prompt_env_files_selection",
    "interactive_env_prompt",
    "display_detected_vars",
    "prompt_env_var_values",
    # Utilities
    "is_sensitive_env_key",
    "redact_env_value",
    "get_env_display_value",
]