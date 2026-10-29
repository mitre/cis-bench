# Textual TUI Framework Research

Research compiled from official Textual documentation for the cis-bench TUI refactoring project.

**Source**: https://github.com/Textualize/textual
**Documentation**: https://textual.textualize.io/
**Research Date**: 2026-01-30

---

## Table of Contents

1. [Core Concepts](#1-core-concepts)
2. [Testing Patterns](#2-testing-patterns)
3. [Screen Architecture](#3-screen-architecture)
4. [Workers and Async](#4-workers-and-async)
5. [Widgets and Messages](#5-widgets-and-messages)
6. [Widget Gallery](#6-widget-gallery)
7. [How-To Guides](#7-how-to-guides)

---

## 1. Core Concepts

### App Lifecycle

**Key Methods:**

- `compose()` - Generator method that yields widget instances to be displayed
- `on_mount()` - Called immediately after app enters application mode; use for initialization
- `exit(value)` - Terminates the app with optional return value

**Pattern:**
```
Initialize → Mount Event (on_mount) → Compose Widgets → User Interaction → Exit
```

**Best Practices:**

- Keep `compose()` declarative and organized
- Use `on_mount()` for one-time setup (style initialization, screen configuration)
- Use `await self.mount()` when dynamically mounting widgets that need immediate modification
- Type your return value: `App[ReturnType]` for type safety

### Screen Management

**Screen Stack Model:**

- Apps maintain a stack of screens; only the topmost is active/visible
- Framework requires at least one screen (auto-created if not specified)
- Previous screens are preserved in the stack (not deleted until explicitly replaced)

**Key Operations:**

- `push_screen()` - Add screen on top (preserves stack below)
- `pop_screen()` - Remove topmost screen, restore previous
- `switch_screen()` - Replace active screen without preserving it

**Advanced Patterns:**

- **Modal Screens** - Use `ModalScreen` to prevent app-level bindings while modal is active
- **Data Return** - Call `dismiss()` to pop and pass data back, or use `push_screen_wait()` for async retrieval
- **Modes** - Define multiple independent screen stacks via `MODES` class variable for context switching

**Best Practice:** Use modal screens for dialogs/overlays; use screen stack for navigation flows.

### Widget Tree & Composition

**Core Concepts:**

- Widgets are rectangular screen regions; they form a hierarchical tree
- Extend `Widget` or `Static` for custom widgets
- Add widgets statically via `compose()` or dynamically via `mount()`

**Widget Features:**

- **`render()`** - Returns content (text with markup or Rich renderables)
- **`DEFAULT_CSS`** - Embed styling directly in widget class
- **`BINDINGS`** - Define keyboard shortcuts with action handlers
- **`can_focus=True`** - Makes widget focusable and keyboard-interactive
- **`border_title`/`border_subtitle`** - Label decorations
- **`tooltip`** - Hover help text
- **`loading` property** - Display loading indicator while async work completes

**Advanced Rendering:**

- **Line API** - Implement `render_line(y)` for efficient row-by-row updates using `Strip`/`Segment`
- **Component Classes** - Style specific visual elements via CSS without coupling to code

**Container Widgets:** Use `Vertical`, `Horizontal`, `Grid` context managers for simplified composition.

### CSS Styling System

**File Format:**

- `.tcss` extension (Textual CSS)
- Rule sets with selectors and properties (similar to standard CSS)

**Selector Types:**

- **Type**: `Button` (matches widget class)
- **ID**: `#dialog` (unique widget)
- **Class**: `.success` (CSS classes on widgets)
- **Universal**: `*` (all widgets)
- **Pseudo-classes**: `:hover`, `:focus`, `:disabled`
- **Combinators**: Space (descendant), `>` (direct child)

**Key Features:**

- **CSS Variables** - Reusable values: `$primary-color`
- **Nesting** - Nested rules with `&` selector
- **Box Model** - width/height, padding, border, margin, box-sizing
- **Responsive Units** - `px`, `%`, `vw`/`vh`, `fr` (fractional space)
- **Live Editing** - Run with `--dev` flag for hot CSS reload

**Dimension Properties:**

- Fixed: `100px`
- Percentage: `50%`
- Viewport: `50vw`, `50vh`
- Fractional: `1fr`, `2fr` (divide available space proportionally)
- Auto: `auto` (size to content)

**Best Practice:** Separate presentation (CSS) from logic (Python) for maintainability.

### Reactive Attributes

**Core Concept:**

- Attributes with "superpowers"—automatically trigger UI updates when changed
- Defined as class variables using `reactive()` descriptor

**Key Superpowers:**

| Feature | Purpose | Example |
|---------|---------|---------|
| **Smart Refresh** | Calls `render()` on change | `count = reactive(0)` |
| **Validation** | Constrain/transform values | `validate_count(value)` method |
| **Watch** | Execute code on change | `watch_count(new_value)` method |
| **Compute** | Derive from other reactives | `compute_total()` caches results |
| **Recompose** | Rebuild widget tree on change | `items = reactive([], recompose=True)` |
| **Layout** | Recalculate layout on change | `width = reactive(0, layout=True)` |

**Advanced Patterns:**

- **`validate_<attr>`** - Called before assignment; can transform value
- **`watch_<attr>(value)`** or **`watch_<attr>(old, new)`** - Called after assignment
- **`compute_<attr>`** - Derives value; re-runs when dependencies change
- **`.watch()` method** - Programmatically add watchers from external code
- **`.data_bind()`** - Auto-sync parent reactive with child widget attribute
- **`.mutate_reactive()`** - Trigger update after modifying mutable objects (list/dict)
- **`set_reactive()`** - Assign during init without triggering watchers (before mount)

**Best Practice:** Use reactives for state-dependent rendering rather than manual updates.

### Event & Message System

**Architecture:**

- Message queue processes events sequentially
- Events are system-generated (keyboard, mouse); messages are custom (widget communication)

**Handler Patterns:**

- **Convention-based**: `on_<namespace>_<messagename>` (e.g., `on_input_changed`)
- **Decorator-based**: `@on(Widget.Message, "css-selector")`

**Key Behaviors:**

- **Bubbling** - Messages propagate up widget tree (parent widgets receive)
- **Prevent Default** - Use `prevent_default()` to override default behavior
- **Async Handlers** - Handlers can be coroutines for async operations
- **Stop Propagation** - Call `stop()` to prevent further bubbling

**Best Practice:** Use messages for widget-to-parent communication; use watchers for internal state changes.

---

## 2. Testing Patterns

### Core Testing Setup

**Framework**: pytest + pytest-asyncio (enable `asyncio_mode = auto` in pytest config)

**Basic Structure**:
```python
async def test_example():
    app = MyApp()
    async with app.run_test() as pilot:
        # Interact and assert
```

The `run_test()` method runs the app headlessly and returns a **Pilot** object for programmatic interaction.

### Simulating User Input (Pilot API)

**Keyboard Presses**:
```python
await pilot.press("h", "e", "l", "l", "o")        # Simulate typing
await pilot.press("enter")                         # Special keys
await pilot.press("ctrl+c")                        # Modifier syntax
```

**Mouse Clicks**:
```python
await pilot.click("#button-id")                    # CSS selector
await pilot.click(Button)                          # Widget type
await pilot.click(offset=(10, 5))                  # Precise coordinates
await pilot.click(times=2)                         # Double/triple click
await pilot.click("#widget", control=True)         # With modifiers
```

**Other Interactions**:
```python
await pilot.hover("#widget-id")                    # Hover simulation
await pilot.hover(offset=(x, y))                   # Hover at coordinates
await pilot.pause(delay=0.5)                       # Wait for async processing
await pilot.resize_terminal(width, height)         # Change screen size
```

### Asserting Widget State

**Property Checks**:
```python
assert widget.visible is True
assert widget.pseudo_classes == {"focus", "enabled", "dark"}
assert button.styles.background != initial_background
assert app.return_code == 0
```

**Query-Based Access**:
```python
widget = app.query_one("#id", Button)              # Get by selector + type
widgets = app.query(".class", Input)               # Get multiple
child = app.get_child_by_type(Label)               # Get by type
```

### Testing Screens and Navigation

**Screen Management Methods**:
```python
app.push_screen(MyScreen())
app.push_screen("screen_name")
app.pop_screen()
app.switch_screen("new_screen")
result = await app.push_screen_wait(MyScreen())   # Wait for result
```

### Async Testing Patterns

**Message Processing**:
```python
await pilot.press("key")
await pilot.pause()                                # Wait for pending messages
assert app.state == expected                       # Now safe to assert
```

**Timing Control**:
```python
await pilot.pause(delay=0.5)                       # Explicit delay
await pilot.wait_for_animation()                   # Wait for animations
await pilot.wait_for_scheduled_animations()        # Wait for all scheduled
```

### Snapshot Testing

**Installation**: `pip install pytest-textual-snapshot`

**Basic Pattern**:
```python
def test_app_appearance(snap_compare):
    assert snap_compare("path/to/app.py")
```

**Advanced Options**:
```python
# Simulate input before snapshot
assert snap_compare("app.py", press=["1", "2", "3"])

# Custom terminal size
assert snap_compare("app.py", terminal_size=(50, 100))

# Run setup code before capture
async def run_before(pilot):
    await pilot.hover("#widget-id")

assert snap_compare("app.py", run_before=run_before)
```

### Testing Best Practices

| Practice | Pattern |
|----------|---------|
| **Always pause after interaction** | `await pilot.pause()` before assertions |
| **Combine assertion + snapshot tests** | Unit tests for logic, snapshots for visual |
| **Use CSS selectors for precise targeting** | `await pilot.click("#specific-widget")` |
| **Test with different screen sizes** | `run_test(size=(width, height))` |
| **Validate state, not just output** | Assert widget properties after each interaction |
| **Test action handlers** | Click buttons and assert that actions executed |

### Example Test Workflow

```python
async def test_button_click_action():
    """Test that clicking button triggers action."""
    action_executed = False

    class MyApp(App):
        def action_do_something(self):
            nonlocal action_executed
            action_executed = True

    app = MyApp()
    async with app.run_test() as pilot:
        button = app.query_one("#my-button", Button)

        await pilot.click(button)                  # Simulate click
        await pilot.pause()                        # Wait for action

        assert action_executed is True             # Verify result
```

### Key Exceptions

- **`OutOfBounds`**: Raised when clicking outside visible screen
- **`WaitForScreenTimeout`**: Potential deadlock—messages not processing
- **`ScreenStackError`**: Attempted to pop the last screen

### Default Screen Size

Testing uses 80×24 character terminal by default. Override with:
```python
async with app.run_test(size=(100, 50)) as pilot:
    # Test with 100 columns × 50 lines
```

---

## 3. Screen Architecture

### Screen vs ModalScreen

| Aspect | Screen | ModalScreen |
|--------|--------|------------|
| **Behavior** | Regular container; app bindings work | Prevents app-level key bindings |
| **Visual** | Full screen content | Semi-transparent overlay (dimmed background) |
| **Use Case** | Major UI sections, main app flow | Dialogs, confirmations, temporary overlays |
| **Generic Type** | `Screen[None]` by default | `ModalScreen[ReturnType]` for type safety |

### Screen Lifecycle

Screens exist in a **stack-based system**:
1. **Created**: `compose()` method yields widgets
2. **Activated**: Pushed to stack (becomes active), receives input events
3. **Inactive**: Covered by another screen (still rendered but no input)
4. **Removed**: Popped or switched; cleaned up unless referenced elsewhere

Note: Screens always occupy full terminal dimensions (no resizing).

### Passing Data Between Screens

**Pattern 1: Callback Functions** (Traditional)
```python
# Child screen dismisses with data
self.dismiss(result_data)

# Parent passes callback
self.push_screen(ChildScreen(), callback_function)
```

**Pattern 2: Async Wait** (Modern, cleaner flow)
```python
@work
async def on_mount(self) -> None:
    result = await self.push_screen_wait(ChildScreen())
    # Continue here with result
```

**Type Safety**: Use generics to declare return types:
```python
class MyScreen(ModalScreen[str]):  # Returns str
    def dismiss(self, result: str) -> None:
        super().dismiss(result)
```

### Screen Stack Operations

- **`push_screen(screen, callback=None)`** - Add screen to stack (preserves underlying)
- **`pop_screen()`** - Remove top screen; minimum 1 screen must remain
- **`switch_screen(screen)`** - Replace top screen (no stack entry, can't return)
- **`push_screen_wait(screen)`** - Async pattern; wait for result in worker context

### Multiple Screens vs Modes

**Single Stack (Normal)**

- Use `push_screen()` / `pop_screen()` for navigation
- Suitable for hierarchical flows (menu → details → confirmation)
- History preserved in stack

**Modes (Multiple Stacks)**

- Define `MODES = {"dashboard": Dashboard, "settings": Settings, ...}`
- Each mode has its own push/pop history
- Use `switch_mode()` to navigate between independent sections
- Suited for apps with separate domains that don't interact

### Key Design Principles

1. **Screens are unaware of callers** - Use callbacks/results, not direct references
2. **Result callbacks enable reusability** - Same screen works in different contexts
3. **Type safety matters** - Use `ModalScreen[T]` generics for IDE support
4. **Async/await is cleaner** - `push_screen_wait()` in workers beats callback chains
5. **Modes scale independent flows** - Don't mix push/pop stacks when you need isolation

---

## 4. Workers and Async

### @work Decorator Usage

**Basic syntax:**
```python
@work(exclusive=True)
async def background_task(self):
    # async code
```

**Key parameters:**

- `exclusive=True` - Cancels previous workers in the same group (prevents race conditions)
- `thread=True` - Runs regular function in a thread (for blocking I/O)
- `name` - Identifier for the worker
- `group` - Groups workers for exclusive control (default: 'default')
- `exit_on_error` - Terminates app on exception (default: True)

When decorated, calling the method automatically creates and starts a worker—no need for explicit `await`.

### Thread Workers vs Async Workers

**Async workers (default):**

- Run as asyncio coroutines on the event loop
- Best for async libraries (httpx, aiohttp, async database drivers)
- Non-blocking; doesn't freeze UI
- Use `await` for async operations

**Thread workers (`thread=True`):**

- Execute in a separate thread pool
- Best for blocking libraries (urllib, synchronous database calls, CPU-heavy work)
- Use `get_current_worker()` inside the worker to check cancellation status
- **Critical:** Must use `app.call_from_thread()` to safely update UI from threads

### Updating UI from Workers

**For async workers:**

- Direct UI updates are safe
- Can await async operations, then modify widgets

**For thread workers:**

- Use `app.call_from_thread(callback)` to safely update UI
- Example: `self.app.call_from_thread(self.update_label, new_value)`
- Prevents race conditions between thread and UI event loop

### Cancellation and Cleanup

**Checking if cancelled:**

- Inside worker: `get_current_worker().is_cancelled`
- From outside: `worker.cancel()` requests cancellation

**Important:** Cancelled workers may still be running. Check `is_cancelled` before applying results:
```python
@work(thread=True)
def long_task(self):
    worker = get_current_worker()
    if not worker.is_cancelled:
        self.app.call_from_thread(self.update_ui)
```

**Automatic cleanup:**

- Workers tied to parent widget are automatically cleaned up when widget is removed
- Cancelled workers emit `Worker.StateChanged` events

### Progress Reporting

**Worker progress tracking:**

- `worker.update(completed_steps=n, total_steps=m)` - Set absolute progress values
- `worker.advance(n)` - Increment completed steps by n
- `worker.progress` - Returns float 0.0-100.0 for UI display

**State changes:**

- Emit `Worker.StateChanged` events as workers transition between states
- Access final result via `worker.result` (SUCCESS) or `worker.error` (ERROR)

### Worker State Management

**Worker states (WorkerState enum):**

- `PENDING` → `RUNNING` → `CANCELLED | ERROR | SUCCESS`

**Handling state changes:**
```python
def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
    if event.worker.is_finished:
        if event.worker.state == WorkerState.SUCCESS:
            result = event.worker.result
        elif event.worker.state == WorkerState.ERROR:
            error = event.worker.error
```

**Race condition prevention:**

- `exclusive=True` on decorator cancels prior workers—essential for search/filter scenarios
- Prevents outdated responses overwriting newer requests

### Key Takeaways

- Textual manages concurrency at a high level; no manual thread/task management needed
- @work decorator is the primary pattern; much cleaner than run_worker()
- Always use `exclusive=True` for user-driven operations (searches, API calls)
- Thread workers require `call_from_thread()` for UI updates—non-negotiable for thread safety
- Progress tracking via worker.update() and advance() enables responsive progress indicators
- Handle Worker.StateChanged events instead of blocking waits for completion

---

## 5. Widgets and Messages

### Custom Widget Creation

**Two Primary Approaches:**

- **Render-based widgets**: Implement `render()` method returning Rich renderables. Use for simple content display. Auto-refresh when reactive properties change.

- **Compose-based widgets** (compound widgets): Implement `compose()` method yielding child widgets. Build complex UIs from widget composition. No `render()` method needed.

- **Hybrid approach**: Implement both `render()` and `compose()`. The render provides background/decoration while composed widgets layer on top.

**Base Classes:**

- `Widget`: Direct base class with full flexibility
- `Static`: Recommended for most cases—caches render results and provides `update()` method

**Widget Lifecycle:**
1. `__init__()` - Basic initialization and parameter storage
2. `compose()` - Declare child widgets (if any)
3. `on_mount()` - Final setup after composition complete; assign reactive properties here
4. `render()` - Generate display content (called when reactive properties change)

### Message System (Posting & Handling)

**Message Flow:**
Messages queue sequentially and process through handlers without blocking. Bubble up DOM hierarchy by default (stop with `message.stop()`).

**Creating Custom Messages:**
```python
class MyWidget(Static):
    class MyMessage(Message):
        """Custom message class."""
        def __init__(self, data: str) -> None:
            super().__init__()
            self.data = data

    def post_custom_message(self) -> None:
        self.post_message(self.MyMessage("payload"))
```

**Handler Naming Convention:**

- Pattern: `on_[namespace_]message_name` (CamelCase → snake_case)
- Example: `class ColorButton.Selected(Message)` → handler `on_color_button_selected`
- Can be async coroutines for concurrent operations

**Alternative: @on Decorator:**
```python
@on(MyWidget.MyMessage)
def handle_my_message(self, message: MyWidget.MyMessage) -> None:
    # Handle the message
```

Supports CSS selectors to filter which widgets trigger handlers.

### Bindings & Actions

**Key Bindings:**
Define as `BINDINGS` class variable (list of tuples):
```python
BINDINGS = [
    ("d", "toggle_dark", "Toggle dark mode"),
    ("q", "quit", "Quit app"),
]
```

**Action Methods:**

- Prefixed with `action_` on App, Screen, or Widget
- Can accept typed parameters: `action_set_color(self, color: str)`
- Can be sync or async coroutines
- Support namespacing: `"app.action_name()"`, `"screen.action_name()"`, `"focused.action_name()"`

**Binding Features:**

- Bind multiple keys: comma-separated (`"ctrl+c,q"`)
- Priority bindings: app-level hotkeys override lower scopes
- Dynamic availability: `check_action()` returns True/False/None to enable/hide/disable

**Binding Scope Resolution:**
Textual checks bindings from focused widget upward through DOM to App.

### Widget Composition Patterns

**Container Types:**

- **Expanding** (`Horizontal`, `Vertical`): Fill available space, resize responsively
- **Group** (`HorizontalGroup`, `VerticalGroup`): Fit to content, compact sizing
- **Scrolling** (`HorizontalScroll`, `VerticalScroll`): Auto-add scrollbars
- **Alignment** (`Center`, `Right`, `Middle`): Positional alignment

**Composition via Context Manager:**
```python
from textual.containers import Horizontal, Vertical

def compose(self) -> ComposeResult:
    with Vertical():
        yield Header()
        with Horizontal():
            yield Sidebar()
            yield Content()
        yield Footer()
```

**"Attributes Down, Messages Up" Pattern:**

- Parent updates child via attributes/method calls
- Child notifies parent via custom messages
- Ensures unidirectional data flow and reusability

### DataTable Best Practices

**Data Management:**

- Add columns: `add_column(label, key=None)` or `add_columns(*labels)`
- Add rows: `add_row(*cells, key=None)` or `add_rows(*rows)`
- Row keys enable reference regardless of sort/filter state
- Update cells: `update_cell(row_key, column_key, value)`
- Remove: `remove_row(row_key)` or `clear()`

**Navigation Modes:**
Four cursor types: `"cell"`, `"row"`, `"column"`, `"none"`

**Styling & Configuration:**

- Cells accept Rich renderables (`Text` objects for styling)
- `show_header`, `show_cursor` - toggle visibility
- `zebra_stripes` - alternate row colors
- `fixed_rows`, `fixed_columns` - freeze headers during scroll

**Events (Messages):**

- `CellSelected`, `RowSelected`, `ColumnSelected` - user selection
- `CellHighlighted`, `RowHighlighted` - during navigation

**Loading State:**
Set `widget.loading = True` to show animated loading indicator.

### Widget Initialization Best Practices

- Call `super().__init__()` when overriding `__init__` in compound widgets
- Store constructor parameters as instance attributes
- Pass `id` through to parent class via `super().__init__(id=id)`
- Avoid accessing widgets in `__init__`—wait for `on_mount()`
- Don't assign reactive properties in `__init__` (causes "widget not found" errors)

---

## 6. Widget Gallery

Complete list of available Textual widgets:

| # | Widget | Description | Key Features |
|---|--------|-------------|--------------|
| 1 | **Button** | Simple button with semantic styling | Default, primary, success, warning, error variants |
| 2 | **Checkbox** | Classic checkbox for binary selections | Multiple items, toggle selections |
| 3 | **Collapsible** | Content that toggles on/off | Expandable/collapsible sections |
| 4 | **ContentSwitcher** | Switches between child widgets | Tab-like content switching |
| 5 | **DataTable** | Powerful data table | Tabular data, configurable cursors |
| 6 | **Digits** | Display numbers in tall characters | Dashboards, prominent numbers |
| 7 | **DirectoryTree** | Tree view of files/folders | File browser, hierarchical |
| 8 | **Footer** | Display app key bindings | Keyboard shortcuts, help |
| 9 | **Header** | Display app title/subtitle | App branding, navigation |
| 10 | **Input** | Single-line text entry | Text input, form fields |
| 11 | **Label** | Simple text label | Status messages, descriptions |
| 12 | **Link** | Clickable link for URLs | Navigation, external links |
| 13 | **ListView** | Display list of items | Dynamic lists, item selection |
| 14 | **LoadingIndicator** | Loading animation | Loading states, progress |
| 15 | **Log** | Display/update text lines | Log files, scrolling output |
| 16 | **Markdown** | Display markdown | Documentation, formatted text |
| 17 | **MarkdownViewer** | Interactive markdown viewer | Navigation, TOC |
| 18 | **MaskedInput** | Template-based text input | Phone numbers, dates |
| 19 | **OptionList** | Vertical list of options | Selectable lists, menus |
| 20 | **Placeholder** | Placeholder content | Mockups, layout prototyping |
| 21 | **Pretty** | Pretty-formatted display | Formatted data output |
| 22 | **ProgressBar** | Configurable progress | Task progress, ETA |
| 23 | **RadioButton** | Simple radio button | Single choice selection |
| 24 | **RadioSet** | Mutually exclusive radios | Grouped radio selections |
| 25 | **RichLog** | Scrolling text panel | Formatted log output |
| 26 | **Rule** | Separator rule | Visual content separation |
| 27 | **Select** | Dropdown selection | Choice selection, compact menus |
| 28 | **SelectionList** | Multi-value selection | Multi-select, checkbox lists |
| 29 | **Sparkline** | Sparkline data display | Compact visualization, trends |
| 30 | **Static** | Simple static content | Foundation for custom widgets |
| 31 | **Switch** | On/off toggle control | Boolean settings, toggles |
| 32 | **Tabs** | Row of tabs | Tab navigation |
| 33 | **TabbedContent** | Tabs + ContentSwitcher | Static content navigation |
| 34 | **TextArea** | Multi-line text with syntax highlighting | Code editing, large text |
| 35 | **Tree** | Tree with expandable nodes | Hierarchical data |

### Widget Categories

- **Input Controls**: Button, Checkbox, Input, MaskedInput, RadioButton, RadioSet, Select, SelectionList, Switch
- **Display**: Label, Link, Markdown, MarkdownViewer, Pretty, Static
- **Lists/Trees**: DirectoryTree, ListView, OptionList, Tree
- **Data**: DataTable, Sparkline
- **Containers**: Collapsible, ContentSwitcher, TabbedContent, Tabs
- **Text**: Log, RichLog, TextArea
- **Layout/Navigation**: Footer, Header, Rule
- **Status**: Digits, LoadingIndicator, ProgressBar
- **Utility**: Placeholder

---

## 7. How-To Guides

### Available Guides

| Guide | Description | Key Patterns |
|-------|-------------|--------------|
| **Center things** | Centering elements in Textual apps | Layout alignment, widget positioning |
| **Design a Layout** | Creating and structuring layouts | Layout planning, widget arrangement |
| **Package with Hatch** | Distributing Textual apps | Python packaging, Hatch config, deployment |
| **Render and compose** | Distinguishing `render()` vs `compose()` | Render for Rich renderables, compose for compound widgets, hybrid approach |
| **Style Inline Apps** | Styling apps running inline (below prompt) | `:inline` pseudo-selector, height/border adjustments |
| **Save time with containers** | Leveraging container components | Container usage, composition patterns |

### Render vs Compose

**Use `render()` for:**

- Returning Rich renderables (text, Table, LinearGradient)
- Simple content display
- Custom animated widgets

**Use `compose()` for:**

- Building compound widgets from other widgets
- Complex UI structures
- Reusable widget combinations

**Hybrid approach:**

- `render()` provides background/decoration
- `compose()` adds widgets on top

---

## Quick Reference

### Essential Patterns for cis-bench TUI

1. **SPA Architecture**: ONE App, multiple Screens, shared state
2. **Screen Stack**: `push_screen()` → work → `pop_screen()` for navigation
3. **Modal for Dialogs**: `ModalScreen` for confirmations/loading
4. **Thread Workers**: `@work(thread=True)` for blocking I/O + `call_from_thread()` for UI updates
5. **Progress Tracking**: `worker.update(completed, total)` for progress bars
6. **Testing**: `async with app.run_test() as pilot` + `await pilot.pause()` before assertions
7. **Base Classes**: Inherit from common base (like `BaseBrowserScreen`) for DRY code
8. **Reactive State**: Use `reactive()` for automatic UI updates
9. **Messages Up, Attributes Down**: Unidirectional data flow

### Common Gotchas

- Don't access widgets in `__init__`—wait for `on_mount()`
- Don't assign reactive properties in `__init__`
- Always `await pilot.pause()` after interactions in tests
- Use `exclusive=True` on workers to prevent race conditions
- Thread workers MUST use `call_from_thread()` for UI updates
- Screens always occupy full terminal (no resizing)
- Minimum 1 screen must remain in stack
