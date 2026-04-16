"""
_hashing.py — Shared file-integrity primitives for packtools.

All tools that produce or verify hashes import from here.  Having one
implementation guarantees that dir_compare, manifest_check, and
verify_install all agree on the encoding convention.

Convention
----------
Hashes are computed after normalising line endings to CRLF so that a file
produced on Linux (LF) and the same file downloaded on Windows (CRLF) yield
identical 16-char prefixes.  This is Ken's cross-platform hashing standard.
"""

import hashlib


def sha16(data: bytes) -> str:
    """
    SHA-256 of CRLF-normalised bytes, first 16 hex chars.

    Example:
        sha16(b"hello\\n")  # same result as sha16(b"hello\\r\\n")
    """
    normalised = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(normalised).hexdigest()[:16]


def bundle_hash(file_hashes: dict[str, str]) -> str:
    """
    Hash-of-hashes: sort tracked paths, concatenate their sha16s, SHA-256,
    return 24 chars.

    Cheap regardless of file sizes — the input is at most a few hundred
    bytes no matter how large the tracked files are.

    Example:
        bundle_hash({"a.py": "abc123...", "b.py": "def456..."})
        # → 24-char hex string
    """
    concatenated = "".join(sha for _, sha in sorted(file_hashes.items()))
    return hashlib.sha256(concatenated.encode()).hexdigest()[:24]
