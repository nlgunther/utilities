"""
filtered_tree.py — Print a regex-filtered ASCII directory tree.

Walks a directory recursively and prints only files whose names match the
given regular expression, along with the ancestor directories needed to
show their location.  Empty directories (after filtering) are omitted.

Usage:
    filtered-tree <directory> <regex> [--out FILE]

Examples:
    filtered-tree . "\\.py$"
    filtered-tree src "test_.*\\.py$" --out tree.txt
"""

import argparse
import re
import sys
from pathlib import Path

# Directories always skipped when building the tree.
IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", ".venv", ".pytest_cache", "node_modules",
})


def build_tree(directory: Path, pattern: re.Pattern, prefix: str = "") -> str:
    """
    Recursively build an ASCII tree string of files matching pattern.

    Directories are included only if they contain at least one matching
    file somewhere in their subtree.  Entries within each directory are
    sorted dirs-first, then files, both alphabetically.

    Example:
        build_tree(Path("."), re.compile(r"\\.py$"))
        # →  "├── packtools/\\n│   ├── __init__.py\\n│   └── cli.py\\n"
    """
    try:
        entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return ""

    valid: list[Path] = []
    for p in entries:
        if p.name in IGNORED_DIRS:
            continue
        if p.is_file():
            if pattern.search(p.name):
                valid.append(p)
        elif build_tree(p, pattern):          # keep dir only if it has matches
            valid.append(p)

    tree = ""
    for i, p in enumerate(valid):
        is_last  = i == len(valid) - 1
        connector = "└── " if is_last else "├── "
        tree += f"{prefix}{connector}{p.name}\n"
        if p.is_dir():
            extension = "    " if is_last else "│   "
            tree += build_tree(p, pattern, prefix + extension)
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a regex-filtered ASCII directory tree.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("directory", type=Path, help="Root directory to scan")
    parser.add_argument("regex",     type=str,  help="Regular expression to match filenames")
    parser.add_argument("--out",     type=Path, help="Optional output file path")
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Error: {args.directory} is not a valid directory.")
        sys.exit(1)

    try:
        pattern = re.compile(args.regex)
    except re.error as exc:
        print(f"Error: Invalid regex: {exc}")
        sys.exit(1)

    output = f"{args.directory.name}/\n" + build_tree(args.directory, pattern)

    if args.out:
        args.out.write_text(output, encoding="utf-8")
        print(f"Tree written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
