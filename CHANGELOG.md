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