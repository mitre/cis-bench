# Tabbed TUI Focus Management Research

**Research Date**: 2026-01-31
**Issue**: Arrow keys don't work for DataTable navigation inside TabbedContent
**Agents**: aa5a5a4, a1d7942

---

## Root Cause Analysis

### Why Arrow Keys Don't Work

The issue stems from how Textual handles focus within nested widget structures:

1. **TabbedContent/TabPane intercepts key events** - The TabbedContent widget captures certain key events for tab navigation. Arrow keys may be consumed by TabbedContent/TabPane before reaching the DataTable.

2. **Widget hierarchy prevents focus propagation** - `CatalogTabPane` extends `Static`, not `App`. This means it doesn't have the same focus management behavior as the working standalone implementations.

3. **Missing focus scope** - Unlike `BaseBrowserApp` which is the top-level App and controls all focus behavior, `CatalogTabPane` is a nested compound widget inside a TabPane. The DataTable's focus needs explicit propagation through the widget hierarchy.

### Code Comparison

**Working Pattern** (standalone apps - `catalog/app.py`):
```python
class CatalogBrowserApp(BaseBrowserApp):  # Extends App
    BINDINGS = COMMON_BINDINGS + [
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
    ]

    def action_cursor_down(self) -> None:
        table = self.query_one("#catalog-table", DataTable)
        table.action_cursor_down()
```

- App-level bindings have direct control
- No intermediate widget layers
- DataTable receives focus directly

**Broken Pattern** (tab pane - `catalog/pane.py`):
```python
class CatalogTabPane(Static):  # Extends Static, not App
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        # Arrow keys are NOT explicitly bound
    ]
```

- Static widget bindings are lower priority
- Arrow keys NOT in BINDINGS list
- Relies on DataTable's default arrow key handling
- TabbedContent intercepts them first

---

## Solutions (From Agent Research)

### Solution 1: Explicit Arrow Key Bindings ✅ RECOMMENDED

Add arrow key bindings to prevent TabbedContent from consuming them:

```python
BINDINGS = BaseTabPane.BINDINGS + [
    # BaseTabPane.BINDINGS already includes:
    # - Binding("down", "cursor_down", "Down", show=False)
    # - Binding("up", "cursor_up", "Up", show=False)
    # - Binding("j", "cursor_down", "Down", show=False)
    # - Binding("k", "cursor_up", "Up", show=False)
    # - Binding("pagedown", "page_down", "Page Down", show=False)
    # - Binding("pageup", "page_up", "Page Up", show=False)

    # Catalog-specific bindings
    Binding("space", "toggle_select", "Select", show=True),
    Binding("f", "toggle_detail_focus", "Detail", show=True),
    Binding("o", "open_in_browser", "Open URL", show=True),
]
```

**Why this works**: Explicit bindings on the widget take priority and prevent TabbedContent from consuming the events.

### Solution 2: CSS Height Constraints ✅ REQUIRED

DataTable scrolling requires proper height constraints:

```python
# In main_app.py
CSS = """
TabbedContent {
    height: 100%;
}

TabbedContent ContentSwitcher, DataTable {
    height: 1fr;
}

TabPane {
    padding: 1 2;
}
"""
```

**Why this works**: Missing height constraints prevent proper layout calculations for scrolling. Must apply to both `ContentSwitcher` AND `DataTable`.

