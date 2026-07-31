# OPUN8

**Universal deployment platform for modern web applications.**

Deploy to Vercel, Netlify, or Render from a single CLI — no provider-specific tooling, no context switching.

[![PyPI version](https://img.shields.io/pypi/v/opun8.svg)](https://pypi.org/project/opun8/)
[![Python versions](https://img.shields.io/pypi/pyversions/opun8.svg)](https://pypi.org/project/opun8/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

OPUN8 is a command-line tool that unifies deployment across multiple hosting providers. It detects your project type, estimates cost before you commit, and ships your app with a single command — regardless of which provider you're targeting.

## Features

- **Multi-provider deployment** — Deploy to Vercel, Netlify, or Render from local files or a connected GitHub repository
- **Unified authentication** — OAuth for GitHub, Vercel, and Netlify; API key support for Render
- **Automatic project detection** — Identifies framework and build configuration without manual setup
- **Cost estimation** — Preview provider costs before deploying
- **Environment variable management** — Detects required variables and prompts interactively
- **Website cloning** — Clone static sites, React applications, or fully JS-rendered pages
- **Deployment history** — Local tracking of past deployments
- **Full-stack orchestration** *(coming soon)* — Deploy frontend and backend together in a single command

## Installation

```bash
# Standard installation
pip install opun8

# With clipboard support
pip install opun8[clipboard]

# Full installation (testing + clipboard)
pip install opun8[all]
```

## Quick Start

```bash
# View available commands
opun8

# Detect your project type
opun8 detect

# Deploy interactively
opun8 deploy

# Or target a specific provider
opun8 deploy vercel
opun8 deploy netlify
opun8 deploy render
```

## Command Reference

| Command | Description |
|---|---|
| `opun8` | Display welcome screen and available commands |
| `opun8 --version` | Show installed version |
| `opun8 doctor` | Check environment; auto-installs Node.js if required |
| `opun8 detect` | Detect project type and framework |
| `opun8 deploy` | Deploy the current project (interactive) |
| `opun8 deploy vercel` | Deploy directly to Vercel |
| `opun8 deploy netlify` | Deploy directly to Netlify |
| `opun8 deploy render` | Deploy directly to Render |
| `opun8 register` | Create an OPUN8 account |
| `opun8 login` | Authenticate with an existing account |
| `opun8 verify` | Verify email via one-time password |
| `opun8 resend-otp` | Resend the verification code |
| `opun8 status` | Check current account status |
| `opun8 logout` | Sign out of all connected services |
| `opun8 github` | Connect a GitHub account |
| `opun8 vercel` | Connect a Vercel account |
| `opun8 netlify` | Connect a Netlify account |
| `opun8 render` | Connect a Render account |
| `opun8 clone` | Clone an existing website |
| `opun8 upgrade` | Upgrade subscription plan |
| `opun8 history` | View past deployments |
| `opun8 badges` | View achievement progress |
| `opun8 help` | List all available commands |

## Configuration

### Environment Variables

| Variable | Description |
|---|---|
| `OPUN8_NO_EMOJI=1` | Disable emoji in CLI output |
| `OPUN8_DEBUG=1` | Enable verbose debug logging |
| `OPUN8_API_URL=<url>` | Override the default API endpoint (`https://opun8-api.onrender.com`) |

### Credential Storage

Authentication tokens are stored using the OS-native credential store:

| Platform | Storage Backend |
|---|---|
| Windows | Windows Credential Manager |
| macOS | Keychain |
| Linux | Secret Service (libsecret) |

A local cache is also maintained in `~/.opun8/` for faster access.

## Supported Platforms

| Provider | Status | Best For |
|---|---|---|
| Vercel | ✅ Supported | Frontend, Next.js, React |
| Netlify | ✅ Supported | Static sites, JAMstack |
| Render | ✅ Supported | Full-stack apps, Python, Node.js |
| Railway | ⬜ Planned | — |

## Project Structure

```
opun8/
├── src/opun8/
│   ├── cli.py              # CLI entry point
│   ├── commands/           # Command implementations
│   ├── core/                # Core application logic
│   ├── providers/           # Vercel, Netlify, Render integrations
│   ├── services/            # Business logic layer
│   └── ui/                  # Terminal UI components
├── tests/                   # Unit tests
├── pyproject.toml           # Project configuration
└── README.md
```

## Development

### Setup

```bash
git clone https://github.com/KakesDavid/opun8.git
cd opun8

python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate

pip install -e ".[all]"
```

### Testing

```bash
pytest
```

### Building & Publishing

```bash
python -m build
twine upload dist/*
```

## Contributing

Contributions are welcome. To submit a change:

1. Fork the repository
2. Create a feature branch
3. Make your changes and add tests where applicable
4. Open a pull request with a clear description of the change

## License

Released under the [MIT License](LICENSE).

---

Maintained by the Kakes David Team. If OPUN8 is useful to you, consider starring the repository.