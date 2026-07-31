# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.6] — 2026-07-31

### Added
- **Netlify provider** — full deployment support, including OAuth 2.0 (PKCE) authentication with personal access token fallback, site creation with conflict resolution, concurrent file upload with SHA1 manifests, cost estimation, and environment variable management.
- **Interactive environment variable detection** — scans source code for variable usage (`process.env`, `os.getenv()`, etc.), suggests framework-specific variables for React, Next.js, Vite, Django, Flask, and FastAPI, parses `.env.example` files, and redacts sensitive values in output.
- **Cost estimator** — pre-deployment cost previews for Vercel, Netlify, and Render, including plan tiers, overage/recharge costs, side-by-side platform comparison, and optimization suggestions.
- **Website cloning** — clone static sites or fully JS-rendered React applications, with automatic framework detection (React, Vue, Angular, Next.js), single-page mode, code cleanup, SSRF protection, and retry with exponential backoff.
- **Deployment history** — local record of past deployments, stored in `~/.opun8/deployment_history.json`.
- **Platform-specific deploy commands** — `opun8 deploy vercel`, `opun8 deploy netlify`, and `opun8 deploy render` for direct, non-interactive deployment.
- **Render provider** — API key authentication, workspace selection, GitHub repo linking, and cost estimation.
- **Vercel provider enhancements** — team/scope switching, project renaming, environment variable management, and plan-based cost estimation.
- **GitHub integration** — OAuth authentication, repository creation, push handling for unrelated histories, private repo support, and deploy-from-repo option.
- **Achievement tracking** — optional progress indicators for CLI usage milestones.
- **No-emoji mode** — set `OPUN8_NO_EMOJI=1` to disable decorative output for CI or accessibility contexts.

### Fixed
- **Netlify authentication** — resolved a startup error caused by a missing import, implemented the personal-access-token login flow (previously a non-functional stub), separated local auth checks from network refresh calls, and added consistent error reporting across retry paths.
- **Netlify deployment** — file paths are now URL-encoded before upload to correctly handle spaces and special characters; site-name conflict resolution now tracks all attempted names; retry waits show a visible countdown instead of appearing to hang; deployment now respects `.gitignore` to prevent accidental secret uploads.
- **Netlify pricing** — corrected inaccurate pricing examples, fixed Enterprise plan display, and switched recharge calculations to integer arithmetic to eliminate floating-point rounding errors.
- **Render pricing** — added accurate compute tier pricing (Free through Pro Ultra), corrected Postgres and Redis instance costs, and ensured the free tier correctly reports $0.
- **CLI messaging** — deployment menus now correctly capture and return user selections; success feedback is now shown after Vercel/Netlify authentication; emoji output now consistently respects `OPUN8_NO_EMOJI`; Ctrl+C is now handled gracefully during prompts.
- **Deploy command logic** — consolidated menu handling, corrected parameter passing for GitHub repo URLs across providers, and removed several dead code paths and unused imports.
- **Folder navigation** — added native OS folder pickers (Windows, macOS, Linux), fixed formatting of file paths containing special characters, and resolved an issue where recent-directory timestamps were not updating.
- **Git integration** — fixed a prompt default that could leak into free-text input, corrected commit-status detection, improved error reporting for repository existence checks, and added support for unrelated-history merges on new repositories.
- **Project detection** — folder selection now correctly triggers re-detection without recursive calls or screen clearing artifacts.

### Removed
- Unused functions, dead code paths, and unused imports across the authentication, messaging, and deployment modules.

### Documentation
- Updated `README.md` with current features, commands, and setup instructions.
- Added this changelog.

---

## [0.1.5] — 2026-07-15

### Added
- Netlify provider (initial implementation)
- Cost estimator for Vercel, Netlify, and Render
- Interactive environment variable detection
- Deployment history tracking
- Website cloning (static and JS-rendered)
- GitHub integration with OAuth
- Vercel provider with team support
- Render provider with API key authentication
- 15+ CLI commands
- Backend OAuth helper API
- Initial PyPI release

### Fixed
- Vercel provider stability issues
- Render authentication flow

---

## [0.1.4] — 2026-07-01

### Added
- Initial release with Vercel and Render support
- Basic CLI structure
- GitHub OAuth
- Project type detection

---

## Roadmap

| Version | Focus | Status |
|---|---|---|
| 0.1.5 | Netlify provider, cost estimator, environment variable detection | Released |
| 0.1.6 | Bug fixes, Render pricing corrections, GitHub deploy, folder picker | Released |
| 0.1.7 | Railway provider | Planned |
| 0.1.8 | Full-stack orchestrator (`opun8 deploy --fullstack`) | Planned |
| 0.1.9 | Deployment rollback | Planned |
| 0.1.10 | Unified log streaming | Planned |
| 0.2.0 | MCP server integration, AI agent mode | Planned |

### Upcoming Detail

**Railway provider (0.1.7)** — OAuth and API key authentication, deployment, cost estimation, and conflict resolution for Railway.

**Full-stack orchestrator (0.1.8)** — `opun8 deploy --fullstack` deploys backend and frontend sequentially in one command, injecting the resolved backend URL into frontend environment variables, and presents a unified dashboard with both live links.

**Rollback (0.1.9)** — `opun8 rollback` reverts to a previous deployment, with `--list` to view deployment history and `--to <id>` to target a specific version, across all supported platforms.

**Unified logs (0.1.10)** — `opun8 logs --tail` streams logs live, with `--platform` and `--lines` filters and platform-based color coding.

**AI agent mode (0.2.0)** — MCP server for Claude Code integration, plus `--json`, `--non-interactive`, `--dry-run`, and `--agent-mode` flags, and a declarative `opun8.json` config format for agent-driven deployments.