"""
filepack.py
=============
A dual-purpose toolkit for managing codebase files, with two fully decoupled groups:

  Group 1 – Archive Tools
    Zip/unzip directory trees by regex-matching filenames, preserving folder structure.

  Group 2 – Context Pack Tools
    Serialize a Python package (or any glob-selected files) into N balanced text files
    so that LLMs can ingest the whole codebase, then reassemble the originals verbatim.

Design principles
-----------------
* **Separation of concerns** – The two groups share zero runtime state and no helpers.
* **DRY via constants & helpers** – Every magic string and pattern lives in one place.
* **Safety** – pathlib throughout; directory-traversal guard on unpack; regex pre-compiled.
* **Performance** – I/O caching for bin-packing; lazy generator pipelines for unpacking.
* **Extensibility** – Dynamic exclude lists and standard Python logging over print().
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from typing import Iterator, NamedTuple, Iterable, Sequence

# Loguru replaces standard logging
from loguru import logger


# =============================================================================
# GROUP 1 – ARCHIVE OPERATIONS  (regex-based zipping)
# =============================================================================

def zip_by_regex(
    glob_pattern: str,
    regex_pattern: str,
    output_zip: str | Path = "archive.zip",
    base_dir: str | Path = ".",
) -> int:
    """Zips files matching a glob and regex, appending if the archive exists."""
    
    # --- FIX: Auto-split absolute glob paths ---
    # pathlib.glob() crashes if given an absolute path. We split the string 
    # into a static base directory and a relative glob pattern.
    gp_str = str(glob_pattern)
    if Path(gp_str).is_absolute():
        parts = Path(gp_str).parts
        base_parts = []
        glob_parts = []
        has_wildcard = False
        
        for part in parts:
            if has_wildcard or any(char in part for char in "*?[]"):
                has_wildcard = True
                glob_parts.append(part)
            else:
                base_parts.append(part)
                
        base_dir = Path(*base_parts)
        # Rejoin the wildcard parts with forward slashes for pathlib
        glob_pattern = "/".join(glob_parts) if glob_parts else "*"
    # -------------------------------------------

    base = Path(base_dir).resolve()
    zip_path = Path(output_zip).resolve()
    
    if not base.is_dir():
        raise NotADirectoryError(f"Base directory not found: {base}")

    pattern = _compile_regex(regex_pattern) 
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Scanning '{base}' with glob '{glob_pattern}' for r'{regex_pattern}'...")

    # Phase 1: Discovery & Filtering
    matched_files = sorted(
        filepath for filepath in base.glob(glob_pattern)
        if filepath.is_file() and pattern.search(filepath.name)
    )

    if not matched_files:
        logger.warning("No matching files found.")
        return 0

    action = "Appending to" if zip_path.exists() else "Creating"
    logger.info(f"{action} archive: {zip_path.name}")

    # Phase 2: Archiving
    files_added = 0
    with zipfile.ZipFile(zip_path, "a", zipfile.ZIP_DEFLATED) as zf:
        for filepath in matched_files:
            try:
                arcname = str(filepath.relative_to(base))
            except ValueError:
                arcname = filepath.name

            zf.write(filepath, arcname=arcname)
            files_added += 1
            logger.debug(f"  + {arcname}")

    return files_added


def extract_zip(zip_path: str | Path, target_dir: str | Path) -> None:
    """Extract a ZIP archive into *target_dir*, creating it if necessary."""
    source = Path(zip_path).resolve()
    target = Path(target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)

    logger.info(f"Extracting '{source.name}' → '{target}' …")
    with zipfile.ZipFile(source, "r") as zf:
        zf.extractall(target)


# =============================================================================
# GROUP 2 – CONTEXT PACK OPERATIONS  (LLM text packing / unpacking)
# =============================================================================

#: Default directories excluded from globbing (common ephemeral / tool artefacts).
_DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".pytest_cache", ".git", ".venv", "env", ".mypy_cache",
})

#: Visual separator line and markers for the text pack format.
_SEPARATOR = "# " + "=" * 75
_BEGIN_MARKER = "# --- BEGIN FILE: {path} ---"
_END_MARKER   = "# --- END FILE: {path} ---"

# Pre-compiled patterns used by the streaming parser.
_RE_BEGIN = re.compile(r"^# --- BEGIN FILE: (.*) ---$")
_RE_END   = re.compile(r"^# --- END FILE: (.*) ---$")
_RE_SEP   = re.compile(r"^# =+$")


class _ContextFile(NamedTuple):
    """Immutable record of one in-memory file extracted from a pack."""
    path: str       
    content: str    


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pack_to_text_bins(
    source_dir: str | Path,
    output_prefix: str = "corpus_pack",
    num_bins: int = 5,
    glob_pattern: str = "*.py",
    exclude_dirs: Sequence[str] | None = None
) -> int:
    """Serialize a directory of source files into balanced text files.
    
    Returns the total number of files packed.
    """
    root = _resolved_dir(source_dir)
    exclude_set = frozenset(exclude_dirs or []) | _DEFAULT_IGNORE_DIRS

    # --- 1. Lazy Discovery & I/O Optimization ----------------------------------
    candidate_generator = (
        p for p in root.rglob(glob_pattern)
        if p.is_file() and exclude_set.isdisjoint(p.parts)
    )
    
    file_records = [(p, p.stat().st_size) for p in candidate_generator]
    
    if not file_records:
        logger.warning(f"No files matching '{glob_pattern}' found in '{root}'.")
        return 0

    # --- 2. Greedy bin-packing -------------------------------------------------
    file_records.sort(key=lambda x: x[1], reverse=True) # Largest first
    
    bins: list[list[Path]] = [[] for _ in range(num_bins)]
    bin_sizes: list[int]   = [0] * num_bins

    for fp, size in file_records:
        idx = bin_sizes.index(min(bin_sizes))   
        bins[idx].append(fp)
        bin_sizes[idx] += size

    # --- 3. Write non-empty bins to disk ---------------------------------------
    total_packed = 0
    for idx, (bin_files, byte_count) in enumerate(zip(bins, bin_sizes)):
        if not bin_files:
            continue
        out_path = Path(f"{output_prefix}_{idx + 1}.txt")
        _write_pack_file(out_path, bin_files, root)
        
        logger.info(f"✓ {out_path.name:<20} ({len(bin_files):>3} files, {byte_count / 1024:>6.1f} KB)")
        total_packed += len(bin_files)
        
    return total_packed


def unpack_text_bins(
    source_dir: str | Path = ".",
    output_dir: str | Path = ".",
    pack_glob: str = "corpus_pack_*.txt",
) -> int:
    """Reconstruct the original file tree from pack text files.
    
    Returns the total number of files restored.
    """
    src = _resolved_dir(source_dir)
    dst = Path(output_dir).resolve()

    pack_files = sorted(src.glob(pack_glob))
    if not pack_files:
        logger.warning(f"No files matching '{pack_glob}' found in '{src}'.")
        return 0

    logger.info(f"Found {len(pack_files)} pack file(s). Reconstructing into '{dst}' …\n")
    total_restored = 0
    
    for pack_file in pack_files:
        logger.info(f"  Processing {pack_file.name}")
        with pack_file.open("r", encoding="utf-8") as fh:
            total_restored += _restore_files_from_stream(fh, dst)

    logger.info("\nUnpacking complete.")
    return total_restored


# ---------------------------------------------------------------------------
# Private helpers – Group 2
# ---------------------------------------------------------------------------

def _write_pack_file(out_path: Path, files: list[Path], root: Path) -> None:
    """Write *files* into a single formatted pack file at *out_path*."""
    with out_path.open("w", encoding="utf-8") as fh:
        for fp in files:
            rel = fp.relative_to(root).as_posix() 

            fh.write(f"\n{_SEPARATOR}\n")
            fh.write(f"{_BEGIN_MARKER.format(path=rel)}\n")
            fh.write(f"{_SEPARATOR}\n\n")

            try:
                fh.write(fp.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                fh.write("# [SKIPPED: binary or non-UTF-8 content]\n")

            fh.write(f"\n\n{_END_MARKER.format(path=rel)}\n")


def _restore_files_from_stream(stream: Iterable[str], target_dir: Path) -> int:
    """Write every ContextFile to disk, guarding against directory traversal."""
    restored_count = 0
    for ctx in _parse_pack_stream(stream):
        out = (target_dir / ctx.path).resolve()

        if not out.is_relative_to(target_dir):
            logger.warning(f"  ⚠  Traversal blocked: {ctx.path!r}")
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(ctx.content, encoding="utf-8")
        logger.debug(f"    ↳ Restored: {ctx.path}")
        restored_count += 1
        
    return restored_count


def _parse_pack_stream(line_stream: Iterable[str]) -> Iterator[_ContextFile]:
    """Generator: parse a pack-file line stream and yield one _ContextFile per file."""
    current_path: str | None = None
    current_lines: list[str] = []

    for raw_line in line_stream:
        line = raw_line.strip()

        if m := _RE_BEGIN.match(line):
            current_path = m.group(1).strip()
            current_lines = []
            continue

        if _RE_END.match(line):
            if current_path is not None:
                yield _ContextFile(
                    path=current_path,
                    content=_strip_pack_framing(current_lines),
                )
                current_path = None
            continue

        if current_path is not None:
            current_lines.append(raw_line)   


def _strip_pack_framing(lines: list[str]) -> str:
    """Remove the packer's separator and blank lines from the head and tail."""
    while lines and (_RE_SEP.match(lines[0].strip()) or not lines[0].strip()):
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "".join(lines)