**Source**: [GitHub Discussion #2961](https://github.com/Textualize/textual/discussions/2961)

### Solution 3: TabActivated Handler ✅ REQUIRED

Focus must be explicitly set when tabs change:

```python
from textual import on
from textual.widgets import TabbedContent, DataTable

class MainTUIApp(App):
    @on(TabbedContent.TabActivated, "#tab-catalog")
    def on_catalog_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Focus DataTable when catalog tab is activated."""
        try:
            table = event.pane.query_one("#catalog-table", DataTable)
            table.focus()
        except Exception:
            pass  # Table not loaded yet
```

**Why this works**: Tab switching doesn't automatically focus child widgets. You must explicitly call `.focus()` when the tab activates.

**Source**: [GitHub Discussion #3026](https://github.com/Textualize/textual/discussions/3026)

---

## How Focus Works Inside TabbedContent

**Key Insight**: TabPane bindings and child widget interactions only activate when focus is **inside** the pane, not just when the tab is selected.

- Each widget has a `can_focus` attribute
- TabbedContent is focusable and manages focus for child TabPane widgets
- **Switching tabs does NOT automatically transfer focus to child widgets**
- Bindings defined on TabPane only display in footer when focus is within the pane

**The Pattern**:
1. Listen for `TabbedContent.TabActivated` events
2. Query for the focusable widget inside the activated pane
3. Call `.focus()` on that widget

---

## Known Issues with DataTable Inside TabbedContent

### Issue #1: Tab Switching Reverts Focus
**GitHub**: [Issue #5225](https://github.com/Textualize/textual/issues/5225)

When a DataTable is active and you press a keybinding to switch tabs, the GUI switches tabs then immediately switches back to the first tab.

**Workaround**: Avoid placing focusable widgets after Input fields on the same tab.

### Issue #2: Scrolling Problems
**GitHub**: [Discussion #2961](https://github.com/Textualize/textual/discussions/2961)

DataTable scrolling and auto-focus fail when inside TabPane without proper CSS.

**Solution**: Apply height constraints (see Solution 2 above).

### Issue #3: Slow Focus Switching
**GitHub**: [Issue #4737](https://github.com/Textualize/textual/issues/4737)

When DataTable contains lots of data, pressing Tab takes ~2 seconds to switch focus. Performance issue with large datasets.

---

## Implementation Checklist

- [x] Create `BaseTabPane(Static)` with COMMON_BINDINGS
- [x] Update `catalog/pane.py` to extend BaseTabPane
- [x] Remove duplicate action methods from pane (now in BaseTabPane)
- [ ] Add CSS height constraints to `main_app.py`
- [ ] Add TabActivated handler to `main_app.py`
- [ ] Test arrow key navigation
- [ ] Test tab switching focus behavior
- [ ] Test page up/down navigation

---

## Sources

- [Textual TabbedContent Documentation](https://textual.textualize.io/widgets/tabbed_content/)
- [Textual Input Guide - Focus](https://textual.textualize.io/guide/input/)
- [Textual Events Guide](https://textual.textualize.io/guide/events/)
- [Issue #5225: TabbedContent and DataTable Tab Switching](https://github.com/Textualize/textual/issues/5225)
- [Discussion #2961: Scrolling in DataTable inside TabPane](https://github.com/Textualize/textual/discussions/2961)
- [Discussion #3026: Different Bindings on TabPanes](https://github.com/Textualize/textual/discussions/3026)
- [Issue #4737: DataTable Focus Switching Performance](https://github.com/Textualize/textual/issues/4737)
- [Discussion #2408: How to use TabbedContent and TabPane](https://github.com/Textualize/textual/discussions/2408)

---

## BaseTabPane Implementation

```python
class BaseTabPane(Static):
    """Base class for tab panes in MainTUIApp.

    Provides shared bindings and common action implementations for all tab panes.
    Extends Static to be used as a widget inside TabbedContent.
    """

    # Share common bindings at widget level
    BINDINGS = COMMON_BINDINGS

    def action_cursor_down(self) -> None:
        """Move cursor down in DataTable."""
        try:
            table = self.query_one(DataTable)
            table.action_cursor_down()
        except Exception:
            pass

    def action_cursor_up(self) -> None:
        """Move cursor up in DataTable."""
        try:
            table = self.query_one(DataTable)
            table.action_cursor_up()
        except Exception:
            pass

    def action_page_down(self) -> None:
        """Page down in DataTable."""
        try:
            table = self.query_one(DataTable)
            table.action_page_down()
        except Exception:
            pass

    def action_page_up(self) -> None:
        """Page up in DataTable."""
        try:
            table = self.query_one(DataTable)
            table.action_page_up()
        except Exception:
            pass
```
