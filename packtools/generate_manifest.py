# generate_manifest.py -- Regenerate MANIFEST.txt for a kentools-style package.
#
# To adapt for a different package, change PACKAGE and FILES only.
#
# Run from the project root whenever files are added, removed, or edited:
#   python generate_manifest.py
#
# Output: MANIFEST.txt (overwrites any existing file)

import hashlib
import os
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configure here
# ---------------------------------------------------------------------------

PACKAGE = "packtools"

FILES = [
    "packtools/__init__.py",
    "packtools/_hashing.py",
    "packtools/delete_pattern.py",
    "packtools/dir_compare.py",
    "packtools/filepack.py",
    "packtools/filtered_tree.py",
    "packtools/manifest_check.py",
    "packtools/verify_install.py",
    "packtools/generate_manifest.py",# <- NEW
    "pyproject.toml",
    "tests/test_packtools.py",
]

# ---------------------------------------------------------------------------
# Hashing (do not edit)
# ---------------------------------------------------------------------------

def sha16(data: bytes) -> str:
    normalised = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(normalised).hexdigest()[:16]


def bundle_hash(file_hashes: dict) -> str:
    cat = "".join(sha for _, sha in sorted(file_hashes.items()))
    return hashlib.sha256(cat.encode()).hexdigest()[:24]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    rows = {}
    for path in FILES:
        if not os.path.exists(path):
            rows[path] = "MISSING"
            continue
        with open(path, "rb") as f:
            rows[path] = sha16(f.read())

    bundle = bundle_hash({p: s for p, s in rows.items() if s != "MISSING"})
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    tc = sum(
        sum(1 for line in open(p) if line.strip().startswith("def test_"))
        for p in FILES if p.startswith("tests/") and os.path.exists(p)
    )

    lines = [
        "# %s file manifest" % PACKAGE,
        "# Generated: %s" % ts,
        "# Format:  sha256_prefix<TAB>local_path",
        "# Comments (lines starting with #) and blank lines are ignored.",
        "# verify-install reads this file - do not change the format.",
        "# Note: hashes computed with CRLF normalisation (Windows-compatible).",
        "# Bundle: SHA-256 of sorted file hashes concatenated (hash-of-hashes).",
        "#",
        "bundle:\t%s" % bundle,
        "#",
        "# Source files",
    ]
    for path, sha in rows.items():
        if sha == "MISSING":
            lines.append("# MISSING\t%s" % path)
        else:
            lines.append("%s\t%s" % (sha, path))
    lines += ["#", "# Tests: %d methods" % tc]

    with open("MANIFEST.txt", "w", encoding="ascii") as f:
        f.write("\n".join(lines) + "\n")

    print("Bundle hash: %s" % bundle)
    print("Tests: %d methods" % tc)
    print("Wrote MANIFEST.txt")

if __name__ == "__main__":
    main()
