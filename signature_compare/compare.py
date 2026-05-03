"""
compare.py — Compute and compare sha16 signatures for one or more paths.

Accepts any number of file paths, prints the sha16 hash of each, and
explicitly flags any two paths whose content is identical (same hash).

Usage:
    signature-compare <path1> <path2> [<path3> ...]

Examples:
    signature-compare foo.py bar.py
    signature-compare src/main.py backup/main.py archive/main.py

Exit codes:
    0 — all signatures unique (or only one path given)
    1 — one or more collisions detected
    2 — argument or I/O error
"""

import argparse
import sys
from collections import defaultdict

from packtools._hashing import sha16


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_signatures(paths: list[str]) -> dict[str, str]:
    """
    Read each path and return {path: sha16}. Unreadable paths get "ERROR(...)".

    Example:
        compute_signatures(["foo.py", "bar.py"])
        # → {"foo.py": "a3f1c2d4e5b6f7a8", "bar.py": "1b2c3d4e5f6a7b8c"}
    """
    result: dict[str, str] = {}
    for path in paths:
        try:
            with open(path, "rb") as f:
                result[path] = sha16(f.read())
        except OSError as e:
            result[path] = f"ERROR({e.strerror})"
    return result


def find_collisions(signatures: dict[str, str]) -> dict[str, list[str]]:
    """
    Return groups of two or more paths that share the same hash.
    ERROR entries are excluded from collision detection.

    Example:
        find_collisions({"a.py": "abc123", "b.py": "abc123", "c.py": "xyz"})
        # → {"abc123": ["a.py", "b.py"]}
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for path, sig in signatures.items():
        if not sig.startswith("ERROR"):
            groups[sig].append(path)
    return {sig: paths for sig, paths in groups.items() if len(paths) > 1}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_report(
    signatures: dict[str, str],
    collisions: dict[str, list[str]],
) -> str:
    """Render the signature table and any collision notices as a string."""
    w = max(len(p) for p in signatures)
    sep = "-" * (w + 2 + 16)

    lines = [
        f"{'Path':<{w}}  Signature",
        sep,
    ]
    for path, sig in signatures.items():
        lines.append(f"{path:<{w}}  {sig}")
    lines += [sep, "", f"Total: {len(signatures)} path(s)"]

    if collisions:
        lines += ["", "COLLISIONS — identical content detected:"]
        for sig, paths in collisions.items():
            lines.append(f"  [{sig}]")
            for p in paths:
                lines.append(f"    {p}")
    else:
        valid = sum(1 for s in signatures.values() if not s.startswith("ERROR"))
        if valid > 1:
            lines.append("All signatures are unique.")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute and compare sha16 signatures for one or more paths.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("paths", nargs="+", help="One or more file paths to hash")
    args = parser.parse_args()

    if not args.paths:
        parser.print_help()
        sys.exit(2)

    signatures = compute_signatures(args.paths)
    collisions = find_collisions(signatures)
    print(format_report(signatures, collisions))

    sys.exit(1 if collisions else 0)


if __name__ == "__main__":
    main()
