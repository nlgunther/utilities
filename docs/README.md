# packtools

A collection of personal CLI utilities for file comparison, codebase
archiving, directory tree viewing, bulk deletion, and manifest-based file
integrity checking.  All tools install into your conda environment via a
single `pip install -e .` and are available from any directory.

---

## Installation

```
cd utilities
pip install -e .
```

To verify the install:

```
verify-install
```

---

## Tools

### compare-folders

Compare two directory trees file by file.  Walks both trees recursively,
computes a hash for every file, and produces a table showing MATCH,
NO_MATCH, PRESENT_A, or PRESENT_B for every file in the union of both sets.
Optionally filters by filename regexp and writes the table to a file.

```
compare-folders <dir_a> <dir_b> [--filter REGEXP] [--output FILE]
```

### filepack / flpk

Codebase archiving and LLM-context toolkit with three subcommands:

- `zip` — archive matched files into a ZIP, preserving directory structure
- `flatten` — copy matched files into a single flat directory and write a
  `directory_map.txt` showing the original structure
- `pack` — serialise matched files into N balanced text bins for LLM ingestion

```
filepack zip     <path> <regex> [-o OUTPUT]
filepack flatten <path> <regex> -o OUTPUT_DIR
filepack pack    <path> [regex] [-b BINS] [--prefix PREFIX]
filepack -v ...
```

`flpk` is a short alias for `filepack`.

### filtered-tree

Print a regex-filtered ASCII directory tree.  Only files whose names match
the pattern are shown, along with the ancestor directories needed to show
their location.  Empty directories are omitted.

```
filtered-tree <directory> <regex> [--out FILE]
```

### delete-pattern

Recursively delete all files and folders under a directory matching a glob
pattern.  Deletes deepest matches first so child items are removed before
their parents.  Use `--dry-run` to preview without deleting.

```
delete-pattern <pattern> [--directory DIR] [--dry-run]
```

### manifest-check

Compare `MANIFEST.txt` hashes against the current state of files on disk.
Prints a side-by-side table (MANIFEST hash vs current hash, status OK /
CHANGED / MISSING) and writes `MANIFEST_current.txt` to the project root.

```
manifest-check [project_root]     # default: current directory
```

### verify-install

Lightweight file integrity checker.  Reads `MANIFEST.txt` and verifies each
tracked file against its recorded hash, then checks the overall bundle hash.
Exits with code 1 if any file is missing or changed.

```
verify-install [--manifest PATH]  # default: ./MANIFEST.txt
```

### generate-manifest

Regenerate `MANIFEST.txt` from scratch by hashing all files listed in the
`FILES` constant.  Run this after any edit, addition, or removal of tracked
files.  Warns on missing files rather than silently skipping them.

```
generate-manifest                 # always run from utilities/ root
```

---

## Package structure

```
utilities/
├── pyproject.toml
├── MANIFEST.txt
├── generate_manifest.py          (also registered as generate-manifest)
├── packtools/
│   ├── __init__.py
│   ├── _hashing.py               shared sha16 + bundle_hash
│   ├── dir_compare.py            compare-folders
│   ├── filepack.py               filepack / flpk
│   ├── filtered_tree.py          filtered-tree  (build_tree shared with filepack)
│   ├── delete_pattern.py         delete-pattern
│   ├── manifest_check.py         manifest-check
│   └── verify_install.py         verify-install
└── tests/
    └── test_packtools.py
```

---

## Hashing convention

All file hashes are computed after normalising line endings to CRLF before
hashing.  This ensures that a file produced on Linux (LF) and the same file
on Windows (CRLF) produce identical hashes.  The bundle hash is a
hash-of-hashes: sort all tracked paths lexicographically, concatenate their
16-char SHA-256 prefixes, SHA-256 the result, take 24 chars.

---

## Running tests

```
pytest tests\ -q
```

---

## Adding a new tracked file

1. Add the path to `FILES` in `packtools/generate_manifest.py`
2. Run `generate-manifest`
3. Run `verify-install` to confirm
