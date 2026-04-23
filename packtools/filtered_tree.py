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
import os
import re
import sys
from pathlib import Path

# Directories always excluded from the walk.
IGNORED_DIRS: frozenset[str] = frozenset({
    ".git", "__pycache__", ".venv", ".pytest_cache", "node_modules",
})


def _collect_matches(root: Path, pattern: re.Pattern) -> list[Path]:
    """
    Return all files under root whose names match pattern, in walk order.

    Prunes IGNORED_DIRS in-place so os.walk never descends into them.

    Example:
        _collect_matches(Path("src"), re.compile(r"\\.py$"))
        # → [Path("src/cli.py"), Path("src/lib/utils.py"), ...]
    """
    matches = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in-place so os.walk skips ignored directories entirely.
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for name in sorted(filenames):
            if pattern.search(name):
                matches.append(Path(dirpath) / name)
    return matches


def _render_tree(root: Path, paths: list[Path]) -> str:
    """
    Build an ASCII tree string for the given paths under root.

    Only directories that are ancestors of at least one path are shown.
    Entries within each directory are sorted dirs-first, then files,
    both alphabetically.

    Example:
        _render_tree(Path("src"), [Path("src/a.py"), Path("src/sub/b.py")])
        # → "├── a.py\\n└── sub/\\n    └── b.py\\n"
    """
    # Group paths by their parent directory, relative to root.
    # dir_children[rel_dir] = sorted list of (is_file, name, full_path) tuples
    from collections import defaultdict
    dir_children: dict[Path, list[tuple[bool, str, Path]]] = defaultdict(list)

    for p in paths:
        rel = p.relative_to(root)
        parts = rel.parts

        # Register every ancestor directory so it appears in the tree.
        for depth in range(len(parts) - 1):
            parent = Path(*parts[:depth]) if depth > 0 else Path(".")
            child_dir = Path(*parts[:depth + 1])
            entry = (False, parts[depth], root / child_dir)
            if entry not in dir_children[parent]:
                dir_children[parent].append(entry)

        # Register the file itself under its immediate parent.
        parent = Path(*parts[:-1]) if len(parts) > 1 else Path(".")
        dir_children[parent].append((True, parts[-1], p))

    # Deduplicate while preserving insertion order isn't needed — sort instead.
    for key in dir_children:
        seen = set()
        deduped = []
        for entry in dir_children[key]:
            if entry not in seen:
                seen.add(entry)
                deduped.append(entry)
        # Dirs first, then files, both alphabetically.
        dir_children[key] = sorted(deduped, key=lambda e: (e[0], e[1].lower()))

    def _render(rel_dir: Path, prefix: str) -> str:
        children = dir_children.get(rel_dir, [])
        lines = []
        for i, (is_file, name, _full) in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            label = name if is_file else f"{name}/"
            lines.append(f"{prefix}{connector}{label}")
            if not is_file:
                extension = "    " if is_last else "│   "
                child_rel = rel_dir / name if rel_dir != Path(".") else Path(name)
                lines.append(_render(child_rel, prefix + extension))
        return "\n".join(filter(None, lines))

    body = _render(Path("."), "")
    return (body + "\n") if body else ""


def build_filtered_tree(directory: Path, pattern: re.Pattern) -> str:
    """
    Return a full ASCII tree string for files under directory matching pattern.

    Example:
        build_filtered_tree(Path("."), re.compile(r"\\.py$"))
        # → ".\\n├── cli.py\\n└── lib/\\n    └── utils.py\\n"
    """
    matches = _collect_matches(directory, pattern)
    if not matches:
        return f"{directory.name}/\n(no matches)\n"
    return f"{directory.name}/\n" + _render_tree(directory, matches)


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
        print(f"Error: {args.directory} is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    try:
        pattern = re.compile(args.regex)
    except re.error as exc:
        print(f"Error: Invalid regex: {exc}", file=sys.stderr)
        sys.exit(1)

    output = build_filtered_tree(args.directory, pattern)

    if args.out:
        args.out.write_text(output, encoding="utf-8")
        print(f"Tree written to {args.out}")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
