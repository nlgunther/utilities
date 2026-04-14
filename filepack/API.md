# filepack — API Reference

## Contents

1. [Module Overview](#1-module-overview)
2. [Architecture](#2-architecture)
3. [Group 1 — Archive API](#3-group-1--archive-api)
   - [zip_by_regex](#zip_by_regex)
   - [extract_zip](#extract_zip)
4. [Group 2 — Context Pack API](#4-group-2--context-pack-api)
   - [pack_to_text_bins](#pack_to_text_bins)
   - [unpack_text_bins](#unpack_text_bins)
5. [Pack File Format Specification](#5-pack-file-format-specification)
6. [Module-Level Constants](#6-module-level-constants)
7. [Private Internals](#7-private-internals)
   - [_write_pack_file](#_write_pack_file)
   - [_restore_files_from_stream](#_restore_files_from_stream)
   - [_parse_pack_stream](#_parse_pack_stream)
   - [_strip_pack_framing](#_strip_pack_framing)
   - [_resolved_dir](#_resolved_dir)
   - [_compile_regex](#_compile_regex)
8. [CLI Reference](#8-cli-reference)
9. [Design Notes & Extension Points](#9-design-notes--extension-points)
10. [Error Reference](#10-error-reference)

---

## 1. Module Overview

`filepack.py` is a single-file, stdlib-only Python module containing two fully
independent groups of functionality:

| Group                  | Purpose                                                                                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **Archive Tools**      | Recursively zip a directory tree, selecting files by regular expression; extract ZIP archives.                                               |
| **Context Pack Tools** | Serialize a source tree into N size-balanced text files (for LLM context windows); reconstruct the originals verbatim from those text files. |

**Requirements:** Python 3.10+, standard library only.

**Import:**

```python
# Import specific functions
from filepack import zip_by_regex, extract_zip
from corpfilepackort pack_to_text_bins, unpack_text_bins

# Or import the whole module
import corpus_tfilepack
```

---

## 2. Architecture

```
filepack.py
│
├── GROUP 1 – Archive Operations
│   ├── zip_by_regex()         ← public
│   └── extract_zip()          ← public
│
├── GROUP 2 – Context Pack Operations
│   ├── pack_to_text_bins()    ← public
│   ├── unpack_text_bins()     ← public
│   ├── _write_pack_file()     ← private helper (writing)
│   ├── _restore_files_from_stream()  ← private helper (reading)
│   ├── _parse_pack_stream()   ← private generator (parsing)
│   └── _strip_pack_framing()  ← private helper (cleanup)
│
├── SHARED PRIVATE UTILITIES
│   ├── _resolved_dir()        ← validates + resolves Path
│   └── _compile_regex()       ← validates + compiles regex
│
└── CLI
    ├── _build_parser()        ← constructs ArgumentParser
    └── _main()                ← dispatches to public API
```

The two groups are **fully decoupled**: they share no module-level state, no mutable
globals, and only the two shared utility functions (`_resolved_dir`, `_compile_regex`).
Either group can be extracted into its own module with only those two helpers.

**Data flow — packing:**

```
source_dir
  └─rglob(glob_pattern)──► [Path, …] ──sort by size──► greedy bin-pack
                                                              │
                                         ┌────────────────────┤
                                         ▼                    ▼
                                  corpus_pack_1.txt   corpus_pack_2.txt …
```

**Data flow — unpacking:**

```
corpus_pack_*.txt
  └─open()──► line stream ──► _parse_pack_stream() ──► _ContextFile generator
                                                              │
                                              ┌───────────────┘
                                              ▼
                               traversal check ──► write to output_dir/path
```

---

## 3. Group 1 — Archive API

### `zip_by_regex`

```python
zip_by_regex(
    source_dir: str | Path,
    output_zip: str | Path,
    regex_pattern: str,
) -> int
```

Recursively scans `source_dir` and writes all files whose **filename** matches
`regex_pattern` into a deflate-compressed ZIP archive at `output_zip`.

The archive preserves the directory structure relative to `source_dir`, so that
`extract_zip` restores the original layout without any path manipulation.

**Parameters**

| Name            | Type          | Description                                                                                                        |
| --------------- | ------------- | ------------------------------------------------------------------------------------------------------------------ |
| `source_dir`    | `str \| Path` | Root directory to scan recursively. Must exist and be a directory.                                                 |
| `output_zip`    | `str \| Path` | Destination `.zip` file. Parent directories are created automatically if absent.                                   |
| `regex_pattern` | `str`         | Regular expression applied to each file's **name only** (not its full path) via `re.search`. Need not be anchored. |

**Returns**

`int` — the number of files written to the archive. Returns `0` if the pattern
matches nothing (the archive is still created but is empty).

**Raises**

| Exception            | Condition                                                    |
| -------------------- | ------------------------------------------------------------ |
| `NotADirectoryError` | `source_dir` does not exist or is not a directory.           |
| `ValueError`         | `regex_pattern` is not a valid regular expression.           |
| `zipfile.BadZipFile` | (from stdlib) if `output_zip` already exists and is corrupt. |

**Behavior details**

- Files are walked with `Path.rglob("*")` and sorted alphabetically before being
  written, ensuring a **deterministic archive order** across all platforms.
- Matching uses `re.search`, not `re.fullmatch`, so partial matches are accepted.
  To require a full-name match, anchor your pattern with `^` and `$`.
- Compression is `ZIP_DEFLATED` (standard zlib). There is no option for
  `ZIP_STORED`; add one if needed (see §9).

**Example**

```python
from filepack import zip_by_regex

# Archive all Python and Markdown files
n = zip_by_regex(
    source_dir    = "myproject/",
    output_zip    = "releases/v2.0.zip",
    regex_pattern = r"\.(py|md)$",
)
print(f"Archived {n} files.")   # e.g. "Archived 42 files."

# Archive only test modules (anchored pattern)
zip_by_regex("myproject/", "tests.zip", r"^test_.*\.py$")
```

**Console output**

```
Scanning 'myproject' for files matching r'\.(py|md)$' …
  + pkg/__init__.py
  + pkg/core.py
  + README.md
  …
```

---

### `extract_zip`

```python
extract_zip(
    zip_path: str | Path,
    target_dir: str | Path,
) -> None
```

Extracts all members of a ZIP archive into `target_dir`.

**Parameters**

| Name         | Type          | Description                                                                                    |
| ------------ | ------------- | ---------------------------------------------------------------------------------------------- |
| `zip_path`   | `str \| Path` | Path to the source `.zip` file.                                                                |
| `target_dir` | `str \| Path` | Directory into which all archive members are extracted. Created (including parents) if absent. |

**Returns** `None`

**Raises**

| Exception            | Condition                           |
| -------------------- | ----------------------------------- |
| `FileNotFoundError`  | `zip_path` does not exist.          |
| `zipfile.BadZipFile` | `zip_path` is not a valid ZIP file. |

> **Security note:** This function delegates to `zipfile.ZipFile.extractall`, which
> does **not** perform directory-traversal checks. Only extract archives from trusted
> sources. For untrusted archives, inspect member names before extracting.

**Example**

```python
from filepack import extract_zip

extract_zip("releases/v2.0.zip", "restored_project/")
```

---

## 4. Group 2 — Context Pack API

### `pack_to_text_bins`

```python
pack_to_text_bins(
    source_dir: str | Path,
    output_prefix: str = "corpus_pack",
    num_bins: int = 5,
    glob_pattern: str = "*.py",
) -> None
```

Collects files from `source_dir` matching `glob_pattern`, distributes them into
`num_bins` size-balanced groups using a **greedy bin-packing algorithm**, and writes
each group to a formatted text file named `<output_prefix>_<n>.txt`.

The resulting `.txt` files are self-describing: each embedded file is wrapped in
structured delimiter markers (see §5) that allow `unpack_text_bins` to reconstruct
the originals verbatim.

**Parameters**

| Name            | Type          | Default         | Description                                                                                                                                                  |
| --------------- | ------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `source_dir`    | `str \| Path` | *(required)*    | Root of the directory tree to pack. Must exist and be a directory.                                                                                           |
| `output_prefix` | `str`         | `"corpus_pack"` | Filename stem for output files. File `n` is named `<prefix>_<n>.txt` (1-indexed).                                                                            |
| `num_bins`      | `int`         | `5`             | Maximum number of output text files. Empty bins (when fewer files exist than bins) are silently skipped, so the actual number of output files may be less.   |
| `glob_pattern`  | `str`         | `"*.py"`        | `Path.rglob` pattern used to select files. Use `"**/*.py"` to match files at any depth, or `"*.{py,md}"` for multiple extensions (Python 3.12+ glob syntax). |

**Returns** `None`

**Raises**

| Exception            | Condition                                          |
| -------------------- | -------------------------------------------------- |
| `NotADirectoryError` | `source_dir` does not exist or is not a directory. |

**Algorithm — greedy bin-packing**

1. All matching files are collected and sorted **largest-first** by byte size.
2. Each file is assigned to whichever bin currently has the smallest total byte
   count (a standard "longest processing time" greedy heuristic).
3. This produces near-optimal balance without any backtracking.

The algorithm is O(F log B) where F is the number of files and B is `num_bins`.

**Excluded directories**

The following directory names are excluded from globbing at every nesting depth:

```
__pycache__,  .pytest_cache,  .git,  .venv,  env,  .mypy_cache
```

(See `_IGNORE_DIRS` in §6 to add or remove entries.)

**Binary files**

If a file cannot be decoded as UTF-8, it is replaced with a single-line comment:

```
# [SKIPPED: binary or non-UTF-8 content]
```

The surrounding `BEGIN`/`END` markers remain intact so the parser does not lose sync.

**Example**

```python
from filepack import pack_to_text_bins

# Basic: pack all Python files from myproject/ into 5 bins
pack_to_text_bins("myproject/")
# → corpus_pack_1.txt, corpus_pack_2.txt, …, corpus_pack_5.txt

# Custom: 3 bins, custom prefix, include all Python files recursively
pack_to_text_bins(
    source_dir    = "myproject/",
    output_prefix = "context",
    num_bins      = 3,
    glob_pattern  = "**/*.py",
)
# → context_1.txt, context_2.txt, context_3.txt
```

**Console output**

```
✓  corpus_pack_1.txt  (12 files, ~48.3 KB)
✓  corpus_pack_2.txt  (11 files, ~47.9 KB)
✓  corpus_pack_3.txt  (10 files, ~46.1 KB)
```

---

### `unpack_text_bins`

```python
unpack_text_bins(
    source_dir: str | Path = ".",
    output_dir: str | Path = ".",
    pack_glob: str = "corpus_pack_*.txt",
) -> None
```

Discovers pack files in `source_dir` matching `pack_glob`, parses each one with a
streaming generator, and writes the recovered files under `output_dir`, recreating
the original directory hierarchy.

**Parameters**

| Name         | Type          | Default               | Description                                                                                                                 |
| ------------ | ------------- | --------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `source_dir` | `str \| Path` | `"."`                 | Directory containing the pack `.txt` files. Must exist.                                                                     |
| `output_dir` | `str \| Path` | `"."`                 | Root directory under which the original tree is recreated. Created automatically if absent.                                 |
| `pack_glob`  | `str`         | `"corpus_pack_*.txt"` | Glob pattern used to discover pack files within `source_dir`. Useful when a non-default `--prefix` was used during packing. |

**Returns** `None`

**Raises**

| Exception            | Condition                                          |
| -------------------- | -------------------------------------------------- |
| `NotADirectoryError` | `source_dir` does not exist or is not a directory. |

**Security — directory-traversal guard**

Every recovered path is resolved with `Path.resolve()` and asserted to be
`relative_to(output_dir)`. Any path containing `..` sequences that would escape
`output_dir` is **blocked and logged** rather than written:

```
⚠  Traversal blocked: '../../etc/passwd'
```

**Memory model**

Pack files are processed one line at a time through a generator pipeline
(`_parse_pack_stream`). At any moment, only the lines of the *current file being
parsed* are held in memory. This makes `unpack_text_bins` safe to use on very large
pack files.

**Example**

```python
from filepack import unpack_text_bins

# Default: unpack corpus_pack_*.txt from current dir into current dir
unpack_text_bins()

# Custom: unpack from packs/ into restored/, with a non-default prefix
unpack_text_bins(
    source_dir = "packs/",
    output_dir = "restored/",
    pack_glob  = "context_*.txt",
)
```

**Console output**

```
Found 3 pack file(s). Reconstructing into '/home/ken/restored' …

  Processing corpus_pack_1.txt
    ↳ Restored: pkg/__init__.py
    ↳ Restored: pkg/core.py
    …
  Processing corpus_pack_2.txt
    ↳ Restored: pkg/utils.py
    …

Unpacking complete.
```

---

## 5. Pack File Format Specification

This section defines the text format written by `_write_pack_file` and consumed by
`_parse_pack_stream`. Understanding it is useful if you want to generate pack files
from another tool or parse them outside Python.

### Structure of one file entry

```
\n
# ===========================================================================\n
# --- BEGIN FILE: <relative/forward/slash/path.py> ---\n
# ===========================================================================\n
\n
<verbatim UTF-8 file content>\n
\n
\n
# --- END FILE: <relative/forward/slash/path.py> ---\n
```

- The separator is the literal string `# ` followed by exactly 75 `=` characters.
- Paths always use **forward slashes** regardless of the host OS.
- The path in `BEGIN` and `END` markers is identical and is the POSIX-relative path
  from the original `source_dir`.
- Content is written verbatim; no escaping is applied.
- Two blank lines separate the content from the `END` marker.

### Full example (two files)

```
# ===========================================================================
# --- BEGIN FILE: pkg/__init__.py ---
# ===========================================================================

# package init

# --- END FILE: pkg/__init__.py ---

# ===========================================================================
# --- BEGIN FILE: pkg/core.py ---
# ===========================================================================

def add(a, b):
    return a + b

# --- END FILE: pkg/core.py ---
```

### Parser state machine

The streaming parser `_parse_pack_stream` implements a two-state machine:

```
        ┌──────────┐   BEGIN marker    ┌─────────┐
  ───►  │ OUTSIDE  │ ────────────────► │  INSIDE │
        │          │ ◄──────────────── │         │
        └──────────┘    END marker     └─────────┘
                       (yields record)
```

Lines outside any `BEGIN`/`END` block are ignored, making the format tolerant of
arbitrary header text or inter-file commentary.

---

## 6. Module-Level Constants

All constants are module-private (prefixed `_`). They are documented here because
changing them affects both the writer and the parser simultaneously.

| Constant        | Type             | Value                                                                     | Purpose                                                |
| --------------- | ---------------- | ------------------------------------------------------------------------- | ------------------------------------------------------ |
| `_IGNORE_DIRS`  | `frozenset[str]` | `{"__pycache__", ".pytest_cache", ".git", ".venv", "env", ".mypy_cache"}` | Directory names excluded from packing at every depth.  |
| `_SEPARATOR`    | `str`            | `"# " + "=" * 75`                                                         | Visual separator line written around `BEGIN` markers.  |
| `_BEGIN_MARKER` | `str`            | `"# --- BEGIN FILE: {path} ---"`                                          | Format string for the opening delimiter.               |
| `_END_MARKER`   | `str`            | `"# --- END FILE: {path} ---"`                                            | Format string for the closing delimiter.               |
| `_RE_BEGIN`     | `re.Pattern`     | Matches `_BEGIN_MARKER` lines, capturing the path.                        | Used by the streaming parser.                          |
| `_RE_END`       | `re.Pattern`     | Matches `_END_MARKER` lines.                                              | Used by the streaming parser.                          |
| `_RE_SEP`       | `re.Pattern`     | Matches separator lines (`# =+`).                                         | Used by `_strip_pack_framing` to drop leading framing. |

> **To add an ignored directory:** Edit `_IGNORE_DIRS`. Both packing and the exclusion
> check in `pack_to_text_bins` automatically pick up the change.
> 
> **To change the delimiter format:** Edit `_BEGIN_MARKER` / `_END_MARKER` **and**
> `_RE_BEGIN` / `_RE_END` together. They must remain consistent.

---

## 7. Private Internals

These functions are not part of the public API but are documented for contributors
and for users who want to embed the parser pipeline in their own code.

---

### `_write_pack_file`

```python
_write_pack_file(
    out_path: Path,
    files: list[Path],
    root: Path,
) -> None
```

Writes `files` into a single pack text file at `out_path` using the format defined
in §5. Non-UTF-8 files are replaced with a placeholder comment. Paths are always
written as POSIX (forward-slash) strings relative to `root`.

---

### `_restore_files_from_stream`

```python
_restore_files_from_stream(
    stream: Iterable[str],
    target_dir: Path,
) -> None
```

Consumes the generator produced by `_parse_pack_stream`, applies the
directory-traversal guard to each recovered path, creates parent directories as
needed, and writes the file content to disk.

---

### `_parse_pack_stream`

```python
_parse_pack_stream(
    line_stream: Iterable[str],
) -> Iterator[_ContextFile]
```

**Generator.** Accepts any iterable of strings (typically an open file handle) and
yields one `_ContextFile(path, content)` named tuple per embedded file.

The generator is **lazy**: it accumulates only the lines of the current file being
parsed. This makes it suitable for streaming very large pack files without loading
them into memory.

Can be used independently to inspect a pack file in Python:

```python
with open("corpus_pack_1.txt") as fh:
    for ctx in _parse_pack_stream(fh):
        print(ctx.path, f"({len(ctx.content)} chars)")
```

---

### `_strip_pack_framing`

```python
_strip_pack_framing(lines: list[str]) -> str
```

Removes the leading separator line and blank lines added by the packer, and strips
trailing blank lines, then joins the remaining lines into a single string. This
ensures the reconstructed content is byte-for-byte identical to the original.

---

### `_resolved_dir`

```python
_resolved_dir(path: str | Path) -> Path
```

Resolves `path` to an absolute `Path` and raises `NotADirectoryError` if it does
not exist or is not a directory. Used at the entry point of every public function
that accepts a source directory.

---

### `_compile_regex`

```python
_compile_regex(pattern: str) -> re.Pattern[str]
```

Compiles `pattern` and converts any `re.error` into a `ValueError` with a clear
message including the invalid pattern. Used by `zip_by_regex`.

---

## 8. CLI Reference

The module is directly executable:

```bash
python filepack.py <command> [options]
```

### `zip` — regex archive

```
python filepack.py zip <source> <regex> [-o OUTPUT]

positional arguments:
  source          Root directory to scan recursively.
  regex           Regular expression matched against filenames (re.search).

optional arguments:
  -o, --output    Output ZIP file path.  [default: archive.zip]
```

### `pack` — serialize to text bins

```
python filepack.py pack <source> [-p PATTERN] [-b BINS] [--prefix PREFIX]

positional arguments:
  source            Root directory to pack.

optional arguments:
  -p, --pattern     rglob pattern selecting files to include.  [default: *.py]
  -b, --bins        Number of output text files.               [default: 5]
  --prefix          Filename prefix for output text files.     [default: corpus_pack]
```

### `unpack` — reconstruct from text bins

```
python filepack.py unpack [-s SOURCE] [-d DEST] [-g GLOB]

optional arguments:
  -s, --source    Directory containing pack .txt files.        [default: .]
  -d, --dest      Destination directory for reconstructed files. [default: .]
  -g, --glob      Glob pattern to locate pack files.           [default: corpus_pack_*.txt]
```

All subcommands display `--help` via:

```bash
python filepack.py <command> --help
```

---

## 9. Design Notes & Extension Points

### Adding a new compression method to `zip_by_regex`

Add a `compression` parameter with a default:

```python
def zip_by_regex(
    source_dir: str | Path,
    output_zip: str | Path,
    regex_pattern: str,
    compression: int = zipfile.ZIP_DEFLATED,   # ← new
) -> int:
    ...
    with zipfile.ZipFile(zip_path, "w", compression) as zf:
```

### Matching on full path instead of filename

Change `pattern.search(filepath.name)` to `pattern.search(str(rel))` in
`zip_by_regex` to match against the relative path (e.g. to filter by directory
name as well as filename).

### Adding a new excluded directory

Edit `_IGNORE_DIRS` at the top of the Context Pack section:

```python
_IGNORE_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".pytest_cache", ".git", ".venv", "env", ".mypy_cache",
    "node_modules",   # ← add here
})
```

### Parsing pack files in a non-Python environment

The format (§5) is plain text with no binary encoding and no escaping. A
POSIX shell script can extract a single file by scanning for `BEGIN FILE` /
`END FILE` lines with `awk` or `sed`.

### Making `zip_by_regex` return a list of archived paths

Change the return type from `int` to `list[Path]`:

```python
archived: list[Path] = []
...
if filepath.is_file() and pattern.search(filepath.name):
    zf.write(filepath, arcname=str(rel))
    archived.append(rel)
return archived
```

---

## 10. Error Reference

| Exception              | Raised by                    | Condition                                                                                                                    |
| ---------------------- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `NotADirectoryError`   | `_resolved_dir`              | Any public function whose first argument is a directory path, when that path does not exist or is a file.                    |
| `ValueError`           | `_compile_regex`             | `regex_pattern` argument to `zip_by_regex` is syntactically invalid.                                                         |
| `FileNotFoundError`    | `extract_zip` (stdlib)       | `zip_path` does not exist.                                                                                                   |
| `zipfile.BadZipFile`   | `extract_zip` (stdlib)       | `zip_path` is not a valid ZIP file.                                                                                          |
| *(logged, not raised)* | `_restore_files_from_stream` | A recovered path attempts to escape `output_dir` (directory-traversal). The offending file is skipped; processing continues. |
| *(logged, not raised)* | `_write_pack_file`           | A source file cannot be decoded as UTF-8. A placeholder comment is written; processing continues.                            |
