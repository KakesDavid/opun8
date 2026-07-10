"""
Project detection for Opun8.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional


class ProjectDetector:
    """Detect project type and configuration."""

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()
        self.project_data = {}

    def detect(self) -> Dict[str, Any]:
        """Detect project type and return project information."""
        result = {
            "name": self.project_path.name,
            "path": str(self.project_path.absolute()),
            "type": "unknown",
            "package_manager": None,
            "build_command": None,
            "output_dir": None,
            "dependencies": [],
            "dev_dependencies": [],
            "node_version": None,
            "framework": None,
            "is_detected": False,
        }

        # Check for package.json
        package_json = self.project_path / "package.json"
        if package_json.exists():
            result = self._detect_node_project(package_json, result)
            result["is_detected"] = "error" not in result
            return result

        # Check for index.html
        index_html = self.project_path / "index.html"
        if index_html.exists():
            result["type"] = "static"
            result["framework"] = "HTML"
            result["is_detected"] = True
            return result

        # Check for requirements.txt
        requirements = self.project_path / "requirements.txt"
        if requirements.exists():
            result["type"] = "python"
            result["framework"] = "Python"
            result["is_detected"] = True
            return result

        return result

    def _detect_node_project(self, package_json: Path, result: Dict) -> Dict:
        """Detect Node.js project details."""
        try:
            with open(package_json, "r", encoding="utf-8") as f:
                data = json.load(f)

            result["type"] = "node"
            result["name"] = data.get("name", self.project_path.name)

            # Package manager detection
            if (self.project_path / "pnpm-lock.yaml").exists():
                result["package_manager"] = "pnpm"
            elif (self.project_path / "yarn.lock").exists():
                result["package_manager"] = "yarn"
            elif (self.project_path / "package-lock.json").exists():
                result["package_manager"] = "npm"

            # Dependencies
            result["dependencies"] = list(data.get("dependencies", {}).keys())
            result["dev_dependencies"] = list(data.get("devDependencies", {}).keys())

            # Detect framework
            all_deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

            if "next" in all_deps:
                result["framework"] = "Next.js"
                result["type"] = "next"
                result["build_command"] = "npm run build"
                result["output_dir"] = ".next"
            elif "react" in all_deps:
                result["framework"] = "React"
                result["type"] = "react"
                result["build_command"] = "npm run build"
                result["output_dir"] = self._find_build_dir()
            elif "vue" in all_deps:
                result["framework"] = "Vue"
                result["type"] = "vue"
                result["build_command"] = "npm run build"
                result["output_dir"] = "dist"
            elif "angular" in all_deps:
                result["framework"] = "Angular"
                result["type"] = "angular"
                result["build_command"] = "npm run build"
                result["output_dir"] = "dist"
            else:
                result["framework"] = "Node.js"
                result["type"] = "node"
                result["build_command"] = "npm start" if "start" in data.get("scripts", {}) else None

            # Check for build script
            scripts = data.get("scripts", {})
            if "build" in scripts:
                result["build_command"] = "npm run build"

            # Node version
            if "engines" in data and "node" in data["engines"]:
                result["node_version"] = data["engines"]["node"]

        except (json.JSONDecodeError, KeyError) as e:
            result["error"] = str(e)

        return result

    def _find_build_dir(self) -> str:
        """Find the build output directory."""
        if (self.project_path / "dist").exists():
            return "dist"
        elif (self.project_path / "build").exists():
            return "build"
        return "dist"  # default