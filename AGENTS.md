# Agent Operational Guide for Reshadeck

## 1. Project Overview
**Reshadeck** is a Decky Loader plugin for the Steam Deck (Linux) that manages and applies ReShade shaders to games running via Gamescope.

### Core Functionality
-   **Frontend (Typescript/React)**: UI for selecting shaders, tweaking parameters, and managing per-game profiles.
-   **Backend (Python)**: Handles file operations, configuration persistence, and executes the shader application script.
-   **Shell Scripts**: `set_shader.sh` applies the shader to the running gamescope instance.

## 2. Architecture & Patterns

### Configuration Management (Global & Per-Game)
-   **Dual Mode**: The plugin supports both global settings (applied to all games) and per-game profiles.
-   **Storage**: Configuration is stored in a JSON file.
    -   Key: `_global` for global settings.
    -   Key: `AppID` (string) for per-game settings.
    -   **Selection Logic**: If a game has `per_game: true` in its config (or the user toggles it), the plugin loads settings from `AppID`. Otherwise, it falls back to `_global`.
-   **Toggling**: The frontend provides a "Per-Game Profile" toggle to switch between these modes for the active game.

### Shader Parameters
-   **Parsing**: The backend `main.py` parses `.fx` files for `uniform` definitions, including custom annotations like `ui_type`, `ui_min`, etc.
-   **Application**: Parameters are patched directly into the `.fx` files before application.

## 3. Workflows

### Release Workflow (`.github/workflows/release.yml`)
-   **Trigger**: Push to `main`.
-   **Versioning Logic**:
    -   Analyzes commits since last tag.
    -   `feat` -> Minor bump.
    -   `fix`, `chore` -> Patch bump.
    -   `!`, `BREAKING CHANGE:` -> Major bump.
    -   `docs`, `ci` -> Skip.
-   **Process**:
    1.  Calculates new version.
    2.  Updates `package.json` in a **detached commit**.
    3.  Tags the detached commit.
    4.  Builds the release artifact (`.zip`).
    5.  Publishes GitHub Release with changelog.
    -   **Note**: The metadata update (version bump) is NOT pushed back to `main`, keeping the main branch history clean.

### Build Build
-   **Command**: `./build_release.sh`
-   **Output**: A zip file in the root directory named `jeanbottein-reshadeck-[version].zip`.

## 4. Development Tips
-   **Frontend**: `src/index.tsx` is the entry point. Uses `decky-frontend-lib`.
-   **Backend**: `main.py` runs as a service managed by Decky Loader.
-   **Testing**:
    -   Frontend changes: `npm run build`.
    -   Full plugin test: Must be deployed to a Steam Deck.
