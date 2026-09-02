"""
Web-based environment variable editor for Opun8.

Opens a local web server and serves a beautiful HTML card UI for editing
environment variables. This replaces the terminal-based env var prompts
with a clean, user-friendly web interface.

Features:
    - Local web server on port 4243
    - Beautiful HTML card UI with clean design
    - Add/delete environment variables
    - Toggle selection with checkboxes
    - Sensitive values hidden (password input)
    - Save & Deploy → returns vars to CLI
    - Cancel → returns empty dict
    - Secure: no CORS headers, Origin validation
    - Secure: variable name validation
    - Secure: rejects unknown variable operations

Architecture:
    1. Server starts in a background thread
    2. Browser opens automatically
    3. User edits vars in the browser
    4. AJAX calls to local API endpoints:
        - GET  /api/vars      → Get current vars
        - POST /api/save      → Save vars and signal completion
        - POST /api/cancel    → Cancel and close
        - POST /api/toggle    → Toggle a variable's selection
        - POST /api/update    → Update a variable's value
        - POST /api/add       → Add a new variable
        - POST /api/delete    → Delete a variable
    5. Server blocks until save/cancel
    6. Returns result to caller

Security Notes:
    - No CORS headers (prevents cross-origin secret theft)
    - Origin validation (only localhost:4243 can access)
    - Variable names validated against safe pattern
    - Unknown variable operations rejected

Usage:
    from opun8.services.env_web_editor import open_env_editor

    detected_vars = {
        "API_URL": {"default": "", "sensitive": False, "description": "Backend API URL"},
        "SECRET_KEY": {"default": "", "sensitive": True, "description": "Secret key"},
    }

    result = open_env_editor(detected_vars)
    # result = {"API_URL": "https://api.example.com", "SECRET_KEY": "abc123"}

Author: OPUN8 Team
Version: 0.1.8
"""

import json
import re
import threading
import webbrowser
import time
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from pathlib import Path
from typing import Dict, Any, Optional, List

from rich.console import Console

console = Console()

# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 4243
SERVER_TIMEOUT = 300  # 5 minutes timeout

# HTML template path
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "env_editor.html"

# ✅ FIX: Safe identifier pattern — matches valid shell/.env variable names
# Variables must start with a letter or underscore, followed by letters,
# numbers, or underscores.
_VALID_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# ✅ FIX: Only these Origins are allowed to talk to the local server.
# Browser navigation to the page itself doesn't send an Origin header, so
# `None` (no header) is also accepted.
_TRUSTED_ORIGINS = {
    f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",
    f"http://127.0.0.1:{DEFAULT_PORT}",
}

# Sensitive patterns for detecting secrets
_SENSITIVE_PATTERNS = [
    "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL",
    "SIGNATURE", "CERT", "CERTIFICATE", "ENCRYPT",
    "JWT", "SSH", "SSL", "TLS", "PRIV",
    "DATABASE_URL", "POSTGRES", "MYSQL", "MONGODB", "REDIS_URL",
]


def _is_sensitive_env_key(key: str) -> bool:
    """Check if an environment variable key appears to be sensitive."""
    key_upper = key.upper()
    for pattern in _SENSITIVE_PATTERNS:
        if pattern in key_upper:
            return True
    return False


# =============================================================================
# HTML CONTENT
# =============================================================================

def _get_html_content() -> str:
    """Read the HTML template file, or fall back to embedded HTML."""
    try:
        if TEMPLATE_PATH.exists():
            return TEMPLATE_PATH.read_text(encoding="utf-8")
        return _get_fallback_html()
    except Exception:
        return _get_fallback_html()