# =============================================================================
# SHARED PRIVATE UTILITIES
# =============================================================================

def _resolved_dir(path: str | Path) -> Path:
    p = Path(path).resolve()
    if not p.is_dir():
        raise NotADirectoryError(f"Directory not found: {p}")
    return p


def _compile_regex(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regular expression {pattern!r}: {exc}") from exc


# =============================================================================
# CLI
# =============================================================================

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="filepack",
        description="Archive and LLM-packing toolkit for codebase files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    # Global options
    parser.add_argument("-v", "--verbose", action="store_true", 
                        help="Enable verbose output.")
    
    sub = parser.add_subparsers(dest="command", required=True)

    # -- zip ------------------------------------------------------------------
    p_zip = sub.add_parser("zip", help="Zip files matching a glob and regex pattern.")
    p_zip.add_argument("glob", help="Glob pattern to find files (e.g., '**/*.py').") 
    p_zip.add_argument("regex",  help="Regex matched against filenames (re.search).")
    p_zip.add_argument("-o", "--output", default="archive.zip",
                       help="Output ZIP file path.")
                       
    # -- pack -----------------------------------------------------------------
    p_pack = sub.add_parser("pack", help="Pack source files into balanced text bins.")
    p_pack.add_argument("source", help="Root directory to pack.")
    p_pack.add_argument("-p", "--pattern", default="*.py",
                        help="rglob pattern selecting files to include.")
    p_pack.add_argument("-b", "--bins", type=int, default=5,
                        help="Number of output text files.")
    p_pack.add_argument("--prefix", default="corpus_pack",
                        help="Filename prefix for output text files.")
    p_pack.add_argument("-x", "--exclude", nargs="*", default=[],
                        help="Additional directory names to ignore.")

    # -- unpack ---------------------------------------------------------------
    p_unpack = sub.add_parser("unpack", help="Reconstruct files from text bins.")
    p_unpack.add_argument("-s", "--source", default=".",
                          help="Directory containing pack .txt files.")
    p_unpack.add_argument("-d", "--dest", default=".",
                          help="Destination directory for reconstructed files.")
    p_unpack.add_argument("-g", "--glob", default="corpus_pack_*.txt",
                          help="Glob pattern to locate pack files.")

    return parser


def _main() -> int:
    """Entry point: parse CLI arguments and dispatch to the appropriate function."""
    args = _build_parser().parse_args()

    # Configure Loguru
    logger.remove()  # Remove standard handler
    if args.verbose:
        # Full details for debugging
        logger.add(sys.stderr, level="DEBUG")
    else:
        # Clean, colored output for standard CLI usage
        logger.add(sys.stderr, format="<level>{message}</level>", level="INFO")

    try:
        if args.command == "zip":
            count = zip_by_regex(
                glob_pattern=args.glob,
                regex_pattern=args.regex,
                output_zip=args.output,
            )
            logger.info(f"\nDone: {count} file(s) archived → {args.output}")

        elif args.command == "pack":
            count = pack_to_text_bins(
                args.source,
                output_prefix=args.prefix,
                num_bins=args.bins,
                glob_pattern=args.pattern,
                exclude_dirs=args.exclude,
            )
            logger.info(f"\nDone: {count} file(s) packed into {args.bins} bin(s).")

        elif args.command == "unpack":
            count = unpack_text_bins(
                source_dir=args.source,
                output_dir=args.dest,
                pack_glob=args.glob,
            )
            logger.info(f"\nDone: {count} file(s) successfully reconstructed.")
            
        return 0

    except KeyboardInterrupt:
        logger.error("\nOperation cancelled by user.")
        return 130
    except Exception as e:
        logger.exception("\nAn unexpected error occurred.")
        return 1


if __name__ == "__main__":
    sys.exit(_main())