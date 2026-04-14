import argparse
import re
from pathlib import Path
import sys

def build_tree(directory, pattern, prefix=""):
    """Recursively builds a tree string of matched files and their parents."""
    paths = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    
    # Filter: Keep if it's a dir (might contain matches) or a file matching the regex
    valid_paths = []
    for p in paths:
        if p.is_file():
            if pattern.search(p.name):
                valid_paths.append(p)
        else:
            # Check if subdirectory contains any matching files recursively
            subtree = build_tree(p, pattern)
            if subtree:
                valid_paths.append(p)

    tree_str = ""
    count = len(valid_paths)
    for i, path in enumerate(valid_paths):
        is_last = i == count - 1
        connector = "└── " if is_last else "├── "
        
        tree_str += f"{prefix}{connector}{path.name}\n"
        
        if path.is_dir():
            extension = "    " if is_last else "│   "
            tree_str += build_tree(path, pattern, prefix + extension)
            
    return tree_str

def main():
    parser = argparse.ArgumentParser(description="Generate a regex-filtered ASCII directory tree.")
    parser.add_argument("directory", type=Path, help="The root directory to scan")
    parser.add_argument("regex", type=str, help="The regular expression to match filenames")
    parser.add_argument("--out", type=Path, help="Optional output file path")

    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"Error: {args.directory} is not a valid directory.")
        sys.exit(1)

    try:
        pattern = re.compile(args.regex)
    except re.error as e:
        print(f"Error: Invalid regex: {e}")
        sys.exit(1)

    # Header for the tree
    output = f"{args.directory.name}/\n" + build_tree(args.directory, pattern)

    if args.out:
        args.out.write_text(output, encoding="utf-8")
        print(f"Tree written to {args.out}")
    else:
        print(output)

if __name__ == "__main__":
    main()