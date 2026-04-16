"""
delete_pattern.py — Recursively delete files and folders matching a glob pattern.

Collects all matches under the target directory (deepest paths first so child
items are removed before their parents), then deletes each one.  Use
--dry-run to preview what would be deleted without touching the filesystem.

Usage:
    delete-pattern <pattern> [--directory DIR] [--dry-run]

Examples:
    delete-pattern "*.pyc"
    delete-pattern "__pycache__" --directory src
    delete-pattern "*.tmp" --dry-run
"""

import argparse
import shutil
import sys
from pathlib import Path


def collect_matches(root: Path, pattern: str) -> list[Path]:
    """
    Return all paths under root matching pattern, sorted deepest-first.

    Deepest-first ordering ensures that when a matched directory contains
    matched children, the children are removed before rmtree touches the
    parent — avoiding 'already deleted' surprises.
    """
    matches = list(root.rglob(pattern))
    matches.sort(key=lambda p: len(p.parts), reverse=True)
    return matches


def delete_matches(matches: list[Path], dry_run: bool) -> None:
    """Delete (or preview) each matched path."""
    for path in matches:
        if not path.exists():
            # A parent rmtree already removed this entry.
            continue

        if dry_run:
            kind = "Folder" if path.is_dir() else "File"
            print(f"Would delete {kind}: {path}")
            continue

        try:
            if path.is_file() or path.is_symlink():
                path.unlink()
                print(f"Deleted File: {path}")
            elif path.is_dir():
                shutil.rmtree(path)
                print(f"Deleted Folder: {path}")
        except Exception as exc:
            print(f"Error deleting {path}: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recursively delete files and folders matching a glob pattern.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pattern",
        help="Glob pattern to match (e.g. '*.tmp', '__pycache__')")
    parser.add_argument("-d", "--directory", default=".",
        help="Target directory (default: current directory)")
    parser.add_argument("--dry-run", action="store_true",
        help="Print items that would be deleted without deleting them")
    args = parser.parse_args()

    root = Path(args.directory).resolve()
    if not root.is_dir():
        print(f"Error: Target directory '{root}' does not exist.")
        sys.exit(1)

    matches = collect_matches(root, args.pattern)
    if not matches:
        print(f"No matches for pattern '{args.pattern}' under {root}")
        return

    delete_matches(matches, args.dry_run)


if __name__ == "__main__":
    main()
