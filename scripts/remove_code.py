#!/usr/bin/env python3
"""LibCST utility for safely removing functions/methods/classes from Python files.

Usage:
    python scripts/remove_code.py --file src/module.py --remove function_name
    python scripts/remove_code.py --file src/module.py --remove "method1,method2,class_name"
    python scripts/remove_code.py --file src/module.py --list  # Show all functions/methods
"""

import argparse
import sys
from pathlib import Path

import libcst as cst


class CodeRemover(cst.CSTTransformer):
    """Remove specified functions, methods, or classes from CST."""

    def __init__(self, names_to_remove: set[str]):
        self.names_to_remove = names_to_remove
        self.removed = []

    def leave_FunctionDef(self, original_node, updated_node):
        """Remove functions/methods by name."""
        if updated_node.name.value in self.names_to_remove:
            self.removed.append(f"function: {updated_node.name.value}")
            return cst.RemovalSentinel.REMOVE
        return updated_node

    def leave_ClassDef(self, original_node, updated_node):
        """Remove classes by name."""
        if updated_node.name.value in self.names_to_remove:
            self.removed.append(f"class: {updated_node.name.value}")
            return cst.RemovalSentinel.REMOVE
        return updated_node


class CodeLister(cst.CSTVisitor):
    """List all functions, methods, and classes in file."""

    def __init__(self):
        self.functions = []
        self.classes = []
        self.methods = []
        self.current_class = None

    def visit_ClassDef(self, node):
        self.classes.append(node.name.value)
        self.current_class = node.name.value

    def leave_ClassDef(self, node):
        self.current_class = None

    def visit_FunctionDef(self, node):
        if self.current_class:
            self.methods.append(f"{self.current_class}.{node.name.value}")
        else:
            self.functions.append(node.name.value)


def remove_code(
    file_path: Path, names_to_remove: set[str], dry_run: bool = False
) -> tuple[str, list[str]]:
    """Remove specified code elements from file.

    Args:
        file_path: Path to Python file
        names_to_remove: Set of function/method/class names to remove
        dry_run: If True, show what would be removed without modifying file

    Returns:
        Tuple of (new_code, removed_items)
    """
    with open(file_path) as f:
        source = f.read()

    module = cst.parse_module(source)
    remover = CodeRemover(names_to_remove)
    new_module = module.visit(remover)

    if not dry_run and remover.removed:
        with open(file_path, "w") as f:
            f.write(new_module.code)

    return new_module.code, remover.removed


def list_code(file_path: Path):
    """List all functions, methods, and classes in file.

    Args:
        file_path: Path to Python file
    """
    with open(file_path) as f:
        source = f.read()

    module = cst.parse_module(source)
    lister = CodeLister()
    module.visit(lister)

    print(f"\n📄 {file_path}")
    print(f"\n{'=' * 60}")

    if lister.classes:
        print(f"\n🏛️  Classes ({len(lister.classes)}):")
        for cls in sorted(lister.classes):
            print(f"  - {cls}")

    if lister.functions:
        print(f"\n⚙️  Functions ({len(lister.functions)}):")
        for func in sorted(lister.functions):
            print(f"  - {func}")

    if lister.methods:
        print(f"\n🔧 Methods ({len(lister.methods)}):")
        for method in sorted(lister.methods):
            print(f"  - {method}")

    print(f"\n{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Safely remove functions/methods/classes using LibCST"
    )
    parser.add_argument("--file", required=True, help="Python file to modify")
    parser.add_argument(
        "--remove",
        help="Comma-separated list of names to remove (e.g., 'func1,method2,Class3')",
    )
    parser.add_argument("--list", action="store_true", help="List all code elements in file")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be removed without modifying"
    )

    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"❌ Error: File not found: {file_path}")
        sys.exit(1)

    # List mode
    if args.list:
        list_code(file_path)
        return

    # Remove mode
    if not args.remove:
        print("❌ Error: Must specify --remove or --list")
        parser.print_help()
        sys.exit(1)

    names = {name.strip() for name in args.remove.split(",")}

    print(f"\n🔍 Analyzing {file_path}...")
    print(f"🎯 Targets: {', '.join(names)}")

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE (no files will be modified)")

    new_code, removed = remove_code(file_path, names, dry_run=args.dry_run)

    if removed:
        print("\n✅ Removed:")
        for item in removed:
            print(f"  - {item}")

        if not args.dry_run:
            print(f"\n💾 File updated: {file_path}")
        else:
            print("\n👀 Preview (first 50 lines):")
            print("-" * 60)
            for i, line in enumerate(new_code.split("\n")[:50], 1):
                print(f"{i:4d} {line}")
    else:
        print("\n⚠️  No matching items found to remove")
        print(f"\nUse --list to see all available items in {file_path}")


if __name__ == "__main__":
    main()
