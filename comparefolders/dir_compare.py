"""
dir_compare.py — Compare two directory trees file by file.

Walks both directories recursively, optionally filtering filenames by a
regexp, and produces a table showing the union of all files at all levels.
Files present in both directories are shown with their hash signatures and
a MATCH / NO_MATCH verdict.  Files present in only one directory are shown
as PRESENT / ABSENT.

Usage:
    python dir_compare.py <dir_a> <dir_b> [--filter REGEXP] [--output FILE]

Examples:
    python dir_compare.py . C:\\backup\\statement_guard
    python dir_compare.py src dst --filter "\\.py$"
    python dir_compare.py src dst --filter "\\.py$" --output diff.txt
"""

import argparse
import hashlib
import os
import re
import sys


# ---------------------------------------------------------------------------
# Shared with manifest_check.py
# ---------------------------------------------------------------------------

def sha16(data: bytes) -> str:
    """SHA-256 of CRLF-normalised bytes, first 16 hex chars."""
    n = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(n).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Directory walking
# ---------------------------------------------------------------------------

def collect_files(root: str, pattern: re.Pattern | None) -> dict[str, str]:
    """
    Walk root recursively and return {relative_path: sha16} for every file
    whose name matches pattern (or all files if pattern is None).

    Relative paths use forward slashes for cross-platform consistency.
    """
    result: dict[str, str] = {}
    for dirpath, _dirs, filenames in os.walk(root):
        for name in filenames:
            if pattern and not pattern.search(name):
                continue
            full = os.path.join(dirpath, name)
            rel  = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                with open(full, "rb") as f:
                    data = f.read()
                result[rel] = sha16(data)
            except OSError:
                result[rel] = "ERROR"
    return result


# ---------------------------------------------------------------------------
# Table building
# ---------------------------------------------------------------------------

def build_rows(
    files_a: dict[str, str],
    files_b: dict[str, str],
    label_a: str,
    label_b: str,
) -> list[tuple[str, str, str, str]]:
    """
    Return list of (path, hash_a, hash_b, status) for the union of both sets,
    sorted lexicographically (which naturally groups by subdirectory level).

    status values:
        MATCH     — present in both, hashes identical
        NO_MATCH  — present in both, hashes differ
        PRESENT_A — only in dir_a  (hash_b = "ABSENT")
        PRESENT_B — only in dir_b  (hash_a = "ABSENT")
    """
    all_paths = sorted(set(files_a) | set(files_b))
    rows = []
    for path in all_paths:
        in_a = path in files_a
        in_b = path in files_b
        sha_a = files_a.get(path, "")
        sha_b = files_b.get(path, "")

        if in_a and in_b:
            status = "MATCH" if sha_a == sha_b else "NO_MATCH"
        elif in_a:
            status = "PRESENT_A"
            sha_b  = "ABSENT"
        else:
            status = "PRESENT_B"
            sha_a  = "ABSENT"

        rows.append((path, sha_a, sha_b, status))

    return rows


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_table(
    rows: list[tuple[str, str, str, str]],
    label_a: str,
    label_b: str,
) -> str:
    """Render the comparison table as a string."""
    # Column widths
    W_path   = max((len(r[0]) for r in rows), default=4)
    W_path   = max(W_path, 4)
    W_hash   = 16
    W_label  = max(len(label_a), len(label_b), W_hash)
    W_status = max(len("NO_MATCH"), len("PRESENT_A"))

    fmt = "%-*s  %-*s  %-*s  %s"
    header = fmt % (
        W_path, "File",
        W_label, label_a,
        W_label, label_b,
        "Status",
    )
    sep = "-" * (W_path + 2 + W_label + 2 + W_label + 2 + W_status)

    lines = [header, sep]
    prev_dir = None
    for path, sha_a, sha_b, status in rows:
        # Blank line between subdirectories for readability
        cur_dir = os.path.dirname(path)
        if prev_dir is not None and cur_dir != prev_dir:
            lines.append("")
        prev_dir = cur_dir

        lines.append(fmt % (W_path, path, W_label, sha_a, W_label, sha_b, status))

    lines.append(sep)

    # Summary counts
    total     = len(rows)
    n_match   = sum(1 for r in rows if r[3] == "MATCH")
    n_nomatch = sum(1 for r in rows if r[3] == "NO_MATCH")
    n_only_a  = sum(1 for r in rows if r[3] == "PRESENT_A")
    n_only_b  = sum(1 for r in rows if r[3] == "PRESENT_B")

    lines.append("")
    lines.append("Total files : %d" % total)
    lines.append("  MATCH     : %d" % n_match)
    lines.append("  NO_MATCH  : %d" % n_nomatch)
    lines.append("  Only in A : %d  (%s)" % (n_only_a, label_a))
    lines.append("  Only in B : %d  (%s)" % (n_only_b, label_b))

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare two directory trees file by file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("dir_a", help="First directory (A)")
    parser.add_argument("dir_b", help="Second directory (B)")
    parser.add_argument(
        "--filter", "-f", dest="pattern", default=None,
        help="Optional regexp to filter filenames (e.g. '\\.py$')",
    )
    parser.add_argument(
        "--output", "-o", dest="output", default=None,
        help="Optional path to write the table (also printed to console)",
    )
    args = parser.parse_args()

    dir_a = os.path.abspath(args.dir_a)
    dir_b = os.path.abspath(args.dir_b)

    for d, label in [(dir_a, "dir_a"), (dir_b, "dir_b")]:
        if not os.path.isdir(d):
            print("Error: %s is not a directory: %s" % (label, d))
            sys.exit(1)

    pattern = re.compile(args.pattern) if args.pattern else None

    label_a = os.path.basename(dir_a) or dir_a
    label_b = os.path.basename(dir_b) or dir_b

    # Collect
    files_a = collect_files(dir_a, pattern)
    files_b = collect_files(dir_b, pattern)

    if not files_a and not files_b:
        print("No files found in either directory (check --filter pattern).")
        sys.exit(0)

    # Build and format
    rows  = build_rows(files_a, files_b, label_a, label_b)
    table = format_table(rows, label_a, label_b)

    print()
    print("A: %s" % dir_a)
    print("B: %s" % dir_b)
    if pattern:
        print("Filter: %s" % args.pattern)
    print()
    print(table)

    if args.output:
        out = os.path.abspath(args.output)
        with open(out, "w", encoding="utf-8") as f:
            f.write("# dir_compare.py output\n")
            f.write("# A: %s\n" % dir_a)
            f.write("# B: %s\n" % dir_b)
            if pattern:
                f.write("# Filter: %s\n" % args.pattern)
            f.write("#\n")
            f.write(table)
        print("Wrote: %s" % out)


if __name__ == "__main__":
    main()
