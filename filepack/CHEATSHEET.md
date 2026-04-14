# filepack — Quick Reference Cheatsheet

> **Two independent tool groups in one file.**
> Group 1 zips/unzips directory trees by regex.
> Group 2 serializes a codebase into balanced text files for LLM ingestion, then reassembles them.

---

## Installation / Requirements

```
Python ≥ 3.10   (uses str | Path union types and match := walrus operator)
stdlib only     (re, zipfile, argparse, pathlib, typing)
```

Copy `filepack.py` anywhere on your `PYTHONPATH` or into your project root.

---

## GROUP 1 — Archive Tools (Regex Zip)

### CLI

```bash
# Zip all .py and .md files under myproject/ → archive.zip (default)
python filepack.py zip myproject/ ".*\.(py|md)$"

# Specify a custom output path
python corpfilepackzip myproject/ ".*\.(py|md)$" -o releases/v1.zip

# Zip only test files
python corpus_tfilepackmyproject/ "^test_.*\.py$" -o tests_only.zip

# Extract an archive into a folder (created if absent)
python corpus_toolsfilepackchive.zip restored/
```

> **Matching rule:** `re.search` is applied to the **filename only** (not the full path).
> The pattern does **not** need to be anchored — `\.py$` is equivalent to `.*\.py$`.

### Python API

```python
from filepack import zip_by_regex, extract_zip

# Zip — returns count of archived files
n = zip_by_regex("myproject/", "releases/v1.zip", r".*\.(py|md)$")
print(f"{n} files archived")

# Extract
extract_zip("releases/v1.zip", "restored/")
```

### Common Regex Patterns

| Goal                         | Pattern                      |
| ---------------------------- | ---------------------------- |
| Python source files          | `\.py$`                      |
| Python + Markdown            | `\.(py\|md)$`                |
| Test files only              | `^test_.*\.py$`              |
| Config files                 | `\.(yaml\|yml\|toml\|ini)$`  |
| Any file in a `docs/` folder | *(use glob in pack instead)* |
| Exclude nothing (all files)  | `.*`                         |

---

## GROUP 2 — Context Pack Tools (LLM Packing)

### Concept

```
myproject/              →  corpus_pack_1.txt   (largest files, ~equal KB)
  pkg/big_module.py        corpus_pack_2.txt
  pkg/utils.py             corpus_pack_3.txt
  pkg/sub/helpers.py    ←  greedy bin-packing keeps bins balanced
  tests/test_core.py
```

Each `.txt` file wraps its constituent files between markers:

```
# ===========================================================================
# --- BEGIN FILE: pkg/utils.py ---
# ===========================================================================

<verbatim file content here>

# --- END FILE: pkg/utils.py ---
```

### CLI

```bash
# Pack all .py files from myproject/ into 5 bins (default)
python filepack.py pack myproject/

# Specify bins, glob pattern, and output prefix
python corpfilepackpack myproject/ -b 3 -p "*.py" --prefix mypack

# Pack Python + config files (use multiple passes or rename files)
python corpus_tfilepack myproject/ -p "**/*.py"

# Unpack from current directory into restored/
python corpus_toolsfilepacks . -d restored/

# Unpack with a custom prefix
python corpus_tools.py filepackcks/ -d restored/ -g "mypack_*.txt"
```

### Python API

```python
from filepack import pack_to_text_bins, unpack_text_bins

# Pack
pack_to_text_bins(
    source_dir  = "myproject/",
    output_prefix = "corpus_pack",   # → corpus_pack_1.txt, corpus_pack_2.txt …
    num_bins    = 5,
    glob_pattern  = "*.py",
)

# Unpack
unpack_text_bins(
    source_dir = ".",          # where the .txt packs live
    output_dir = "restored/",  # where to write the reconstructed tree
    pack_glob  = "corpus_pack_*.txt",
)
```

### Directories always excluded from packing

```
__pycache__   .pytest_cache   .git   .venv   env   .mypy_cache
```

---

## Full Round-Trip Workflow

```bash
# 1. Pack codebase
python filepack.py pack myproject/ -b 3 --prefix ctx

# 2. Upload ctx_1.txt, ctx_2.txt, ctx_3.txt to your LLM session

# 3. After LLM edits, save the modified packs

# 4. Restore
python corpfilepackunpack -s . -d restored/ -g "ctx_*.txt"

# 5. Verify nothing was lost
diff -r myproject/ restored/
```

---

## Error Handling Cheatsheet

| Error                                    | Cause                            | Fix                                        |
| ---------------------------------------- | -------------------------------- | ------------------------------------------ |
| `NotADirectoryError`                     | `source_dir` does not exist      | Check the path                             |
| `ValueError: Invalid regular expression` | Bad regex syntax                 | Test pattern with `re.compile()` first     |
| `⚠ Traversal blocked`                    | Pack file contains `../../` path | Untrusted pack file; inspect manually      |
| No files found                           | Pattern matches nothing          | Widen glob or check `_IGNORE_DIRS`         |
| `UnicodeDecodeError` skipped             | Binary file in source tree       | Expected; a placeholder comment is written |

---

## Defaults at a Glance

| Parameter             | Default             |
| --------------------- | ------------------- |
| `zip` output          | `archive.zip`       |
| `pack` glob pattern   | `*.py`              |
| `pack` number of bins | `5`                 |
| `pack` output prefix  | `corpus_pack`       |
| `unpack` source dir   | `.` (current dir)   |
| `unpack` dest dir     | `.` (current dir)   |
| `unpack` glob         | `corpus_pack_*.txt` |
