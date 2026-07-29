# Changelog

All notable changes to Opun8 will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.5] - 2026-07-29

### Added
- **Netlify Provider** — Full Netlify integration with OAuth 2.0 authentication
  - Site creation and management
  - File upload and deployment via Netlify API
  - Environment variable management
  - Credit-based cost estimation
  - Interactive site name conflict resolution
  - Personal Access Token support for automation
- **Interactive Environment Variables** — Complete rewrite of env var handling
  - Scans source code for env var usage (`process.env`, `os.getenv`, etc.)
  - Framework-specific detection (React, Next.js, Vite, Django, Flask, FastAPI)
  - Checkbox-style interactive selection with source file context
  - Sensitive value redaction (API keys, tokens, passwords)
  - Framework-aware variable suggestions
- **Netlify Cost Estimator** — Credit-based pricing breakdown
  - Bandwidth, compute, web requests, and deploy credits
  - Recharge block calculations for overages
  - Visual credit usage percentage
- **Interactive Service Name Conflict Resolution** — Applied to Netlify and Render
  - Detects name conflicts
  - Lists existing sites/services
  - Offers: use existing, enter new name, or cancel
- **Environment Service Module** — Complete rewrite (`services/env_service.py`)
  - Source code scanning for env var patterns across multiple languages
  - .env.example and .env.sample parsing
  - Framework-specific detection
  - Interactive checkbox UI with source context
- **UI Messages** — Netlify-specific messages and displays
  - Authentication success/failure messages
  - Deployment status messages
  - Site listing tables
  - PAT instructions

### Changed
- **Vercel Provider** — Updated to use new interactive env var prompting
- **Render Provider** — Updated to use new interactive env var prompting
- **Netlify Deploy** — Fixed SHA1 vs file path mapping for `required` files
- **Netlify Deploy** — Moved interactive prompts OUTSIDE progress bars to fix garbled output
- **Cost Display UI** — Added Netlify credit-based cost tables
- **pyproject.toml** — Version bumped to 0.1.5, added optional dependencies

### Fixed
- Netlify OAuth `Retry-After` header parsing (date format fix)
- Netlify site name conflict resolution no longer garbles progress bar output
- Netlify `required` files now correctly matched by SHA1 hash
- Render service name conflict resolution argument ordering
- Render `list_render_services` now properly unwraps `item["service"]`
- Render `list_render_services` pagination support
- Render env var deployment (was silently failing)
- `open_folder_dialog` now handles headless environments gracefully
- Various UI crash fixes (None values in slicing, missing emoji keys)

---

## [0.1.4] - 2026-07-20

### Added
- **Cost Estimator** — Show deployment costs before deploying
  - Vercel cost estimation (Hobby, Pro, Enterprise)
  - Render cost estimation (Individual, Team, Organization)
  - Savings tips and optimization suggestions
- **Deployment History** — Track all deployments locally
  - Stored in `~/.opun8/deployment_history.json`
  - Badge progression tracking
- **Native Folder Browser** — File explorer dialog for selecting project folders
  - Tkinter, PyQt5, and easygui fallbacks
  - Manual path entry as last resort
- **Render Service Listing** — View all your Render services with `opun8 render --show`
- **Environment Variable Detection** — Auto-detects .env files and prompts for selection
- **Deployment Badges** — 7 achievement levels with visual notifications
  - 🌱 First Clone (1)
  - 🔍 Curious Explorer (3)
  - 🧩 Pattern Finder (5)
  - 📚 Archivist (10)
  - 🚀 Speed Runner (25)
  - 🏆 Master Archiver (50)
  - 👑 Clone King (100)

### Changed
- **Renamed deployment URL** — Now correctly shows the live URL after deployment
- **Improved URL resolution** — Better detection of deployment URLs across providers
- **Better error handling** — Graceful handling of Ctrl+Z and EOF errors
- **Rich UI improvements** — Better terminal output with tables, panels, and progress bars

### Fixed
- Redeploy now works properly with existing Vercel projects
- Vercel OAuth connection retries with proper timeout (fixes Render free tier wake-up issues)
- Rich markup errors in console output
- Badge notifications now show after every successful deployment
- Folder selection now uses native file browser instead of manual path entry

---

## [0.1.3] - 2026-07-15

### Added
- **Render Provider** — Deploy to Render directly from GitHub repositories
- **Render Authentication** — OAuth and API key support for Render
- **Environment Variable Detection** — Auto-detects .env files and prompts for selection
- **Native Folder Browser** — File explorer dialog for selecting project folders (no more manual path typing)
- **Deployment Badges** — 7 achievement levels with visual notifications
- **Render Service Listing** — View all your Render services with `opun8 render --show`

### Changed
- **Renamed deployment URL** — Now correctly shows the live URL after deployment
- **Improved URL resolution** — Better detection of deployment URLs across providers
- **Better error handling** — Graceful handling of Ctrl+Z and EOF errors

### Fixed
- Redeploy now works properly with existing Vercel projects
- Vercel OAuth connection retries with proper timeout (fixes Render free tier wake-up issues)
- Rich markup errors in console output
- Badge notifications now show after every successful deployment
- Folder selection now uses native file browser instead of manual path entry

---

## [0.1.2] - 2026-07-10

### Added
- **Vercel Provider** — Full Vercel integration with OAuth 2.0 + PKCE
- **GitHub Integration** — Repository listing, cloning, and push support
- **Website Cloning** — Clone static, React, and SPA websites
  - Static HTML cloner
  - React cloner
  - Perfect cloner (Playwright-based)
- **Project Detection** — Auto-detects frameworks (React, Next.js, Vue, Node.js, Python, Static)
- **Build Service** — Auto-build projects before deployment
- **Cost Estimator** — Basic cost estimation for Vercel
- **Deployment History** — Track deployments in local JSON file

### Changed
- Initial public release

---

## [0.1.0] - 2026-07-01

### Added
- Initial project setup
- CLI framework (Typer + Rich)
- Basic authentication (register, login, verify)
- Deployment to Vercel
- GitHub OAuth integration
- Website cloning foundations