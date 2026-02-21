import argparse
import os
import sys
import json
import sqlite3
import shutil
import subprocess
import urllib.parse
import hashlib

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green"
})
console = Console(theme=custom_theme)

def get_workspace_hash(path):
    """
    Calculate the VS Code / Cursor workspace hash for a given path.
    We try to use Node.js to ensure 100% compatibility with VS Code's algorithm.
    If Node.js is not available, we fallback to a pure Python implementation.
    """
    node_script = """
const fs = require('fs');
const crypto = require('crypto');
let path = process.argv[1];
try {
    const stat = fs.statSync(path);
    let ctime;
    if (process.platform === 'linux') {
        ctime = stat.ino;
    } else if (process.platform === 'darwin') {
        ctime = stat.birthtime.getTime();
    } else if (process.platform === 'win32') {
        ctime = Math.floor(stat.birthtimeMs);
        path = path.toLowerCase();
    } else {
        ctime = stat.birthtime.getTime();
    }
    const hash = crypto.createHash('md5').update(path).update(String(ctime)).digest('hex');
    console.log(hash);
} catch (e) {
    console.error(e);
    process.exit(1);
}
"""
    try:
        result = subprocess.run(['node', '-e', node_script, path], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback to pure Python
        try:
            stat = os.stat(path)
            if sys.platform == 'win32':
                # Windows birthtime
                ctime = int(stat.st_ctime * 1000)
                # Windows paths are lowercased for the hash
                path = path.lower()
            elif hasattr(stat, 'st_birthtime'):
                # macOS birthtime
                ctime = int(stat.st_birthtime * 1000)
            else:
                # Linux fallback (VS Code uses ino on Linux)
                ctime = stat.st_ino
                
            hash_input = path + str(ctime)
            return hashlib.md5(hash_input.encode('utf-8')).hexdigest()
        except Exception as e:
            console.print(f"[error]Error calculating hash for {path}: {e}[/error]")
            sys.exit(1)

def find_workspace_storage(base_dir, source_uri):
    """
    Find the workspaceStorage folder that matches the source URI.
    """
    if not os.path.exists(base_dir):
        return None
    
    for folder in os.listdir(base_dir):
        folder_path = os.path.join(base_dir, folder)
        workspace_json_path = os.path.join(folder_path, 'workspace.json')
        if os.path.exists(workspace_json_path):
            try:
                with open(workspace_json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('folder') == source_uri:
                        return folder_path
                    elif data.get('workspace') == source_uri:
                        return folder_path
            except Exception:
                pass
    return None

def replace_in_sqlite(db_path, old_str, new_str, old_uri, new_uri):
    """
    Replace occurrences of old_str with new_str and old_uri with new_uri in the SQLite database.
    """
    if not os.path.exists(db_path):
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if ItemTable exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ItemTable'")
        if not cursor.fetchone():
            conn.close()
            return
            
        cursor.execute("SELECT key, value FROM ItemTable")
        rows = cursor.fetchall()
        
        for key, value in rows:
            if not isinstance(value, str):
                continue
                
            new_value = value
            if old_uri in new_value:
                new_value = new_value.replace(old_uri, new_uri)
            if old_str in new_value:
                new_value = new_value.replace(old_str, new_str)
                
            if new_value != value:
                cursor.execute("UPDATE ItemTable SET value = ? WHERE key = ?", (new_value, key))
                
        conn.commit()
        conn.close()
    except Exception as e:
        console.print(f"[warning]Error updating SQLite DB {db_path}: {e}[/warning]")

def replace_in_files(directory, old_str, new_str, old_uri, new_uri):
    """
    Recursively replace strings in text files within a directory.
    """
    if not os.path.exists(directory):
        return
        
    for root, _, files in os.walk(directory):
        for file in files:
            if file == 'state.vscdb' or file == 'state.vscdb.backup':
                continue # Handled separately
                
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                new_content = content
                if old_uri in new_content:
                    new_content = new_content.replace(old_uri, new_uri)
                if old_str in new_content:
                    new_content = new_content.replace(old_str, new_str)
                    
                if new_content != content:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
            except UnicodeDecodeError:
                pass # Skip binary files
            except Exception as e:
                console.print(f"[warning]Error updating file {file_path}: {e}[/warning]")

def migrate_editor(editor_name, storage_base, source_path, dest_path, source_uri, dest_uri, progress, task):
    source_storage = find_workspace_storage(storage_base, source_uri)
    
    if not source_storage:
        progress.console.print(f"[warning]  ⚠ No {editor_name} workspace storage found for {os.path.basename(source_path)}[/warning]")
        return False
        
    progress.update(task, description=f"[cyan]Migrating {editor_name} for {os.path.basename(source_path)}...")
    
    dest_hash = get_workspace_hash(dest_path)
    dest_storage = os.path.join(storage_base, dest_hash)
    
    if os.path.exists(dest_storage):
        shutil.rmtree(dest_storage)
        
    shutil.copytree(source_storage, dest_storage)
    
    # Update workspace.json
    workspace_json_path = os.path.join(dest_storage, 'workspace.json')
    if os.path.exists(workspace_json_path):
        with open(workspace_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if 'folder' in data:
            data['folder'] = dest_uri
        elif 'workspace' in data:
            data['workspace'] = dest_uri
        with open(workspace_json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
    # Update state.vscdb
    db_path = os.path.join(dest_storage, 'state.vscdb')
    replace_in_sqlite(db_path, source_path, dest_path, source_uri, dest_uri)
    
    # Update other files (like chatSessions)
    replace_in_files(dest_storage, source_path, dest_path, source_uri, dest_uri)
    
    progress.console.print(f"[success]  ✔ {editor_name} migration complete for {os.path.basename(source_path)}[/success]")
    return True

def migrate_workspace(source_path, dest_path, no_copy, progress, overall_task):
    workspace_name = os.path.basename(source_path)
    task = progress.add_task(f"[cyan]Processing {workspace_name}...", total=None)
    
    files_status = "[dim]➖ Skipped[/dim]"
    vscode_status = "[dim]➖ Not Found[/dim]"
    cursor_status = "[dim]➖ Not Found[/dim]"
    details = ""
    
    if not os.path.exists(source_path):
        progress.console.print(f"[error]  ✖ Source path {source_path} does not exist.[/error]")
        progress.update(task, completed=100)
        progress.remove_task(task)
        return {"name": workspace_name, "status": "Failed", "files": "[red]❌ Failed[/red]", "vscode": vscode_status, "cursor": cursor_status, "details": "Source missing"}
        
    if source_path == dest_path:
        progress.console.print(f"[error]  ✖ Source and destination paths are the same for {workspace_name}.[/error]")
        progress.update(task, completed=100)
        progress.remove_task(task)
        return {"name": workspace_name, "status": "Failed", "files": "[red]❌ Failed[/red]", "vscode": vscode_status, "cursor": cursor_status, "details": "Same path"}
        
    # Copy project folder
    if not no_copy:
        if os.path.exists(dest_path):
            progress.console.print(f"[warning]  ⚠ Destination {dest_path} already exists. Skipping copy.[/warning]")
            files_status = "[yellow]⚠️ Exists[/yellow]"
        else:
            progress.update(task, description=f"[cyan]Copying files for {workspace_name}...")
            try:
                shutil.copytree(source_path, dest_path)
                files_status = "[green]✅ Copied[/green]"
            except Exception as e:
                progress.console.print(f"[error]  ✖ Failed to copy {workspace_name}: {e}[/error]")
                progress.update(task, completed=100)
                progress.remove_task(task)
                return {"name": workspace_name, "status": "Failed", "files": "[red]❌ Failed[/red]", "vscode": vscode_status, "cursor": cursor_status, "details": "Copy failed"}
    else:
        if not os.path.exists(dest_path):
            progress.console.print(f"[error]  ✖ Destination {dest_path} does not exist, and --no-copy was specified.[/error]")
            progress.update(task, completed=100)
            progress.remove_task(task)
            return {"name": workspace_name, "status": "Failed", "files": "[red]❌ Failed[/red]", "vscode": vscode_status, "cursor": cursor_status, "details": "Dest missing (--no-copy)"}
        files_status = "[dim]⏭ Skipped[/dim]"
            
    source_uri = f"file://{urllib.parse.quote(source_path)}"
    dest_uri = f"file://{urllib.parse.quote(dest_path)}"
    
    # Handle Windows paths in URIs (e.g., file:///c%3A/...)
    if os.name == 'nt':
        source_uri = f"file:///{urllib.parse.quote(source_path.replace('\\\\', '/'))}"
        dest_uri = f"file:///{urllib.parse.quote(dest_path.replace('\\\\', '/'))}"
    
    if sys.platform == 'darwin':
        vscode_storage_base = os.path.expanduser("~/Library/Application Support/Code/User/workspaceStorage")
        cursor_storage_base = os.path.expanduser("~/Library/Application Support/Cursor/User/workspaceStorage")
    elif sys.platform == 'win32':
        vscode_storage_base = os.path.expandvars(r"%APPDATA%\Code\User\workspaceStorage")
        cursor_storage_base = os.path.expandvars(r"%APPDATA%\Cursor\User\workspaceStorage")
    else:
        # Linux
        vscode_storage_base = os.path.expanduser("~/.config/Code/User/workspaceStorage")
        cursor_storage_base = os.path.expanduser("~/.config/Cursor/User/workspaceStorage")
    
    vscode_success = migrate_editor("VS Code", vscode_storage_base, source_path, dest_path, source_uri, dest_uri, progress, task)
    cursor_success = migrate_editor("Cursor", cursor_storage_base, source_path, dest_path, source_uri, dest_uri, progress, task)
    
    if vscode_success:
        vscode_status = "[green]✅ Migrated[/green]"
    if cursor_success:
        cursor_status = "[green]✅ Migrated[/green]"
        
    progress.update(task, completed=100)
    progress.remove_task(task)
    
    if not vscode_success and not cursor_success:
        details = ""
    
    return {
        "name": workspace_name, 
        "status": "Done", 
        "files": files_status,
        "vscode": vscode_status,
        "cursor": cursor_status,
        "details": details
    }

def main():
    parser = argparse.ArgumentParser(description="Migrate VS Code and Cursor workspaces while preserving chat history.")
    parser.add_argument("--source", required=True, help="Source workspace or root folder path")
    parser.add_argument("--dest", required=True, help="Destination workspace or root folder path")
    parser.add_argument("--no-copy", action="store_true", help="Skip copying the actual project folder")
    parser.add_argument("--batch", action="store_true", help="Treat source and dest as root folders containing multiple workspaces")
    
    args = parser.parse_args()
    
    source_root = os.path.abspath(args.source)
    dest_root = os.path.abspath(args.dest)
    
    console.print(Panel.fit("[bold blue]VS Code & Cursor Workspace Migrator[/bold blue]", border_style="blue"))
    
    workspaces_to_migrate = []
    
    if args.batch:
        if not os.path.isdir(source_root):
            console.print(f"[error]Batch source {source_root} is not a directory.[/error]")
            sys.exit(1)
        
        for item in os.listdir(source_root):
            item_path = os.path.join(source_root, item)
            if os.path.isdir(item_path):
                workspaces_to_migrate.append((item_path, os.path.join(dest_root, item)))
                
        if not workspaces_to_migrate:
            console.print(f"[warning]No directories found in {source_root}[/warning]")
            sys.exit(0)
    else:
        workspaces_to_migrate.append((source_root, dest_root))
        
    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console
    ) as progress:
        
        overall_task = progress.add_task("[bold green]Overall Progress...", total=len(workspaces_to_migrate))
        
        for src, dst in workspaces_to_migrate:
            res = migrate_workspace(src, dst, args.no_copy, progress, overall_task)
            results.append(res)
            progress.advance(overall_task)
            
    # Print Summary Table
    console.print("\n[bold blue]Migration Summary[/bold blue]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Workspace", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Files", justify="center")
    table.add_column("VS Code", justify="center")
    table.add_column("Cursor", justify="center")
    table.add_column("Details", style="dim", no_wrap=True)
    
    for res in results:
        status_display = "[green]✅ Done[/green]" if res["status"] == "Done" else "[red]❌ Failed[/red]"
        table.add_row(
            res["name"], 
            status_display, 
            res["files"],
            res["vscode"],
            res["cursor"],
            res["details"]
        )
        
    console.print(table)
    console.print("\n[bold green]All done![/bold green] You can now open the new folders in VS Code or Cursor.")

if __name__ == "__main__":
    main()
