#!/usr/bin/env python3
"""
reformat_math.py — Canonically format display-math blocks in Markdown files.

Canonical form
--------------
Every  $$ ... $$  display-math block is emitted as:

    [blank line]
    $$
    <equation content, one or more lines, untouched>
    $$
    [blank line]

Rules
-----
    • A single blank line is inserted before the opening $$.
    • The opening $$  appears alone on its own line.
    • The equation content is preserved exactly (only leading/trailing
      blank lines within the block are stripped).
    • The closing $$ appears alone on its own line.
    • A single blank line is inserted after the closing $$.
    • Runs of three or more consecutive newlines in the final output
      are collapsed to two (= one blank line).
    • Fenced code blocks (``` ... ```) are left completely untouched.

Usage
-----
    python reformat_math.py <file>                # edit in place
    python reformat_math.py <file> <output_file>  # write to a new file
    python reformat_math.py --help
"""

import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Compiled patterns (module-level for efficiency)
# ---------------------------------------------------------------------------

# Splits text on fenced code blocks; odd-indexed segments are inside fences.
_FENCE = re.compile(r'(```.*?```)', re.DOTALL)

# Matches a display-math block: $$ ... $$  (non-greedy, spans newlines).
_DISPLAY = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)

# Three or more consecutive newlines.
_EXCESS_BLANK = re.compile(r'\n{3,}')


# ---------------------------------------------------------------------------
# Transformation helpers
# ---------------------------------------------------------------------------

def _reformat_block(match: re.Match) -> str:
    """Return the canonical four-line form for a single $$ ... $$ block."""
    content = match.group(1).strip('\n').rstrip()   # trim surrounding blank lines only
    content = content.strip()                        # trim any remaining whitespace
    return f'\n\n$$\n{content}\n$$\n\n'


def _reformat_segment(text: str) -> str:
    """Reformat all display-math blocks within one plain-text segment."""
    return _DISPLAY.sub(_reformat_block, text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reformat(text: str) -> str:
    """
    Return *text* with every display-math block canonically formatted.

    Fenced code blocks (``` ... ```) are passed through unchanged.
    """
    # Normalise Windows line endings.
    text = text.replace('\r\n', '\n')

    # Protect fenced code blocks by splitting around them.
    # Odd-indexed segments are inside fences and are left alone.
    segments = _FENCE.split(text)
    segments = [
        seg if idx % 2 == 1 else _reformat_segment(seg)
        for idx, seg in enumerate(segments)
    ]

    result = ''.join(segments)

    # Collapse runs of 3+ newlines to exactly 2 (one blank line).
    result = _EXCESS_BLANK.sub('\n\n', result)

    # Ensure exactly one trailing newline.
    return result.strip('\n') + '\n'


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    input_path  = Path(args[0])
    output_path = Path(args[1]) if len(args) > 1 else input_path

    if not input_path.is_file():
        sys.exit(f'Error: file not found: {input_path}')

    original    = input_path.read_text(encoding='utf-8')
    result      = reformat(original)

    # Compare against the normalised original to avoid spurious "changed" reports.
    normalised_original = original.replace('\r\n', '\n').strip('\n') + '\n'
    if result == normalised_original:
        print(f'No changes needed: {input_path}')
        return

    output_path.write_text(result, encoding='utf-8')

    n_blocks = len(_DISPLAY.findall(original))
    if output_path == input_path:
        print(f'Reformatted in place — {n_blocks} display-math block(s) processed: {input_path}')
    else:
        print(f'Reformatted {n_blocks} display-math block(s): {input_path} → {output_path}')


if __name__ == '__main__':
    main()
