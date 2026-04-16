# packtools Cheatsheet

## compare-folders

```
# Basic comparison
compare-folders src backup

# Filter to Python files only
compare-folders src backup --filter "\.py$"

# Write table to file (also prints to console)
compare-folders src backup --filter "\.py$" --output diff.txt
```

Status codes: `MATCH` `NO_MATCH` `PRESENT_A` `PRESENT_B`

---

## filepack / flpk

```
# Archive all .py files to a zip
filepack zip . "\.py$" -o archive.zip
filepack zip src "\.py$" -o src.zip

# Flatten matched files into a single directory
filepack flatten . "\.py$" -o flat/
filepack flatten src "\.(py|md)$" -o flat/

# Pack into 1 text bin (default)
filepack pack . "\.py$"

# Pack into 3 balanced bins with custom prefix
filepack pack . "\.py$" -b 3 --prefix ctx

# Enable debug logging
filepack -v pack . "\.py$"
```

Collision handling in flatten: `module/main.py` → `module_main.py`
Output bins: `corpus_pack_1.txt`, `corpus_pack_2.txt`, ...

---

## filtered-tree

```
# Print tree of all .py files
filtered-tree . "\.py$"

# Filter to test files only
filtered-tree src "test_.*\.py$"

# Write to file
filtered-tree . "\.py$" --out tree.txt
```

Always omits: `.git` `__pycache__` `.venv` `.pytest_cache` `node_modules`

---

## delete-pattern

```
# Preview what would be deleted
delete-pattern "*.pyc" --dry-run
delete-pattern "__pycache__" --dry-run

# Delete from current directory
delete-pattern "*.pyc"
delete-pattern "*.tmp"

# Delete from a specific directory
delete-pattern "*.log" --directory C:\logs

# Delete folders matching a pattern
delete-pattern "__pycache__"
delete-pattern "*.egg-info"
```

Deepest matches deleted first — safe for nested directories.

---

## manifest-check

```
# Check current directory
manifest-check

# Check a specific project
manifest-check C:\path\to\project
manifest-check ..\other_project
```

Writes `MANIFEST_current.txt` alongside `MANIFEST.txt`.
Status codes: `OK` `CHANGED` `MISSING`

---

## verify-install

```
# Check ./MANIFEST.txt
verify-install

# Check a specific manifest
verify-install --manifest path\to\MANIFEST.txt
verify-install -m ..\other\MANIFEST.txt
```

Exits 0 if all OK, exits 1 if anything is missing or changed.

---

## generate-manifest

```
# Always run from the utilities/ root
cd C:\path\to\utilities
generate-manifest
```

Edit `FILES` in `packtools/generate_manifest.py` to add or remove tracked files.
Edit `PACKAGE` to change the manifest header when reusing for another project.

---

## Integrity workflow

```
# After any code change:
generate-manifest        # recompute hashes → writes MANIFEST.txt
verify-install           # confirm all files match

# To check a project without regenerating:
manifest-check           # detailed side-by-side table
verify-install           # pass/fail summary
```

---

## Tests

```
pytest tests\ -q
```

---

## pip install / reinstall

```
# From utilities\ root
pip install -e .

# After editing pyproject.toml (new entry points):
pip install -e .         # re-registers console scripts
```