def _get_fallback_html() -> str:
    """Fallback HTML in case the template file is missing."""
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Environment Variables — Opun8</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0e17;
            color: #e0e0e0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }
        .card {
            background: #141b2d;
            border: 1px solid #00d4ff;
            border-radius: 16px;
            padding: 32px;
            max-width: 720px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0, 212, 255, 0.1);
        }
        .card-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 4px;
        }
        .card-header h1 {
            color: #00d4ff;
            font-size: 24px;
            margin: 0;
        }
        .subtitle {
            color: #666;
            margin-top: 0;
            margin-bottom: 24px;
            font-size: 14px;
        }
        .var-row {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 0;
            border-bottom: 1px solid #1a2340;
        }
        .var-row input[type="checkbox"] {
            width: 18px;
            height: 18px;
            accent-color: #00d4ff;
            cursor: pointer;
            flex-shrink: 0;
        }
        .var-row .var-name {
            flex: 0 0 140px;
            font-weight: 600;
            color: #00d4ff;
            font-size: 13px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .var-row .var-input {
            flex: 1;
            padding: 8px 12px;
            background: #0a0e17;
            border: 1px solid #1a2340;
            border-radius: 6px;
            color: #e0e0e0;
            font-size: 13px;
            transition: border-color 0.2s;
            min-width: 0;
        }
        .var-row .var-input:focus {
            border-color: #00d4ff;
            outline: none;
        }
        .var-row .var-input::placeholder {
            color: #444;
        }
        .var-row .delete-btn {
            background: none;
            border: none;
            color: #ff4444;
            cursor: pointer;
            padding: 4px 6px;
            border-radius: 4px;
            display: flex;
            align-items: center;
            transition: background 0.2s;
            flex-shrink: 0;
        }
        .var-row .delete-btn:hover {
            background: rgba(255, 68, 68, 0.15);
            color: #ff6666;
        }
        .actions {
            display: flex;
            gap: 12px;
            margin-top: 24px;
            flex-wrap: wrap;
        }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 13px;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: background 0.2s, transform 0.1s;
        }
        .btn:active { transform: scale(0.97); }
        .btn-primary {
            background: #00d4ff;
            color: #0a0e17;
        }
        .btn-primary:hover { background: #00e5ff; }
        .btn-secondary {
            background: #1a2340;
            color: #e0e0e0;
        }
        .btn-secondary:hover { background: #2a3350; }
        .btn-danger {
            background: #cc3333;
            color: #fff;
        }
        .btn-danger:hover { background: #ff4444; }
        .btn-success {
            background: #00cc88;
            color: #0a0e17;
        }
        .btn-success:hover { background: #00dd99; }
        .add-row {
            display: flex;
            gap: 12px;
            margin-top: 16px;
            padding: 12px 0;
            border-top: 1px dashed #1a2340;
        }
        .add-row input {
            flex: 1;
            padding: 8px 12px;
            background: #0a0e17;
            border: 1px solid #1a2340;
            border-radius: 6px;
            color: #e0e0e0;
            font-size: 13px;
            transition: border-color 0.2s;
        }
        .add-row input:focus {
            border-color: #00d4ff;
            outline: none;
        }
        .add-row .btn { padding: 8px 16px; }
        .stats {
            color: #555;
            font-size: 13px;
            margin-top: 16px;
        }
        .message {
            margin-top: 10px;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 13px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .message-error {
            background: rgba(255, 68, 68, 0.1);
            color: #ff6666;
            border: 1px solid rgba(255, 68, 68, 0.2);
        }
        .message-success {
            background: rgba(0, 212, 255, 0.1);
            color: #00d4ff;
            border: 1px solid rgba(0, 212, 255, 0.2);
        }
        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: #555;
            font-size: 14px;
        }
        .hidden { display: none !important; }
        .icon { display: inline-flex; flex-shrink: 0; }
        .icon svg { display: block; }

        /* Mobile responsive */
        @media (max-width: 600px) {
            .card { padding: 16px; }
            .var-row { flex-wrap: wrap; gap: 6px; }
            .var-row .var-name { flex: 0 0 100%; font-size: 12px; }
            .var-row .var-input { flex: 1 1 100%; }
            .var-row input[type="checkbox"] { margin-right: 4px; }
            .actions .btn { flex: 1 1 100%; justify-content: center; }
            .add-row { flex-wrap: wrap; }
            .add-row input { flex: 1 1 100%; }
        }
    </style>
</head>
<body>
    <div class="card" id="app">
        <div class="card-header">
            <span class="icon" id="icon-lock"></span>
            <h1>Environment Variables</h1>
        </div>
        <p class="subtitle">Configure the variables for your deployment.</p>
        <div id="vars-container"></div>
        <div id="add-row" class="add-row hidden">
            <input type="text" id="new-var-name" placeholder="Variable name" autocomplete="off">
            <input type="password" id="new-var-value" placeholder="Value" autocomplete="off">
            <button class="btn btn-success" onclick="addVariable()">Add</button>
            <button class="btn btn-secondary" onclick="cancelAdd()">Cancel</button>
        </div>
        <div class="actions">
            <button class="btn btn-secondary" onclick="showAddRow()">
                <span class="icon" id="icon-add-btn"></span> Add Variable
            </button>
            <button class="btn btn-primary" onclick="saveAndDeploy()">
                <span class="icon" id="icon-save-btn"></span> Save &amp; Deploy
            </button>
            <button class="btn btn-danger" onclick="cancel()">
                <span class="icon" id="icon-cancel-btn"></span> Cancel
            </button>
        </div>
        <div class="stats" id="stats">Loading variables...</div>
        <div id="message" class="message hidden"></div>
    </div>

    <script>
        // SVG Icons
        const ICONS = {
            lock: '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="9" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
            plus: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
            save: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8M7 3v5h8"/></svg>',
            close: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
            trash: '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0-1 14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1L5 6"/></svg>',
            alert: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a1 1 0 0 0 .9 1.5h18.6a1 1 0 0 0 .9-1.5L13.7 3.9a1 1 0 0 0-1.7 0Z"/></svg>',
            check: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.1V12a10 10 0 1 1-5.9-9.1"/><path d="m9 11 3 3L22 4"/></svg>',
        };

        function icon(name) { return ICONS[name] || ''; }

        // Set icons
        document.getElementById('icon-lock').innerHTML = icon('lock');
        document.getElementById('icon-add-btn').innerHTML = icon('plus');
        document.getElementById('icon-save-btn').innerHTML = icon('save');
        document.getElementById('icon-cancel-btn').innerHTML = icon('close');

        let vars = [];

        function loadVars() {
            fetch('/api/vars')
                .then(r => r.json())
                .then(data => {
                    vars = data;
                    renderVars();
                })
                .catch(() => {
                    document.getElementById('vars-container').innerHTML =
                        '<div class="empty-state">' + icon('alert') + ' Could not load variables</div>';
                    document.getElementById('stats').textContent = 'Error loading variables';
                });
        }

        function renderVars() {
            const container = document.getElementById('vars-container');
            const selected = vars.filter(v => v.selected).length;
            document.getElementById('stats').textContent =
                'Selected: ' + selected + ' of ' + vars.length + ' variables';

            if (vars.length === 0) {
                container.innerHTML = '<div class="empty-state">No variables detected.<br><span style="font-size:12px;color:#444;">Add one using the button below.</span></div>';
                return;
            }

            let html = '';
            vars.forEach((v, i) => {
                const inputType = v.sensitive ? 'password' : 'text';
                const displayValue = v.sensitive && v.value ? '' : v.value;
                html += `
                    <div class="var-row">
                        <input type="checkbox" ${v.selected ? 'checked' : ''} onchange="toggleSelection(${i})">
                        <span class="var-name" title="${escapeHtml(v.name)}">${escapeHtml(v.name)}</span>
                        <input class="var-input" type="${inputType}" value="${escapeHtml(displayValue)}" onchange="updateValue(${i}, this.value)" placeholder="Enter ${escapeHtml(v.name)}">
                        <button class="delete-btn" onclick="deleteVariable(${i})" title="Delete ${escapeHtml(v.name)}">${icon('close')}</button>
                    </div>
                `;
            });
            container.innerHTML = html;
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function toggleSelection(index) {
            const v = vars[index];
            if (!v) return;
            v.selected = !v.selected;
            fetch('/api/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: v.name })
            }).then(() => renderVars());
        }

        function updateValue(index, value) {
            const v = vars[index];
            if (!v) return;
            v.value = value;
            fetch('/api/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: v.name, value: value })
            });
        }

        function deleteVariable(index) {
            const v = vars[index];
            if (!v) return;
            if (confirm('Delete "' + v.name + '"?')) {
                fetch('/api/delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: v.name })
                }).then(() => loadVars());
            }
        }

        function showAddRow() {
            const row = document.getElementById('add-row');
            row.classList.remove('hidden');
            document.getElementById('new-var-name').focus();
        }

        function cancelAdd() {
            document.getElementById('add-row').classList.add('hidden');
            document.getElementById('new-var-name').value = '';
            document.getElementById('new-var-value').value = '';
            hideMessage();
        }

        function addVariable() {
            const nameInput = document.getElementById('new-var-name');
            const valueInput = document.getElementById('new-var-value');
            const name = nameInput.value.trim();
            const value = valueInput.value;

            if (!name) {
                showMessage('Please enter a variable name.', 'error');
                nameInput.focus();
                return;
            }

            fetch('/api/add', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, value: value })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    cancelAdd();
                    loadVars();
                    showMessage('Added: ' + name, 'success');
                } else {
                    showMessage(data.error || data.message || 'Could not add variable.', 'error');
                }
            });
        }

        function saveAndDeploy() {
            showMessage('Saving...', 'info');
            fetch('/api/save', { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showDoneState('Variables saved — deployment will continue in your terminal.', 'success');
                    } else {
                        showMessage(data.error || 'Save failed.', 'error');
                    }
                })
                .catch(() => {
                    showMessage('Network error. Please try again.', 'error');
                });
        }

        function cancel() {
            if (confirm('Cancel deployment?')) {
                fetch('/api/cancel', { method: 'POST' })
                    .then(() => showDoneState('Cancelled.', 'error'));
            }
        }

        function showDoneState(message, type) {
            document.querySelector('.actions').classList.add('hidden');
            document.getElementById('add-row').classList.add('hidden');
            document.getElementById('vars-container').innerHTML =
                '<div class="message message-' + type + '">' + icon('check') + ' ' + escapeHtml(message) + '</div>' +
                '<p class="subtitle" style="margin-top:12px;">You can close this tab now.</p>';
            document.getElementById('stats').textContent = '';
            hideMessage();
            // Best-effort close (works only if tab was opened by script)
            window.close();
        }

        function showMessage(msg, type) {
            const el = document.getElementById('message');
            el.className = 'message message-' + type;
            el.innerHTML = (type === 'error' ? icon('alert') : icon('check')) + ' ' + escapeHtml(msg);
            el.classList.remove('hidden');
        }

        function hideMessage() {
            document.getElementById('message').classList.add('hidden');
        }

        // Load on page ready
        loadVars();

        // Auto-focus first input after render
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(function() {
                const firstInput = document.querySelector('.var-row .var-input');
                if (firstInput) firstInput.focus();
            }, 500);
        });
    </script>
