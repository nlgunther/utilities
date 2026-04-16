"""
filepack.py
=============
A unified codebase archiving and LLM-context toolkit.

Commands:
  zip     - Archives files matching a regex/glob to a zip file.
  flatten - Copies matched files to a single directory and builds a directory map.
  pack    - Serializes the codebase into balanced text bins for LLM ingestion.
"""
from __future__ import annotations

import argparse
import re
import sys
import shutil
import zipfile
from pathlib import Path
from typing import Iterator, Iterable
from loguru import logger

# --- Constants ---
DEFAULT_IGNORE = frozenset({".git", "__pycache__", ".venv", ".pytest_cache", "node_modules"})
PACK_SEP = "# " + "=" * 75
PACK_BEGIN = "# --- BEGIN FILE: {path} ---"
PACK_END = "# --- END FILE: {path} ---"

# =============================================================================
# CORE DISCOVERY & UTILITIES
# =============================================================================

def get_file_stream(
    input_path: str | Path, 
    regex: str = ".*", 
    glob: str | None = None,
    exclude: Iterable[str] = ()
) -> tuple[Path, Iterator[Path]]:
    """Resolves base directory and yields files matching glob & regex patterns."""
    raw_path = str(input_path).strip('"').strip("'").strip()
    base = Path(raw_path).resolve()
    
    if not base.exists():
        raise FileNotFoundError(f"Path does not exist: {base}")

    # Adjust base if input is a specific file/glob
    glob_pattern = glob or "**/*"
    if not base.is_dir():
        glob_pattern = base.name
        base = base.parent

    ignore_set = set(exclude) | DEFAULT_IGNORE
    pattern = re.compile(regex)

    def _stream() -> Iterator[Path]:
        for p in base.glob(glob_pattern):
            if p.is_file() and not any(part in ignore_set for part in p.parts):
                if pattern.search(p.name):
                    yield p

    return base, _stream()

def generate_filtered_tree(directory: Path, pattern: re.Pattern, prefix: str = "") -> str:
    """Recursively builds an ASCII tree diagram of files matching the regex."""
    paths = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    
    valid_paths = []
    for p in paths:
        if p.name in DEFAULT_IGNORE:
            continue
        if p.is_file():
            if pattern.search(p.name):
                valid_paths.append(p)
        else:
            if generate_filtered_tree(p, pattern):  # Keep dir if it contains matches
                valid_paths.append(p)

    tree_str = ""
    for i, path in enumerate(valid_paths):
        is_last = i == len(valid_paths) - 1
        connector = "└── " if is_last else "├── "
        tree_str += f"{prefix}{connector}{path.name}\n"
        
        if path.is_dir():
            extension = "    " if is_last else "│   "
            tree_str += generate_filtered_tree(path, pattern, prefix + extension)
            
    return tree_str

# =============================================================================
# COMMAND ROUTINES
# =============================================================================

def cmd_zip(input_path: str, regex: str, output: str) -> int:
    """Archives discovered files into a ZIP, preserving directory structure."""
    base, files = get_file_stream(input_path, regex)
    out_path = Path(output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with zipfile.ZipFile(out_path, "a" if out_path.exists() else "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in files:
            zf.write(fp, arcname=fp.relative_to(base))
            count += 1
    return count

def cmd_flatten(input_path: str, regex: str, output_dir: str) -> int:
    """Flattens matched files into one directory and creates a structural map."""
    base, files = get_file_stream(input_path, regex)
    dest = Path(output_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    # Generate and save structural map
    pattern = re.compile(regex)
    tree_diagram = f"{base.name}/\n" + generate_filtered_tree(base, pattern)
    (dest / "directory_map.txt").write_text(tree_diagram, encoding="utf-8")
    
    count = 0
    for fp in files:
        target_name = fp.name
        if (dest / target_name).exists():
            target_name = f"{fp.parent.name}_{fp.name}"  # Simple collision handling
            
        shutil.copy2(fp, dest / target_name)
        count += 1
        
    logger.info(f"\nFiltered Tree Map:\n{tree_diagram}")
    return count

def cmd_pack(source: str, regex: str, bins: int, prefix: str) -> int:
    """Packs codebase text files into N balanced text bins for LLMs."""
    base, files = get_file_stream(source, regex)
    
    # Sort files by size for greedy bin-packing
    records = sorted([(f, f.stat().st_size) for f in files], key=lambda x: x[1], reverse=True)
    if not records: return 0

    bin_contents: list[list[Path]] = [[] for _ in range(bins)]
    bin_sizes = [0] * bins

    for fp, size in records:
        idx = bin_sizes.index(min(bin_sizes))
        bin_contents[idx].append(fp)
        bin_sizes[idx] += size

    for i, contents in enumerate(bin_contents):
        if not contents: continue
        out_p = Path(f"{prefix}_{i+1}.txt")
        with out_p.open("w", encoding="utf-8") as f:
            for fp in contents:
                rel = fp.relative_to(base).as_posix()
                f.write(f"\n{PACK_SEP}\n{PACK_BEGIN.format(path=rel)}\n{PACK_SEP}\n\n")
                try:
                    f.write(fp.read_text(encoding="utf-8", errors="replace"))
                except Exception:
                    f.write("# [SKIPPED: Content unreadable]\n")
                f.write(f"\n\n{PACK_END.format(path=rel)}\n")
    return len(records)

# =============================================================================
# CLI ENTRYPOINT
# =============================================================================

def _main():
    parser = argparse.ArgumentParser(prog="filepack", description="Codebase management toolkit.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logs")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # ZIP
    p_zip = sub.add_parser("zip", help="Archive matched files.")
    p_zip.add_argument("path", help="Target directory")
    p_zip.add_argument("regex", help="Filename regex filter")
    p_zip.add_argument("-o", "--output", default="archive.zip")

    # FLATTEN
    p_flat = sub.add_parser("flatten", help="Copy matching files to a flat folder.")
    p_flat.add_argument("path", help="Target directory")
    p_flat.add_argument("regex", help="Filename regex filter")
    p_flat.add_argument("-o", "--output", required=True)

    # PACK
    p_pack = sub.add_parser("pack", help="Serialize files for LLMs.")
    p_pack.add_argument("path", help="Target directory")
    p_pack.add_argument("regex", default=r"\.py$", help="Filename regex filter")
    p_pack.add_argument("-b", "--bins", type=int, default=1, help="Number of text bins")
    p_pack.add_argument("--prefix", default="corpus_pack", help="Output file prefix")

    args = parser.parse_args()
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "INFO", format="<level>{message}</level>")

    try:
        if args.cmd == "zip":
            n = cmd_zip(args.path, args.regex, args.output)
        elif args.cmd == "flatten":
            n = cmd_flatten(args.path, args.regex, args.output)
        elif args.cmd == "pack":
            n = cmd_pack(args.path, args.regex, args.bins, args.prefix)
            
        logger.info(f"Success. Processed {n} files.")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    _main()