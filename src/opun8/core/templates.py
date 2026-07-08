"""
Project templates for Opun8.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class ProjectTemplates:
    """Generate project templates with user feedback."""

    TEMPLATES: Dict[str, Dict[str, Any]] = {
        "react": {
            "name": "React + Vite",
            "description": "Modern React with Vite, fast and lightweight.",
            "command": ["npm", "create", "vite@latest", "."],
            "dependencies": ["react", "react-dom"],
            "dev_dependencies": ["vite", "@vitejs/plugin-react"],
        },
        "nextjs": {
            "name": "Next.js",
            "description": "Full-stack React framework with SSR and SSG.",
            "command": ["npx", "create-next-app@latest", "."],
            "dependencies": ["next", "react", "react-dom"],
            "dev_dependencies": [],
        },
        "static": {
            "name": "Static HTML + CSS",
            "description": "Simple HTML, CSS, and JavaScript.",
            "command": None,
            "dependencies": [],
            "dev_dependencies": [],
        },
        "node": {
            "name": "Node.js API",
            "description": "Express.js REST API with JavaScript.",
            "command": ["npm", "init", "-y"],
            "dependencies": ["express", "cors", "dotenv"],
            "dev_dependencies": ["nodemon"],
        },
    }

    @classmethod
    def create_project(cls, template: str, project_name: str, path: Optional[Path] = None) -> bool:
        """Create a new project from template with progress feedback."""
        if template not in cls.TEMPLATES:
            console.print("[red]Error: Unknown template.[/red]")
            return False

        target_path = path or Path.cwd()
        project_path = target_path / project_name

        # Check if directory already exists
        if project_path.exists():
            console.print(f"[yellow]Directory '{project_name}' already exists.[/yellow]")
            overwrite = input("Overwrite? (y/N): ").strip().lower()
            if overwrite != 'y':
                console.print("[dim]Project creation cancelled.[/dim]")
                return False

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Creating project...", total=None)

            try:
                # Create project directory
                project_path.mkdir(parents=True, exist_ok=True)
                os.chdir(project_path)

                # Run template-specific creation
                if template == "react":
                    success = cls._create_react_project(project_path, project_name)
                elif template == "nextjs":
                    success = cls._create_nextjs_project(project_path, project_name)
                elif template == "static":
                    success = cls._create_static_project(project_path, project_name)
                elif template == "node":
                    success = cls._create_node_project(project_path, project_name)
                else:
                    success = False

                if success:
                    progress.update(task, description="[green]Project created successfully!")
                    return True
                else:
                    progress.update(task, description="[red]Failed to create project.")
                    return False

            except Exception as e:
                console.print(f"[red]Error creating project: {e}[/red]")
                return False

    # ──────────────────────────────────────────────────────────────
    # REACT + VITE
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _create_react_project(cls, project_path: Path, project_name: str) -> bool:
        """Create React + Vite project."""
        try:
            # Try Vite create command first
            subprocess.run(
                ["npm", "create", "vite@latest", project_name, "--", "--template", "react"],
                cwd=project_path.parent,
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to manual creation
            return cls._create_react_manual(project_path, project_name)

    @classmethod
    def _create_react_manual(cls, project_path: Path, project_name: str) -> bool:
        """Manually create React project (fallback)."""
        try:
            # package.json
            package_json = {
                "name": project_name,
                "version": "1.0.0",
                "type": "module",
                "scripts": {
                    "dev": "vite",
                    "build": "vite build",
                    "preview": "vite preview",
                },
                "dependencies": {
                    "react": "^18.3.1",
                    "react-dom": "^18.3.1",
                },
                "devDependencies": {
                    "@vitejs/plugin-react": "^4.0.0",
                    "vite": "^5.0.0",
                },
            }
            with open(project_path / "package.json", "w", encoding="utf-8") as f:
                json.dump(package_json, f, indent=2)

            # index.html
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{project_name}</title>
</head>
<body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
</body>
</html>"""
            with open(project_path / "index.html", "w", encoding="utf-8") as f:
                f.write(html)

            # src folder
            src_path = project_path / "src"
            src_path.mkdir(exist_ok=True)

            main_jsx = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)"""
            with open(src_path / "main.jsx", "w", encoding="utf-8") as f:
                f.write(main_jsx)

            app_jsx = """import React from 'react'