</body>
</html>
"""


# =============================================================================
# STATE MANAGEMENT
# =============================================================================

class EnvEditorState:
    """
    Manages the state of the environment variable editor.

    This is shared between the main thread and the HTTP server thread.
    All operations are validated to prevent security issues.
    """

    def __init__(self, detected_vars: Dict[str, Dict]):
        self.detected_vars = detected_vars
        self.selected_vars: List[str] = list(detected_vars.keys())
        self.result: Optional[Dict[str, str]] = None
        self.is_done = False
        self.is_cancelled = False

        # Populate initial values from detected vars
        self.values: Dict[str, str] = {}
        for var_name, meta in detected_vars.items():
            default = meta.get("default")
            self.values[var_name] = str(default) if default is not None else ""

    def get_all_vars(self) -> List[Dict[str, Any]]:
        """Get all variables with their current state for the UI."""
        result = []
        for var_name in sorted(self.detected_vars.keys()):
            meta = self.detected_vars.get(var_name, {})
            result.append({
                "name": var_name,
                "value": self.values.get(var_name, ""),
                "selected": var_name in self.selected_vars,
                "sensitive": meta.get("sensitive", False),
                "description": meta.get("description", ""),
                "default": meta.get("default", ""),
            })
        return result

    def toggle_selection(self, var_name: str) -> bool:
        """
        Toggle selection status of a variable.

        ✅ FIX: Rejects names that were never actually detected/added.
        """
        if var_name not in self.detected_vars:
            return False
        if var_name in self.selected_vars:
            self.selected_vars.remove(var_name)
        else:
            self.selected_vars.append(var_name)
        return True

    def update_value(self, var_name: str, value: str) -> bool:
        """
        Update the value of a variable.

        ✅ FIX: Rejects names that were never actually detected/added.
        """
        if var_name not in self.detected_vars:
            return False
        self.values[var_name] = str(value)
        return True

    def add_variable(self, var_name: str, value: str = "") -> bool:
        """
        Add a new variable to the editor.

        ✅ FIX: Names are validated against _VALID_ENV_NAME pattern.
        ✅ FIX: Rejects empty names or names that already exist.
        """
        if not var_name or not _VALID_ENV_NAME.match(var_name):
            return False
        if var_name in self.detected_vars:
            return False

        self.detected_vars[var_name] = {
            "default": value,
            "sensitive": True,
            "description": "Custom variable",
        }
        self.values[var_name] = value
        self.selected_vars.append(var_name)
        return True

    def delete_variable(self, var_name: str) -> bool:
        """Delete a variable from the editor."""
        if var_name in self.detected_vars:
            del self.detected_vars[var_name]
            self.values.pop(var_name, None)
            self.selected_vars = [v for v in self.selected_vars if v != var_name]
            return True
        return False

    def save_and_close(self) -> Dict[str, str]:
        """Save current state and mark as done."""
        result = {}
        for var_name in self.selected_vars:
            if var_name in self.values:
                result[var_name] = self.values[var_name]
        self.result = result
        self.is_done = True
        return result

    def cancel_and_close(self) -> None:
        """Cancel and mark as done."""
        self.is_cancelled = True
        self.is_done = True


# =============================================================================
# HTTP REQUEST HANDLER
# =============================================================================

class EnvEditorHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for the environment variable editor.

    Serves the HTML page and handles API endpoints:
        - GET  /            → Serve the HTML page
        - GET  /api/vars    → Get current variables
        - POST /api/save    → Save and signal completion
        - POST /api/cancel  → Cancel and close
        - POST /api/toggle  → Toggle selection
        - POST /api/update  → Update variable value
        - POST /api/add     → Add new variable
        - POST /api/delete  → Delete variable

    Security:
        - No CORS headers (prevents cross-origin secret theft)
        - Origin validation (only localhost:4243 can access)
        - Variable name validation
        - Unknown variable operations rejected
    """

    state: Optional[EnvEditorState] = None

    def log_message(self, format, *args):
        """Suppress default logging to keep console clean."""
        pass

    def _origin_is_trusted(self) -> bool:
        """
        ✅ FIX: Validate Origin header.
        Browser navigation omits Origin, so None is accepted.
        Any other Origin must match the server's address.
        """
        origin = self.headers.get("Origin")
        return origin is None or origin in _TRUSTED_ORIGINS

    def do_GET(self):
        """Handle GET requests."""
        if not self._origin_is_trusted():
            self.send_response(403)
            self.end_headers()
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "":
            self._serve_html()
        elif path == "/api/vars":
            self._serve_vars()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle POST requests."""
        if not self._origin_is_trusted():
            self.send_response(403)
            self.end_headers()
            return

        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/save":
            self._handle_save()
        elif path == "/api/cancel":
            self._handle_cancel()
        elif path == "/api/toggle":
            self._handle_toggle()
        elif path == "/api/update":
            self._handle_update()
        elif path == "/api/add":
            self._handle_add()
        elif path == "/api/delete":
            self._handle_delete()
        else:
            self.send_response(404)
            self.end_headers()

    def _serve_html(self):
        """Serve the HTML page."""
        html = _get_html_content()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _serve_vars(self):
        """Serve the current variables as JSON."""
        if not self.state:
            self.send_response(500)
            self.end_headers()
            return
        self._send_json(self.state.get_all_vars())

    def _handle_save(self):
        """Handle save request."""
        if not self.state:
            self._send_json({"success": False, "error": "No state"})
            return
        result = self.state.save_and_close()
        self._send_json({"success": True, "result": result})

    def _handle_cancel(self):
        """Handle cancel request."""
        if self.state:
            self.state.cancel_and_close()
        self._send_json({"success": True})

    def _handle_toggle(self):
        """Handle toggle selection request."""
        if not self.state:
            self._send_json({"success": False})
            return

        data = self._get_json_body()
        if data and isinstance(data.get("name"), str):
            ok = self.state.toggle_selection(data["name"])
            self._send_json({"success": ok, "error": None if ok else "Unknown variable"})
        else:
            self._send_json({"success": False, "error": "Missing or invalid name"})

    def _handle_update(self):
        """Handle update value request."""
        if not self.state:
            self._send_json({"success": False})
            return

        data = self._get_json_body()
        if data and isinstance(data.get("name"), str):
            ok = self.state.update_value(data["name"], data.get("value", ""))
            self._send_json({"success": ok, "error": None if ok else "Unknown variable"})
        else:
            self._send_json({"success": False, "error": "Missing or invalid name"})

    def _handle_add(self):
        """Handle add variable request."""
        if not self.state:
            self._send_json({"success": False})
            return

        data = self._get_json_body()

        # ✅ FIX: Validate name is a string before calling .strip()
        if not data or not isinstance(data.get("name"), str):
            self._send_json({"success": False, "error": "Missing or invalid name"})
            return

        name = data["name"].strip()
        value = data.get("value", "")
        if not isinstance(value, str):
            value = str(value)

        if not name:
            self._send_json({"success": False, "error": "Name cannot be empty"})
            return

        # ✅ FIX: Clear error message for invalid names
        if not _VALID_ENV_NAME.match(name):
            self._send_json({
                "success": False,
                "error": "Use only letters, numbers, and underscores; don't start with a number.",
            })
            return

        if self.state.add_variable(name, value):
            self._send_json({"success": True})
        else:
            self._send_json({"success": False, "error": f"Variable '{name}' already exists"})

    def _handle_delete(self):
        """Handle delete variable request."""
        if not self.state:
            self._send_json({"success": False})
            return

        data = self._get_json_body()
        if data and isinstance(data.get("name"), str):
            success = self.state.delete_variable(data["name"])
            self._send_json({"success": success})
        else:
            self._send_json({"success": False, "error": "Missing or invalid name"})

    def _send_json(self, data: Dict) -> None:
        """
        Send JSON response.

        ✅ FIX: No CORS headers. This UI only calls itself (same-origin).
        """
        response = json.dumps(data)
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(response.encode("utf-8"))

    def _get_json_body(self) -> Optional[Dict]:
        """Parse JSON from request body."""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                return None
            body = self.rfile.read(content_length).decode("utf-8")
            parsed = json.loads(body)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def open_env_editor(
    detected_vars: Dict[str, Dict[str, Any]],
    timeout: int = SERVER_TIMEOUT,
) -> Dict[str, str]:
    """
    Open the web-based environment variable editor.

    Args:
        detected_vars: Dictionary of detected variables with metadata.
            Format: {
                "VAR_NAME": {
                    "default": "default_value",
                    "sensitive": True/False,
                    "description": "Description of the variable"
                }
            }
        timeout: Maximum time to wait for user interaction (seconds)

    Returns:
        Dictionary of selected environment variables and their values.
        Returns empty dict if cancelled or timed out.

    Example:
        >>> detected_vars = {
        ...     "API_URL": {"default": "", "sensitive": False, "description": "Backend URL"},
        ...     "SECRET_KEY": {"default": "", "sensitive": True, "description": "Secret key"},
        ... }
        >>> result = open_env_editor(detected_vars)
        >>> print(result)
        {"API_URL": "https://api.example.com", "SECRET_KEY": "abc123"}
    """
    console.print()
    console.print("[dim]🌐 Opening environment editor in your browser...[/dim]")

    if not detected_vars:
        console.print("[yellow]⚠️ No environment variables detected.[/yellow]")
        return {}

    # Create state
    state = EnvEditorState(detected_vars)

    # Set the state on the handler class
    EnvEditorHandler.state = state

    # Start server
    server = None
    try:
        server = HTTPServer((DEFAULT_HOST, DEFAULT_PORT), EnvEditorHandler)
    except OSError:
        console.print(f"[red]❌ Port {DEFAULT_PORT} is already in use.[/red]")
        console.print("[dim]Please close any other application using this port and try again.[/dim]")
        return {}

    # Start server in background thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Open browser
    url = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}"
    opened = webbrowser.open(url)
    if not opened:
        console.print("[yellow]⚠️ Could not open browser automatically.[/yellow]")
        console.print(f"[dim]Please open this URL manually: {url}[/dim]")
    else:
        console.print(f"[green]✅ Browser opened: {url}[/green]")

    console.print(f"[dim]⏳ Waiting for you to save or cancel (timeout: {timeout}s)...[/dim]")
    console.print("[dim]Press Ctrl+C to cancel[/dim]")
    console.print()

    # Wait for user interaction
    start_time = time.time()
    try:
        while not state.is_done:
            if time.time() - start_time > timeout:
                console.print("[yellow]⚠️ Editor timed out. Skipping environment variables.[/yellow]")
                state.cancel_and_close()
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Cancelled by user.[/yellow]")
        state.cancel_and_close()

    # Shutdown server
    server.shutdown()
    server.server_close()
    server_thread.join(timeout=1)

    # Return result
    if state.is_cancelled or state.result is None:
        console.print("[dim]⏭️ Skipping environment variables.[/dim]")
        return {}

    result = state.result
    count = len(result)
    console.print(f"[green]✅ Selected {count} environment variable(s).[/green]")

    sensitive_count = sum(1 for k in result.keys() if _is_sensitive_env_key(k))
    if sensitive_count:
        console.print(f"[dim]🔒 {sensitive_count} sensitive value(s) hidden from display[/dim]")

    return result


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "open_env_editor",
]