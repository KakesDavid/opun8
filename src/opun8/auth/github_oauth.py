"""
GitHub OAuth authentication for Opun8.
"""

import webbrowser
import requests
import json
from pathlib import Path
from typing import Optional, Dict, List
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()

# OAuth Configuration
CLIENT_ID = "Ov23li4Xo94q11E9y4Xz"
CLIENT_SECRET = "4f63ccff0474443868df3a41ba61c5f320ed52ee"
REDIRECT_URI = "http://localhost:8080/callback"
AUTHORIZE_URL = f"https://github.com/login/oauth/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&scope=repo,workflow"

# Storage for tokens
TOKEN_FILE = Path.home() / ".opun8" / "github_token.json"


def get_github_token() -> Optional[str]:
    """Get saved GitHub token."""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
                return data.get("access_token")
        except:
            return None
    return None


def get_github_user() -> Optional[Dict]:
    """Get saved GitHub user info."""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
                return data.get("user")
        except:
            return None
    return None


def save_github_token(token: str, user_info: Dict) -> None:
    """Save GitHub token locally."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": token,
            "user": user_info
        }, f, indent=2)


def login_to_github() -> Optional[str]:
    """
    Start GitHub OAuth flow.
    Opens browser for user to authorize Opun8.
    Returns access token or None.
    """
    console.print()
    console.print(Panel(
        "[bold cyan]🔐 GitHub Authentication[/bold cyan]\n\n"
        "Opun8 needs access to GitHub to:\n"
        "  • Create repositories\n"
        "  • Push your code\n"
        "  • Enable auto-deploy\n\n"
        "[dim]Your browser will open for authorization.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()
    console.print("[bold]1[/] 🔑  [white]Login with GitHub[/white]  [dim](opens browser)[/dim]")
    console.print("[bold]2[/] ⏭️  [white]Skip[/white]  [dim](deploy without GitHub)[/dim]")
    console.print()
    
    choice = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2"],
        default="1",
        show_choices=False,
    )
    
    if choice == "2":
        console.print("\n[yellow]Skipping GitHub authentication.[/yellow]")
        return None
    
    if choice != "1":
        console.print("\n[red]Invalid option.[/red]")
        return None
    
    # Open browser for OAuth
    console.print()
    console.print(f"[dim]🌐 Opening browser...[/dim]")
    console.print("[dim]If browser doesn't open, visit:[/dim]")
    console.print(f"[dim]{AUTHORIZE_URL}[/dim]")
    console.print()
    
    webbrowser.open(AUTHORIZE_URL)
    
    console.print("[bold]Waiting for GitHub to redirect back...[/bold]")
    console.print("[dim]You should see a localhost page when done.[/dim]")
    console.print()
    console.print("[yellow]📋 After authorizing, GitHub will show a code.[/yellow]")
    
    code = Prompt.ask("[bold cyan]➜[/] Paste the code from the browser")
    
    if not code:
        console.print("[red]No code provided.[/red]")
        return None
    
    return exchange_code_for_token(code)


def exchange_code_for_token(code: str) -> Optional[str]:
    """Exchange OAuth code for access token."""
    try:
        response = requests.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=30
        )
        
        data = response.json()
        
        if "access_token" in data:
            token = data["access_token"]
            
            user = get_user_info(token)
            if user:
                save_github_token(token, user)
                console.print()
                console.print(f"[bold green]✅ Connected as: {user.get('login', 'Unknown')}[/bold green]")
                console.print("[dim]Token saved securely for future use.[/dim]")
            else:
                console.print("[yellow]Could not get user info, but token saved.[/yellow]")
                save_github_token(token, {"login": "Unknown"})
            
            return token
        else:
            console.print(f"[red]Failed to get token: {data.get('error', 'Unknown error')}[/red]")
            return None
            
    except Exception as e:
        console.print(f"[red]Error exchanging code: {e}[/red]")
        return None


def get_user_info(token: str) -> Optional[Dict]:
    """Get GitHub user information."""
    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            console.print(f"[red]Failed to get user info: {response.status_code}[/red]")
            return None
    except Exception as e:
        console.print(f"[red]Error getting user info: {e}[/red]")
        return None


def is_authenticated() -> bool:
    """Check if user is authenticated with GitHub."""
    return get_github_token() is not None


def logout() -> None:
    """Remove saved GitHub token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        console.print("[green]✅ Logged out of GitHub.[/green]")
    else:
        console.print("[yellow]Not logged in.[/yellow]")


def get_authenticated_user() -> Optional[str]:
    """Get the username of the authenticated user."""
    user = get_github_user()
    if user:
        return user.get("login")
    return None


def list_github_repos(token: str = None) -> List[Dict]:
    """List all repositories for the authenticated user."""
    if token is None:
        token = get_github_token()
    
    if not token:
        return []
    
    try:
        response = requests.get(
            "https://api.github.com/user/repos",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": 50, "sort": "updated"},
            timeout=10
        )
        
        if response.status_code == 200:
            repos = response.json()
            return [
                {
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "private": repo["private"],
                    "url": repo["html_url"],
                    "description": repo.get("description", ""),
                    "updated_at": repo.get("updated_at", "")
                }
                for repo in repos
            ]
        else:
            return []
    except Exception:
        return []


def create_github_repo(token: str, name: str, description: str = "", private: bool = False) -> Optional[Dict]:
    """Create a new GitHub repository."""
    if token is None:
        token = get_github_token()
    
    if not token:
        return None
    
    try:
        response = requests.post(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "name": name,
                "description": description,
                "private": private,
                "auto_init": True
            },
            timeout=30
        )
        
        if response.status_code == 201:
            return response.json()
        else:
            return None
    except Exception:
        return None