import './App.css'

function App() {
  return (
    <div className="App">
      <h1>Hello, Opun8!</h1>
      <p>Your React app is ready.</p>
    </div>
  )
}

export default App"""
            with open(src_path / "App.jsx", "w", encoding="utf-8") as f:
                f.write(app_jsx)

            index_css = """:root {
  font-family: Inter, system-ui, Avenir, Helvetica, Arial, sans-serif;
  line-height: 1.5;
  font-weight: 400;
  color-scheme: light dark;
  color: rgba(255, 255, 255, 0.87);
  background-color: #242424;
}
body {
  margin: 0;
  display: flex;
  place-items: center;
  min-width: 320px;
  min-height: 100vh;
}"""
            with open(src_path / "index.css", "w", encoding="utf-8") as f:
                f.write(index_css)

            app_css = """.App {
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
  text-align: center;
}
h1 {
  font-size: 3.2em;
  line-height: 1.1;
}"""
            with open(src_path / "App.css", "w", encoding="utf-8") as f:
                f.write(app_css)

            # vite.config.js
            vite_config = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})"""
            with open(project_path / "vite.config.js", "w", encoding="utf-8") as f:
                f.write(vite_config)

            # Install dependencies
            console.print("[dim]Installing dependencies (may take a moment)...[/dim]")
            subprocess.run(["npm", "install"], cwd=project_path, check=True, capture_output=True)

            return True
        except Exception as e:
            console.print(f"[red]Manual React creation failed: {e}[/red]")
            return False

    # ──────────────────────────────────────────────────────────────
    # NEXT.JS
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _create_nextjs_project(cls, project_path: Path, project_name: str) -> bool:
        """Create Next.js project."""
        try:
            subprocess.run(
                ["npx", "create-next-app@latest", project_name, "--js", "--tailwind", "--eslint"],
                cwd=project_path.parent,
                check=True,
                capture_output=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            console.print(f"[red]Next.js creation failed: {e}[/red]")
            return False

    # ──────────────────────────────────────────────────────────────
    # STATIC HTML + CSS + JS
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _create_static_project(cls, project_path: Path, project_name: str) -> bool:
        """Create static HTML project."""
        try:
            # index.html
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name}</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="container">
        <h1>Welcome to {project_name}</h1>
        <p>Your static site is ready.</p>
        <button onclick="handleClick()">Click me!</button>
    </div>
    <script src="script.js"></script>
</body>
</html>"""
            with open(project_path / "index.html", "w", encoding="utf-8") as f:
                f.write(html)

            # style.css
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
    font-size: 16px;
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

            # script.js
            js = """function handleClick() {
    alert('Hello from Opun8!');
}"""
            with open(project_path / "script.js", "w", encoding="utf-8") as f:
                f.write(js)

            return True
        except Exception as e:
            console.print(f"[red]Static creation failed: {e}[/red]")
            return False

    # ──────────────────────────────────────────────────────────────
    # NODE.JS API
    # ──────────────────────────────────────────────────────────────

    @classmethod
    def _create_node_project(cls, project_path: Path, project_name: str) -> bool:
        """Create Node.js API project."""
        try:
            # package.json
            package_json = {
                "name": project_name,
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

            # server.js
            server = """require('dotenv').config();
const express = require('express');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

// Routes
app.get('/', (req, res) => {
    res.json({ message: 'Hello from Opun8!' });
});

app.get('/health', (req, res) => {
    res.json({ status: 'OK', timestamp: new Date().toISOString() });
});

// Start server
app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});"""
            with open(project_path / "server.js", "w", encoding="utf-8") as f:
                f.write(server)

            # .env
            env = f"""PORT=3000
NODE_ENV=development"""
            with open(project_path / ".env", "w", encoding="utf-8") as f:
                f.write(env)

            console.print("[dim]Installing dependencies (may take a moment)...[/dim]")
            subprocess.run(["npm", "install"], cwd=project_path, check=True, capture_output=True)

            return True
        except Exception as e:
            console.print(f"[red]Node creation failed: {e}[/red]")
            return False