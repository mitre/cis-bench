"""Backwards compatibility - imports from new modular location.

This file re-exports from cis_bench.cli.commands.tui.catalog for
backwards compatibility with existing code.

New code should import from cis_bench.cli.commands.tui.catalog directly.
"""

from cis_bench.cli.commands.tui.catalog import (
    ActionMenu,
    CatalogBrowserApp,
    CatalogDetailView,
    run_catalog_browser,
)

__all__ = [
    "ActionMenu",
    "CatalogBrowserApp",
    "CatalogDetailView",
    "run_catalog_browser",
]
