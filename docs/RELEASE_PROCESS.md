# Release Process — SanGir Automations

This document describes how to build, test, and release the desktop application.

## Prerequisites

1. **Git** — for version control and tagging
2. **Python 3.13** — for backend development
3. **Node.js 20+** — for Electron and build tooling
4. **GitHub CLI** (`gh`) — for managing releases
5. **Two GitHub repositories:**
   - `FCMR` (source code, private or public)
   - `sangir-releases` (installers, public)

## Setup (One-Time)

### 1. Create the public releases repository

```bash
# On GitHub, create a new public repository
# Owner: ihbsandeepreddy
# Name: sangir-releases
# Description: SanGir Automations desktop app releases and updates
# Visibility: Public (auto-updater needs to read releases)
```

### 2. Generate a GitHub Personal Access Token (PAT)

```bash
# 1. Go to https://github.com/settings/tokens
# 2. Create a new Classic token with scopes:
#    - repo (full control of private repositories)
#    - public_repo (access to public repositories)
# 3. Copy the token
# 4. Add it to your FCMR repo as a GitHub Actions secret:
#    Settings > Secrets and variables > Actions > New repository secret
#    Name: RELEASE_TOKEN
#    Value: <your PAT>
```

## Release Workflow

### Step 1: Prepare for release

```bash
cd /path/to/FCMR

# Pull latest
git checkout main
git pull origin main

# Update version in pyproject.toml (MAJOR.MINOR.PATCH)
# Example: from 0.1.0 to 0.2.0
# Also ensure package.json version matches

# Commit version bump
git add pyproject.toml package.json
git commit -m "chore: bump version to 0.2.0"
git push origin main
```

### Step 2: Create and push a release tag

```bash
# Tag follows semantic versioning: v<MAJOR>.<MINOR>.<PATCH>
git tag -a v0.2.0 -m "Release v0.2.0: Add backup feature"
git push origin v0.2.0
```

This triggers the GitHub Actions workflow in `.github/workflows/release.yml`.

### Step 3: Monitor the build

```bash
# Watch the Actions tab on GitHub
# https://github.com/ihbsandeepreddy/FCMR/actions

# The workflow will:
# 1. Build the Python backend (PyInstaller)
# 2. Build the Electron desktop app
# 3. Create the Windows installer (NSIS)
# 4. Upload to the sangir-releases repo
```

### Step 4: Verify the release

```bash
# Check sangir-releases releases
# https://github.com/ihbsandeepreddy/sangir-releases/releases

# Installed app will auto-detect the update and notify the user
```

## Testing Before Release

### Local build (without tagging)

```bash
# Install dependencies
pip install -e ".[dev]"
npm install

# Build backend only
npm run build:backend

# Run the dev app
npm start

# Or run backend + web separately
# Terminal 1:
python desktop_backend.py --port 8765

# Terminal 2:
python -m uvicorn app.main:app --port 8000
```

### Manual Electron build (sandbox test)

```bash
npm run dist

# Outputs: dist/SAND-Setup-0.2.0.exe
# Run the installer and test the app
```

## Auto-Update Behavior

Once installed:

1. **On startup:** App checks `sangir-releases` for a newer version
2. **If update found:** User is notified
3. **On restart:** Update installs automatically
4. **Logs:** `data/logs/update.log` records all checks and installs

## Rollback

If a release has issues:

1. **Delete the bad release** from `sangir-releases`
2. **Tag a new version** with a fix (e.g., `v0.2.1`)
3. Users will be offered the new version on their next check

## Code Signing (Future)

Currently, the Windows installer is **unsigned**. Browsers/antivirus may flag it.

To add code signing later:

1. Purchase a code signing certificate
2. Set `GH_CERT_FILE` and `GH_CERT_PASSWORD` secrets in GitHub Actions
3. electron-builder will automatically sign the `.exe` during release

## Troubleshooting

### Build fails in GitHub Actions

- Check the Actions log
- Ensure `RELEASE_TOKEN` is set and valid
- Verify `sangir-releases` repo exists and is public

### App won't update

- Check `data/logs/update.log` for errors
- Ensure `sangir-releases` has the release with a `latest.yml` file
- Test with `npm run dist` locally first

### PyInstaller fails

- Run `npm run build:backend` locally to debug
- Check for missing hidden imports in `build/sangir-backend.spec`
- Verify all dependencies are listed in `pyproject.toml`
