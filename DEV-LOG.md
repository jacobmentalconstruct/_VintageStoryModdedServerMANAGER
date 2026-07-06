# Vintage Story Server Manager DEV LOG

Last updated: 2026-07-06

## Purpose

This project is a local Tkinter manager for running Vintage Story dedicated servers without needing to hand-edit server folders, mod lists, or world generation config files. The app now treats each generated server under `servers/` as a managed Vintage Story data root and lets a host prepare maps, apply mods, start/stop servers, bundle client mods, and maintain backups from one UI.

## Runtime Layout

- `start.bat` launches the app with `python -m src.app`.
- `src/app.py` creates `UiApp` with `src` as the app directory.
- The controller resolves the project root from the app directory and stores managed runtime data outside source:
  - `servers/` for generated server data roots.
  - `mods/` for the project-local mod repository.
  - `server_archives/` for deleted/wiped server archives.
  - `src/vs_server_manager_config.json` for local app state.
- These runtime paths are ignored by Git because they can contain saves, caches, unpacked mods, deep paths, and machine-local settings.

## Architecture

### UI Layer

`src/ui_core/ui_app.py` owns the root Tk window, tab registry, log view, periodic UI pump, generation completion modal, and shutdown handling.

The tab modules under `src/ui_core/tabs/` are thin UI coordinators:

- `dashboard_tab.py`: high-level online/offline/generating status and quick start/stop.
- `server_tab.py`: selected server details, readiness, start/stop, reset/delete/wipe/delete actions.
- `world_tab.py`: world generation controls, server list, config presets, Generate Map.
- `mods_tab.py`: project mod repository, active mod list, mod profile/bundle/download workflows.
- `backup_tab.py`: backup scheduling, snapshot browser, restore flow.
- `player_tab.py`: player command helpers.

### Orchestration Layer

`src/orchestration_core/app_controller.py` is the main application boundary. UI code calls controller methods instead of touching backend services directly.

Responsibilities include:

- Loading and saving `AppState`.
- Discovering managed server worlds.
- Selecting a server and syncing `data_path` / port.
- Writing Vintage Story `serverconfig.json` for map generation.
- Applying active mods to selected server data roots.
- Starting/stopping the dedicated server process.
- Tracking map generation lifecycle.
- Guarding destructive/conflicting actions.
- Running backups and restores.
- Fetching/parsing online mod catalog data.

### Backend Layer

`src/server_manager_core/` contains small focused services:

- `server_process.py`: launches and controls the dedicated server process.
- `backup_manager.py`: creates/list/restores zip backups.
- `mod_manager.py`: scans, copies, bundles, and parses mod information.
- `network_client.py`: talks to Vintage Story ModDB.
- `config_store.py`: JSON persistence for `AppState`.
- `port_checker.py`: local TCP listening checks.
- `models.py`: the `AppState` dataclass.

## Major Features

### Managed Server Worlds

Generated servers are stored in `servers/<server-id>/`. Each folder is used directly as a Vintage Story `--dataPath` root and gets familiar subfolders such as `Mods`, `Saves`, `Cache`, and `Logs`.

The controller writes `.vs_manager_server.json` in each managed server folder so discovery can rebuild the server list if the config state is missing or stale.

### World Generation

The World Gen tab writes a `serverconfig.json` into the selected/generated server data root and then starts the dedicated server when possible. If no server executable is set, the data root is still prepared and the UI tells the user what is missing.

The generated config includes:

- Map size.
- World name and seed.
- Save file location.
- World configuration keys such as landcover, oceanscale, climate, survival, temporal, and resource settings.
- Default server role definitions for `suplayer` and `admin`, preventing Vintage Story from failing on a missing default group code.

### World Config Presets

World Gen includes built-in profiles:

- `Standard`
- `Continents & Oceans`
- `Island Chains`
- `Lush Jungle`
- `Wild Highlands`
- `Crazy Caves`
- `Easy Builders`

User profiles are stored in `AppState.world_profiles`. Saving a profile with the same name as a built-in shadows the built-in; deleting the saved profile reveals the built-in again.

### Map Generation Lock

Map generation is tracked with:

- `map_generation_in_progress`
- `map_generation_server_id`
- `map_generation_started_at`

While generation is active, the controller blocks conflicting operations such as starting another server, generating another map, changing world profiles, applying mods to the server, resetting/deleting/wiping servers, restoring backups, and creating backups.

The UI disables related buttons in Server, World Gen, Backup, and Dashboard tabs. Stop/Kill remain available.

Completion detection uses server output markers, process-exit fallback, and a fallback check for an active save plus listening port. When generation completes or fails, the app shows a modal. The modal has a persistent `Auto-close next time after 10 seconds` checkbox.

### Mods

The app defaults to a project-local `mods/` repository. Users can add mods to an active list, apply them to the selected server, save/load mod profiles, and create a client bundle from the selected active mods.

The online catalog fetch uses `https://mods.vintagestory.at/api/mods`.

### Backups

Backups zip the selected server data root's `Saves` folder into the configured backup root. Restores rename the current `Saves` folder before extracting the selected snapshot.

Restore extraction now validates zip member paths before extraction to avoid writing outside the target folder.

## Stabilization Notes

Recent hardening work included:

- Fixed missing `PortChecker.is_port_listening()` compatibility method.
- Added missing backup controller methods used by the Backups tab.
- Blocked backup/create/restore and server-mod writes during map generation.
- Hardened backup restore against unsafe zip paths.
- Made server process launch portable across Windows/non-Windows by only using `CREATE_NO_WINDOW` on Windows.
- Improved server process cleanup after graceful stops, kills, and natural exits.
- Ensured config save creates the parent directory.
- Added explicit default server roles to generated `serverconfig.json`.
- Switched ModDB catalog URL to HTTPS.
- Added Tk root DPI awareness and UI-pump throttling to reduce window-drag jank.

## Known Gaps / Future Work

- The project currently has no automated tests; `pytest` reports `no tests ran`.
- The app is still a local desktop utility, not a multi-user web dashboard.
- Player admin commands are basic wrappers and would benefit from stronger parsing of server command responses.
- Backup scheduling currently runs in-process with the app; if the UI is closed, scheduled backups do not run.
- Generation-completion detection depends partly on server output and port checks. It is robust enough for current use, but a future improvement could parse Vintage Story log phases more formally.
- The UI still contains some dense Tk layouts. A later pass could consolidate repeated server-list widgets and shared disabled-state behavior.

## Operational Checklist

1. Put reusable mods in project `mods/`.
2. Open the app with `start.bat`.
3. In World Gen, pick or save a config profile.
4. Select active mods in Mods.
5. Generate a map.
6. Wait for the generation modal.
7. Use Server tab to start/stop the selected server.
8. Use Create Bundle in Mods to distribute the active mod set to players.
9. Configure Backups before long-running play.

