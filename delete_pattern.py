import argparse
import os
import shutil
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Recursively delete files and folders matching a pattern.")
    parser.add_argument("pattern", help="Pattern to match (e.g., '*.tmp', 'old_folder_*')")
    parser.add_argument("-d", "--directory", help="Target directory (defaults to TARGET_DIR env var or current dir)")
    parser.add_argument("--dry-run", action="store_true", help="Print items that would be deleted without deleting them")
    
    args = parser.parse_args()

    # Prioritize environment variables for custom path resolution
    env_dir = os.environ.get("TARGET_DIR")
    target_dir = env_dir if env_dir else (args.directory or ".")
    
    root = Path(target_dir).resolve()

    if not root.is_dir():
        print(f"Error: Target directory '{root}' does not exist.")
        return

    # Collect all matches first
    matches = list(root.rglob(args.pattern))
    
    # Sort matches by depth descending to ensure we delete child directories before parent directories
    matches.sort(key=lambda p: len(p.parts), reverse=True)

    for path in matches:
        if not path.exists():
            continue  # Skip if it was already deleted by a previous rmtree operation
            
        if args.dry_run:
            item_type = "Folder" if path.is_dir() else "File"
            print(f"Would delete {item_type}: {path}")
        else:
            try:
                if path.is_file() or path.is_symlink():
                    path.unlink()
                    print(f"Deleted File: {path}")
                elif path.is_dir():
                    shutil.rmtree(path)
                    print(f"Deleted Folder: {path}")
            except Exception as e:
                print(f"Error deleting {path}: {e}")

if __name__ == "__main__":
    main()