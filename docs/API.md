# packtools API Reference

All public functions are importable from their respective modules.  Internal
helpers are prefixed with `_` and should not be called directly.

---

## packtools._hashing

Shared hashing primitives used by all integrity tools.  Import from here
rather than re-implementing in new modules.

---

### `sha16(data: bytes) -> str`

SHA-256 of CRLF-normalised bytes, first 16 hex chars.

Line endings are normalised to CRLF before hashing so that the same logical
file produces the same hash regardless of which OS wrote it.

```python
from packtools._hashing import sha16

sha16(b"hello\n")    # same result as sha16(b"hello\r\n")
# → "a948904f2f0f479b"  (example)
```

---

### `bundle_hash(file_hashes: dict[str, str]) -> str`

Hash-of-hashes: sort tracked paths lexicographically, concatenate their
`sha16` values, SHA-256 the result, return 24 hex chars.

Cheap regardless of file sizes — the input is at most a few hundred bytes.

```python
from packtools._hashing import bundle_hash

bundle_hash({"a.py": "abc123def456abcd", "b.py": "fed987cba654fedc"})
# → "3f1a9c2e..." (24-char hex string)
```

---

## packtools.dir_compare

---

### `collect_files(root: str, pattern: re.Pattern | None) -> dict[str, str]`

Walk `root` recursively and return `{relative_path: sha16}` for every file
whose name matches `pattern` (or all files if `pattern` is `None`).

Relative paths use forward slashes for cross-platform consistency.
Files that cannot be read are recorded as `"ERROR"`.

```python
from packtools.dir_compare import collect_files
import re

files = collect_files("/path/to/src", re.compile(r"\.py$"))
# → {"main.py": "a1b2c3d4e5f6a1b2", "module/logic.py": "..."}
```

---

### `build_rows(files_a, files_b) -> list[tuple[str, str, str, str]]`

Return a sorted list of `(path, hash_a, hash_b, status)` tuples for the
union of both file sets.

`status` values: `MATCH`, `NO_MATCH`, `PRESENT_A`, `PRESENT_B`.
`hash_a` or `hash_b` is `"ABSENT"` when the file exists only in the other tree.

```python
from packtools.dir_compare import collect_files, build_rows

fa = collect_files("src", None)
fb = collect_files("backup", None)
rows = build_rows(fa, fb)
```

---

### `format_table(rows, label_a: str, label_b: str) -> str`

Render the comparison rows as a fixed-width text table with a summary footer.
Returns a string ending with `\n`.

```python
from packtools.dir_compare import format_table
table = format_table(rows, "src", "backup")
print(table)
```

---

### `main() -> None`

CLI entry point registered as `compare-folders`.

---

## packtools.filtered_tree

---

### `IGNORED_DIRS: frozenset[str]`

Directories always skipped when building trees.  Default:
`{".git", "__pycache__", ".venv", ".pytest_cache", "node_modules"}`.

Imported by `filepack` to apply the same ignore list during file discovery.

---

### `build_tree(directory: Path, pattern: re.Pattern, prefix: str = "") -> str`

Recursively build an ASCII tree string of files matching `pattern`.

Directories are included only if they contain at least one matching file
somewhere in their subtree.  Entries are sorted dirs-first, then files,
both alphabetically.  Returns an empty string if no files match.

```python
from packtools.filtered_tree import build_tree
import re
from pathlib import Path

tree = build_tree(Path("src"), re.compile(r"\.py$"))
print(tree)
# ├── main.py
# └── module/
#     └── logic.py
```

---

### `main() -> None`

CLI entry point registered as `filtered-tree`.

---

## packtools.filepack

---

### `get_file_stream(input_path, regex, glob, exclude) -> tuple[Path, Iterator[Path]]`

Resolve base directory and yield files matching glob and regex patterns.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | `str \| Path` | required | Directory or file path |
| `regex` | `str` | `".*"` | Filename regex filter |
| `glob` | `str \| None` | `None` | Glob pattern (default: `**/*`) |
| `exclude` | `Iterable[str]` | `()` | Additional directory names to skip |

