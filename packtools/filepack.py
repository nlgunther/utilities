"""
filepack.py — Codebase archiving and LLM-context toolkit.

Commands:
    zip     Archive files matching a regex/glob to a zip file.
    flatten Copy matched files to a single directory and build a directory map.
    pack    Serialise the codebase into balanced text bins for LLM ingestion.

Usage:
    filepack zip     <path> <regex> [-o OUTPUT]
    filepack flatten <path> <regex> -o OUTPUT_DIR
    filepack pack    <path> [regex]  [-b BINS] [--prefix PREFIX]
    filepack -v ...  (enable debug logging)

Examples:
    filepack zip . "\\.py$" -o archive.zip
    filepack flatten src "\\.py$" -o flat/
    filepack pack . "\\.py$" -b 3 --prefix ctx
"""
from __future__ import annotations

import argparse
import logging
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Iterable, Iterator

from packtools.filtered_tree import build_filtered_tree, IGNORED_DIRS

log = logging.getLogger(__name__)

# Delimiters used to wrap each file in a pack bin.
_SEP   = "# " + "=" * 75
_BEGIN = "# --- BEGIN FILE: {path} ---"
_END   = "# --- END FILE: {path} ---"


# ---------------------------------------------------------------------------
# Core discovery
# ---------------------------------------------------------------------------

def get_file_stream(
    input_path: str | Path,
    regex: str = ".*",
    glob: str | None = None,
    exclude: Iterable[str] = (),
) -> tuple[Path, Iterator[Path]]:
    """
    Resolve base directory and yield files matching glob & regex.

    Returns (base, iterator) so callers can compute relative paths.

    Example:
        base, files = get_file_stream("src", r"\\.py$")
        for p in files:
            print(p.relative_to(base))
    """
    raw = str(input_path).strip('"').strip("'").strip()
    base = Path(raw).resolve()
    if not base.exists():
        raise FileNotFoundError(f"Path does not exist: {base}")

    glob_pattern = glob or "**/*"
    if not base.is_dir():
        glob_pattern = base.name
        base = base.parent

    ignore = set(exclude) | IGNORED_DIRS
    pattern = re.compile(regex)

    def _stream() -> Iterator[Path]:
        for p in base.glob(glob_pattern):
            if p.is_file() and not any(part in ignore for part in p.parts):
                if pattern.search(p.name):
                    yield p

    return base, _stream()


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def cmd_zip(input_path: str, regex: str, output: str) -> int:
    """Archive discovered files into a ZIP, preserving directory structure."""
    base, files = get_file_stream(input_path, regex)
    out_path = Path(output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if out_path.exists() else "w"
    count = 0
    with zipfile.ZipFile(out_path, mode, zipfile.ZIP_DEFLATED) as zf:
        for fp in files:
            zf.write(fp, arcname=fp.relative_to(base))
            count += 1
    return count


def cmd_flatten(input_path: str, regex: str, output_dir: str) -> int:
    """
    Flatten matched files into one directory and write a directory_map.txt.

    Name collisions are resolved by prepending the immediate parent directory
    name (e.g. module/main.py → module_main.py).
    """
    base, files = get_file_stream(input_path, regex)
    dest = Path(output_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    pattern     = re.compile(regex)
    tree_diagram = build_filtered_tree(base, pattern)
    (dest / "directory_map.txt").write_text(tree_diagram, encoding="utf-8")
    log.debug("Directory map:\n%s", tree_diagram)

    count = 0
    for fp in files:
        target_name = fp.name
        if (dest / target_name).exists():
            target_name = f"{fp.parent.name}_{fp.name}"
        shutil.copy2(fp, dest / target_name)
        count += 1
    return count


def cmd_pack(source: str, regex: str, bins: int, prefix: str) -> int:
    """Pack codebase text files into N balanced text bins for LLM ingestion."""
    base, files = get_file_stream(source, regex)

    # Sort descending by size for greedy bin-packing (largest file first).
    records = sorted(
        ((f, f.stat().st_size) for f in files),
        key=lambda x: x[1],
        reverse=True,
    )
    if not records:
        return 0

    bin_contents: list[list[Path]] = [[] for _ in range(bins)]
    bin_sizes = [0] * bins
    for fp, size in records:
        idx = bin_sizes.index(min(bin_sizes))
        bin_contents[idx].append(fp)
        bin_sizes[idx] += size

    for i, contents in enumerate(bin_contents):
        if not contents:
            continue
        out_p = Path(f"{prefix}_{i + 1}.txt")
        with out_p.open("w", encoding="utf-8") as f:
            for fp in contents:
                rel = fp.relative_to(base).as_posix()
                f.write(f"\n{_SEP}\n{_BEGIN.format(path=rel)}\n{_SEP}\n\n")
                try:
                    f.write(fp.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    f.write("# [SKIPPED: Content unreadable]\n")
                f.write(f"\n\n{_END.format(path=rel)}\n")

    return len(records)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="filepack",
        description="Codebase archiving and LLM-context toolkit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_zip = sub.add_parser("zip", help="Archive matched files into a ZIP.")
    p_zip.add_argument("path",  help="Target directory")
    p_zip.add_argument("regex", help="Filename regex filter")
    p_zip.add_argument("-o", "--output", default="archive.zip")

    p_flat = sub.add_parser("flatten", help="Copy matching files to a flat folder.")
    p_flat.add_argument("path",  help="Target directory")
    p_flat.add_argument("regex", help="Filename regex filter")
    p_flat.add_argument("-o", "--output", required=True)

    p_pack = sub.add_parser("pack", help="Serialise files for LLM ingestion.")
    p_pack.add_argument("path",  help="Target directory")
    p_pack.add_argument("regex", nargs="?", default=r"\.py$", help="Filename regex filter")
    p_pack.add_argument("-b", "--bins",   type=int, default=1, help="Number of output bins")
    p_pack.add_argument("--prefix",       default="corpus_pack", help="Output filename prefix")

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(format="%(message)s", level=level, stream=sys.stderr)

    try:
        if args.cmd == "zip":
            n = cmd_zip(args.path, args.regex, args.output)
        elif args.cmd == "flatten":
            n = cmd_flatten(args.path, args.regex, args.output)
        elif args.cmd == "pack":
            n = cmd_pack(args.path, args.regex, args.bins, args.prefix)
        log.info("Success. Processed %d files.", n)
    except Exception as exc:
        log.error("Error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
