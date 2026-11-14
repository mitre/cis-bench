#!/usr/bin/env python3
"""Fix markdown list formatting issues.

Python-Markdown, which builds the docs, reads a list that follows a text line with no blank
line between them as part of that paragraph. This script puts the blank line in.

Fenced code is left as it is, at any indentation: the docs use SuperFences, which finds
fences inside admonitions and tabs (a CommonMark parser such as markdown-it-py reads a fence
indented four spaces as indented code, so it cannot be used to find them). YAML front matter
at the start of a file is left as it is too.
"""

import re
import sys
from pathlib import Path

# A bullet (-, *, +) or a number followed by . or ), then a space: the start of a list item.
LIST_ITEM = re.compile(r"[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]")
# An opening fence: three or more backticks or tildes, at any indentation.
FENCE = re.compile(r"[ \t]*(`{3,}|~{3,})")


def _closes(line: str, fence: str) -> bool:
    """Whether ``line`` closes a block opened with ``fence``: the same character, at least
    as many of it, and nothing after but whitespace."""
    match = FENCE.match(line)
    return (
        match is not None
        and match.group(1)[0] == fence[0]
        and len(match.group(1)) >= len(fence)
        and line[match.end() :].strip() == ""
    )


def _front_matter_end(lines: list[str]) -> int:
    """The index of the first line after YAML front matter (0 when there is none)."""
    if not lines or lines[0].strip() != "---":
        return 0
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() in ("---", "..."):
            return index + 1
    return 0


def fix_list_formatting(content: str) -> tuple[str, int]:
    """Fix markdown list formatting by adding blank lines before lists.

    Args:
        content: Markdown file content

    Returns:
        Tuple of (fixed_content, number_of_fixes)
    """
    lines = content.split("\n")
    start = _front_matter_end(lines)
    fixed_lines = lines[:start]
    fixes = 0
    fence: str | None = None  # the opening fence of the code block we are in
    # Whether the run of lines since the last blank line began with a list item (None: no
    # run yet). The wrapped lines of an item, code fenced inside it and lazy continuation
    # lines all belong to the list, so an item after them needs no blank line.
    run_is_list: bool | None = None

    for line in lines[start:]:
        if fence is not None:
            if _closes(line, fence):
                fence = None
        elif not line.strip():
            run_is_list = None
        elif (opening := FENCE.match(line)) is not None:
            fence = opening.group(1)
            if run_is_list is None:
                run_is_list = False
        elif LIST_ITEM.match(line):
            if run_is_list is False:
                fixed_lines.append("")
                fixes += 1
            run_is_list = True
        elif run_is_list is None:
            run_is_list = False
        fixed_lines.append(line)

    return "\n".join(fixed_lines), fixes


def process_markdown_file(file_path: Path, dry_run: bool = False) -> int:
    """Process a single markdown file.

    Args:
        file_path: Path to markdown file
        dry_run: If True, only report issues without fixing

    Returns:
        Number of fixes applied
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        fixed_content, fixes = fix_list_formatting(content)

        if fixes > 0:
            print(f"  {file_path}: {fixes} fix(es)")

            if not dry_run:
                file_path.write_text(fixed_content, encoding="utf-8")
                return fixes
            else:
                print(f"    [DRY RUN] Would fix {fixes} list(s)")
                return 0
        else:
            return 0

    except Exception as e:
        print(f"  ERROR processing {file_path}: {e}", file=sys.stderr)
        return 0


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Fix markdown list formatting")
    parser.add_argument(
        "paths",
        nargs="*",
        default=["docs/", "README.md"],
        help="Paths to process (default: docs/ and README.md)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be fixed without making changes"
    )
    args = parser.parse_args()

    total_fixes = 0
    files_processed = 0

    print("Scanning markdown files for list formatting issues...")
    print()

    for path_str in args.paths:
        path = Path(path_str)

        if path.is_file() and path.suffix == ".md":
            # Single file
            fixes = process_markdown_file(path, args.dry_run)
            total_fixes += fixes
            files_processed += 1

        elif path.is_dir():
            # Directory - process all .md files recursively
            for md_file in path.rglob("*.md"):
                # Skip archive and research directories
                if "archive" in md_file.parts or "research" in md_file.parts:
                    continue

                fixes = process_markdown_file(md_file, args.dry_run)
                total_fixes += fixes
                files_processed += 1

    print()
    print(f"Processed: {files_processed} file(s)")
    print(f"Fixed: {total_fixes} list(s)")

    if args.dry_run:
        print("\n[DRY RUN] No files were modified. Run without --dry-run to apply fixes.")
    else:
        print(f"\n✓ Fixed {total_fixes} list formatting issue(s)")

    return 0 if total_fixes == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