Returns `(base, iterator)` where `base` is the resolved root and `iterator`
yields matching `Path` objects.  Directories in `IGNORED_DIRS` are always
excluded.

```python
from packtools.filepack import get_file_stream

base, files = get_file_stream("src", r"\.py$")
for p in files:
    print(p.relative_to(base))
```

---

### `cmd_zip(input_path: str, regex: str, output: str) -> int`

Archive all matched files into a ZIP at `output`, preserving directory
structure relative to the base.  Appends to an existing ZIP.
Returns the number of files archived.

---

### `cmd_flatten(input_path: str, regex: str, output_dir: str) -> int`

Copy matched files into `output_dir` as a flat list and write
`directory_map.txt` showing the original structure.  Name collisions are
resolved by prepending the immediate parent directory name.
Returns the number of files copied.

---

### `cmd_pack(source: str, regex: str, bins: int, prefix: str) -> int`

Serialise matched files into `bins` balanced text files named
`{prefix}_1.txt`, `{prefix}_2.txt`, etc.  Files are distributed across bins
using a greedy algorithm (largest file first) to balance total size.
Each file is wrapped in `BEGIN FILE` / `END FILE` delimiters.
Returns the total number of files packed.

---

### `main() -> None`

CLI entry point registered as `filepack` and `flpk`.

---

## packtools.delete_pattern

---

### `collect_matches(root: Path, pattern: str) -> list[Path]`

Return all paths under `root` matching the glob `pattern`, sorted
deepest-first so child items appear before their parents.

```python
from packtools.delete_pattern import collect_matches
from pathlib import Path

matches = collect_matches(Path("src"), "*.pyc")
```

---

### `delete_matches(matches: list[Path], dry_run: bool) -> None`

Delete (or preview) each path in `matches`.  Skips paths that no longer
exist (e.g. already removed by a parent `rmtree`).  Prints each action.

```python
from packtools.delete_pattern import collect_matches, delete_matches
from pathlib import Path

matches = collect_matches(Path("."), "__pycache__")
delete_matches(matches, dry_run=True)   # preview only
delete_matches(matches, dry_run=False)  # actually delete
```

---

### `main() -> None`

CLI entry point registered as `delete-pattern`.

---

## packtools.manifest_check

---

### `load_manifest(manifest_path: str) -> tuple[str | None, dict[str, str]]`

Parse `MANIFEST.txt` and return `(expected_bundle, {local_path: expected_sha16})`.
Skips blank lines and comment lines (starting with `#`).

---

### `check(root: str) -> None`

Run the full manifest check for the project at `root`.  Reads
`MANIFEST.txt`, hashes all tracked files, prints a comparison table, and
writes `MANIFEST_current.txt`.  Exits with code 1 if any file is missing
or changed.

---

### `main() -> None`

CLI entry point registered as `manifest-check`.

---

## packtools.verify_install

---

### `load_manifest(path: str) -> tuple[str | None, dict[str, str]]`

Parse `MANIFEST.txt` and return `(expected_bundle, {local_path: expected_sha16})`.
Skips blank lines and comment lines.  Exits with code 1 if the file is not found.

---

### `verify(manifest_path: str = "MANIFEST.txt") -> None`

Check all tracked files against their recorded hashes and verify the bundle
hash.  Prints `OK`, `MISMATCH`, or `MISSING` for each file.  Exits with
code 1 if anything is out of date.

```python
from packtools.verify_install import verify

verify()                          # reads ./MANIFEST.txt
verify("path/to/MANIFEST.txt")   # explicit path
```

---

### `main() -> None`

CLI entry point registered as `verify-install`.

---

## packtools.generate_manifest

Not intended for import.  Run as `generate-manifest` from the `utilities/`
root.  Reads `FILES` and `PACKAGE` at module level, hashes every tracked
file, and writes `MANIFEST.txt`.  Warns on missing files rather than
silently skipping them.
