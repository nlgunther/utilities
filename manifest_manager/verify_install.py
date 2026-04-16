# verify_install.py
# Verifies your local install matches the expected file hashes in MANIFEST.txt.
#
# Usage (run from project root):
#   python verify_install.py
#   python verify_install.py --manifest path/to/MANIFEST.txt
#
# To update expected results after downloading new files:
#   Edit MANIFEST.txt — change only the hash values on the relevant lines.
#   The format is:  sha256_prefix<TAB>local_path
#   Lines starting with # are comments. The bundle: line holds the overall hash.
#
# Line endings: hashes are computed after normalising to CRLF (Windows-style)
# so the manifest works correctly regardless of which OS generated the files.

import hashlib
import os
import sys


def sha16(data: bytes) -> str:
    """SHA-256 of data normalised to CRLF line endings, first 16 hex chars."""
    normalised = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(normalised).hexdigest()[:16]


def bundle_hash(file_hashes: dict[str, str]) -> str:
    """
    Compute bundle integrity hash from individual file hashes.

    Method: sort tracked paths lexicographically, concatenate their 16-char
    SHA-256 prefixes in that order, SHA-256 the result, return 24 chars.

    This is cheaper than hashing all file contents — the input is at most
    a few hundred bytes regardless of how large the files are.
    """
    concatenated = "".join(
        sha for _, sha in sorted(file_hashes.items())
    )
    return hashlib.sha256(concatenated.encode()).hexdigest()[:24]


def load_manifest(path):
    """
    Parse MANIFEST.txt into (bundle_hash, {local_path: expected_sha}).
    Skips blank lines and comment lines (starting with #).
    """
    if not os.path.exists(path):
        print("ERROR: manifest file not found: %s" % path)
        sys.exit(1)

    # bundle: line holds hash-of-hashes (SHA-256 of sorted file hashes concatenated)
    bundle = None
    files = {}

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if not line or line.startswith("#"):
                continue
            if line.startswith("bundle:"):
                bundle = line.split("\t", 1)[1].strip()
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                expected_sha, path_str = parts[0].strip(), parts[1].strip()
                files[path_str] = expected_sha

    return bundle, files


def verify(manifest_path="MANIFEST.txt"):
    bundle_expected, files = load_manifest(manifest_path)

    ok = True
    actual_hashes: dict[str, str] = {}   # path → actual sha16

    for local_path, expected in files.items():
        win_path = local_path.replace("/", os.sep)
        if not os.path.exists(win_path):
            print("MISSING  %s" % local_path)
            ok = False
            actual_hashes[local_path] = "0" * 16   # placeholder so bundle still computes
            continue
        with open(win_path, "rb") as f:
            data = f.read()
        actual = sha16(data)
        actual_hashes[local_path] = actual
        if actual == expected:
            print("OK       %s" % local_path)
        else:
            print("MISMATCH %s" % local_path)
            print("         expected: %s" % expected)
            print("         actual:   %s" % actual)
            ok = False

    print()

    # Verify bundle hash (hash-of-hashes, sorted lexicographically by path)
    if bundle_expected:
        actual_bundle = bundle_hash(actual_hashes)
        if actual_bundle == bundle_expected:
            print("Bundle OK:       %s" % actual_bundle)
        else:
            print("Bundle MISMATCH")
            print("  expected: %s" % bundle_expected)
            print("  actual:   %s" % actual_bundle)
            ok = False

    print()
    if ok:
        print("All files match.")
    else:
        print("Some files are out of date or missing.")
        print("Re-download from the outputs folder and try again.")
        sys.exit(1)


if __name__ == "__main__":
    manifest = "MANIFEST.txt"
    if len(sys.argv) > 2 and sys.argv[1] == "--manifest":
        manifest = sys.argv[2]
    verify(manifest)
