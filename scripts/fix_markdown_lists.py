#!/usr/bin/env python3
"""Fix markdown list formatting issues.

Markdown requires a blank line before bullet lists for proper rendering.
This script finds and fixes instances where lists are missing the blank line.
"""

import sys
from pathlib import Path


def fix_list_formatting(content: str) -> tuple[str, int]:
    """Fix markdown list formatting by adding blank lines before lists.

    Args:
        content: Markdown file content

    Returns:
        Tuple of (fixed_content, number_of_fixes)
    """
    lines = content.split("\n")
    fixed_lines = []
    fixes = 0

    for i, line in enumerate(lines):
        # Check if current line is a bullet list item
        is_list_item = line.strip().startswith(("- ", "* ", "+ "))

        # Check if previous line exists and is not blank
        if i > 0:
            prev_line = lines[i - 1].strip()
            prev_is_blank = prev_line == ""

            # If this is a list item and previous line is not blank and not a list item
            if is_list_item and not prev_is_blank:
                # Check if previous line is not also a list item
                prev_is_list = prev_line.startswith(("- ", "* ", "+ "))

                if not prev_is_list:
                    # Add blank line before this list
                    fixed_lines.append("")
                    fixes += 1

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
