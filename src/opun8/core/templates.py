"""
Project templates for Opun8.
Fetches templates from remote sources instead of storing code locally.
"""

import os
import subprocess
import zipfile
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console

import requests

console = Console()


class ProjectTemplates:
    """Fetch and create project templates from remote sources."""

    TEMPLATES = {
        "react": {
            "name": "React + Vite",
            "description": "Modern React with Vite, fast and lightweight.",
            "source": "https://github.com/KakesDavid/opun8-template-react/archive/master.zip",
            "dependencies": [],
            "dev_dependencies": [],
        },
        "nextjs": {
            "name": "Next.js",
            "description": "Full-stack React framework with SSR and SSG.",
            "source": None,  # Placeholder - will implement later
            "dependencies": [],
            "dev_dependencies": [],
        },
        "static": {
            "name": "Static HTML + CSS",
            "description": "Simple HTML, CSS, and JavaScript.",
            "source": None,  # Created locally
            "dependencies": [],
            "dev_dependencies": [],
        },
        "node": {
            "name": "Node.js API",
            "description": "Express.js REST API with JavaScript.",
            "source": None,  # Created locally
            "dependencies": [],
            "dev_dependencies": [],
        },
    }

    @classmethod
    def create_project(cls, template: str, project_name: str, path: Optional[Path] = None) -> bool:
        """Create a new project from template."""
        if template not in cls.TEMPLATES:
            console.print("[red]Error: Unknown template.[/red]")
            return False

        target_path = path or Path.cwd()
        project_path = target_path / project_name

        if project_path.exists():
            console.print(f"[yellow]Directory '{project_name}' already exists.[/yellow]")
            return False

        project_path.mkdir(parents=True, exist_ok=True)

        template_config = cls.TEMPLATES[template]

        if template_config["source"]:
            # Fetch from remote source
            return cls._create_from_remote(template, project_path, template_config)
        else:
            # Create locally (static or node)
            return cls._create_locally(template, project_path)

    @classmethod
    def _create_from_remote(cls, template: str, project_path: Path, config: Dict) -> bool:
        """Fetch and extract template from remote source."""
        try:
            console.print("[dim]📥 Downloading template...[/dim]")

            # Download ZIP
            response = requests.get(config["source"], timeout=60)
            response.raise_for_status()

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_file:
                tmp_file.write(response.content)
                zip_path = tmp_file.name

            console.print("[dim]📦 Extracting template...[/dim]")

            # Extract to a temporary directory
            extract_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find the extracted folder (GitHub wraps everything in a root folder)
            extracted_items = list(Path(extract_dir).iterdir())

            # If there's exactly one folder and it contains a package.json, it's the wrapper
            if len(extracted_items) == 1 and extracted_items[0].is_dir():
                source_folder = extracted_items[0]
            else:
                # If multiple items, it's already flat
                source_folder = Path(extract_dir)

            # Move all contents from source_folder to project_path
            for item in source_folder.iterdir():
                dest = project_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

            # Clean up
            os.unlink(zip_path)
            shutil.rmtree(extract_dir)

            # Remove .git folder if it exists
            git_folder = project_path / ".git"
            if git_folder.exists():
                shutil.rmtree(git_folder)

            # Check if package.json exists after extraction
            if (project_path / "package.json").exists():
                console.print("[green]✅ Template downloaded and extracted successfully![/green]")
                return True
            else:
                console.print("[red]❌ Extraction failed: package.json not found.[/red]")
                return False

        except Exception as e:
            console.print(f"[red]Failed to fetch template: {e}[/red]")
            return False

    @classmethod
    def _create_locally(cls, template: str, project_path: Path) -> bool:
        """Create template locally (for static and node templates)."""
        if template == "static":
            return cls._create_static_project(project_path)
        elif template == "node":
            return cls._create_node_project(project_path)
        return False

    @classmethod
    def _create_static_project(cls, project_path: Path) -> bool:
        """Create static HTML project."""
        try:
            html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>My Static Site</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <h1>Welcome to Opun8</h1>
        <p>Your static site is ready.</p>
        <button onclick="handleClick()">Click me!</button>
    </div>
    <script src="script.js"></script>
</body>
</html>"""
            with open(project_path / "index.html", "w", encoding="utf-8") as f:
                f.write(html)

            css = """* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    background: #f0f2f5;
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100vh;
}

.container {
    text-align: center;
    padding: 40px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
    max-width: 500px;
    width: 90%;
}

h1 {
    color: #1a1a1a;
    margin-bottom: 16px;
}

p {
    color: #666;
    margin-bottom: 24px;
}

button {
    padding: 12px 32px;
    background: #007bff;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 16px;
    font-weight: 600;
    transition: background 0.2s;
}

button:hover {
    background: #0056b3;
}"""
            with open(project_path / "style.css", "w", encoding="utf-8") as f:
                f.write(css)

            js = """function handleClick() {
    alert('Hello from Opun8!');
}"""
            with open(project_path / "script.js", "w", encoding="utf-8") as f:
                f.write(js)

            return True
        except Exception as e:
            console.print(f"[red]Static creation failed: {e}[/red]")
            return False

    @classmethod
    def _create_node_project(cls, project_path: Path) -> bool:
        """Create Node.js API project."""
        try:
            import json

            package_json = {
                "name": project_path.name,
                "version": "1.0.0",
                "description": "Node.js API with Express",
                "main": "server.js",
                "scripts": {
                    "start": "node server.js",
                    "dev": "nodemon server.js",
                },
                "dependencies": {
                    "express": "^4.18.2",
                    "cors": "^2.8.5",
                    "dotenv": "^16.0.3",
                },
                "devDependencies": {
                    "nodemon": "^2.0.22",
                },
            }
            with open(project_path / "package.json", "w", encoding="utf-8") as f:
                json.dump(package_json, f, indent=2)

            server_js = """require('dotenv').config();
const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

app.get('/', (req, res) => {
    res.json({ message: 'Hello from Opun8!' });
});

app.get('/health', (req, res) => {
    res.json({ status: 'OK', timestamp: new Date().toISOString() });
});

app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});"""
            with open(project_path / "server.js", "w", encoding="utf-8") as f:
                f.write(server_js)

            env = f"""PORT=3000
NODE_ENV=development"""
            with open(project_path / ".env", "w", encoding="utf-8") as f:
                f.write(env)

            console.print("[dim]Installing dependencies...[/dim]")
            subprocess.run(["npm", "install"], cwd=project_path, check=True, capture_output=True)

            return True
        except Exception as e:
            console.print(f"[red]Node creation failed: {e}[/red]")
            return False