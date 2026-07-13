# Changelog

All notable changes to Opun8 will be documented in this file.

## [0.1.3] - 2026-07-13

### Fixed
- Redeploy now works properly with existing Vercel projects
- Folder selection now uses native file browser instead of manual path entry
- Vercel API connection now retries with proper timeout (fixes Render free tier wake-up issues)
- Rename URL now correctly claims the new domain on Vercel

### Improved
- Better error handling for Vercel API calls
- Removed misleading "Check for build errors" hint on redeploy failures

## [0.1.2] - 2026-07-12

### Added
- Secure backend API for OAuth token exchange
- Vercel OAuth with PKCE support
- Native folder browser dialog

### Fixed
- GitHub OAuth now uses API backend instead of .env file
- Vercel OAuth now uses API backend instead of .env file

## [0.1.1] - 2026-07-12

### Fixed
- Added missing `requests` dependency

## [0.1.0] - 2026-07-12

### Added
- Initial public beta release
- Deploy to Vercel
- GitHub OAuth integration
- Project auto-detection (React, Next.js, Vue, Node.js, Python, Static HTML)
- Git operations (init, commit, push, create repo)
- Deployment history tracking
- Badge system (7 levels)
- Cross-platform support (Windows, Mac, Linux, Termux)