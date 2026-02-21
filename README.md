# Workspace Chat Migrator

A Python script to migrate (copy) VS Code and Cursor workspace folders from a source path to a new destination while preserving **ALL** agent chat history, workspace state, and settings.

## The Problem

VS Code and Cursor store workspace state (including Copilot/Cursor chat history, UI state, and local settings) in a global `workspaceStorage` directory. The folder names in this directory are hashes generated from the workspace's absolute path and creation time. 

If you simply copy or move a project folder to a new location, the editor will treat it as a completely new workspace, generating a new hash and an empty storage folder. This results in the loss of all your chat history and local state.

## The Solution

This script automates the migration process by:
1. Copying your project files to the new destination.
2. Finding the original `workspaceStorage` folder for both VS Code and Cursor.
3. Calculating the exact hash the editors will use for the new destination.
4. Copying the storage folder to the new hash location.
5. Deeply updating all internal paths (including inside SQLite databases like `state.vscdb` and JSON files) to point to the new location.

## Prerequisites

- Python 3.6+
- Node.js (optional, but recommended for 100% accurate hash calculation matching VS Code's internal algorithm)

## Usage

Run the script using the provided wrapper script (`run.sh` for macOS/Linux, `run.bat` for Windows), which automatically sets up and uses a Python virtual environment (`venv`):

### macOS / Linux
```bash
./run.sh --source /path/to/source/folder --dest /path/to/new/folder
```

### Windows
```cmd
run.bat --source C:\path\to\source\folder --dest C:\path\to\new\folder
```

### Options

- `--source`: The absolute or relative path to the original workspace folder (or root folder if using `--batch`).
- `--dest`: The absolute or relative path to the new workspace folder (or root folder if using `--batch`).
- `--batch`: Treat the source and destination paths as root directories containing multiple workspaces. The script will iterate through all subdirectories in the source and migrate them to the destination.
- `--no-copy`: Skip copying the actual project files. Use this if you have already moved or copied the files yourself and just want to migrate the chat history and workspace state.

### Example

```bash
# Copy a single project and migrate its chat history
./run.sh --source ~/git/old-project --dest ~/git/new-project

# Migrate chat history for a project you already moved
./run.sh --source ~/git/old-project --dest ~/git/new-project --no-copy

# Batch migrate ALL workspaces in a directory
./run.sh --source ~/git/old-workspaces --dest ~/git/new-workspaces --batch
```

*(On Windows, use `run.bat` instead of `./run.sh` and use Windows-style paths like `C:\git\old-project`)*

## How it works under the hood

1. **Hash Calculation**: VS Code and Cursor calculate the workspace hash using `md5(path + birthtime)`. The script replicates this exactly.
2. **Storage Discovery**: It scans `~/Library/Application Support/Code/User/workspaceStorage` (and the Cursor equivalent) to find the folder matching your source path.
3. **Path Replacement**: It connects to the `state.vscdb` SQLite database and recursively scans text files to replace all occurrences of the old absolute path and `file://` URI with the new ones.

## Supported Editors

- Visual Studio Code
- Cursor

## Credits

This tool was written by **Gemini 3.1 Pro (Preview)** via GitHub Copilot.

## Notes

- **Close your editors**: It is highly recommended to close VS Code and Cursor before running this script to ensure the SQLite databases are not locked.
- **Multi-root workspaces**: Currently optimized for single-folder workspaces. Multi-root workspaces (`.code-workspace` files) may require manual adjustments.
