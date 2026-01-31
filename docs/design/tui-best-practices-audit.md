# TUI Best Practices Audit

Audit of cis-bench TUI code against Textual framework best practices.

**Audit Date**: 2026-01-30
**Reference**: `docs/design/textual-framework-research.md`
**Status**: ✅ ALL ISSUES FIXED

---

## Issues Found and Fixed

### Critical/High Priority (Must Fix)

| # | File | Lines | Issue | Status |
|---|------|-------|-------|--------|
| 1 | test_tui_workflows.py | 151-154 | Loop without pause between backspace iterations | ✅ Fixed - Changed to atomic multi-key press |
| 2 | test_tui_workflows.py | 283-284 | down+space without pause between | ✅ Fixed - Added pause after cursor move |
| 3 | test_tui_workflows.py | 414-416 | space+down+space without pauses between | ✅ Fixed - Added pauses between each action |
| 4 | widgets.py | 81 | HelpScreen uses `pop_screen()` instead of `dismiss(None)` | ✅ Fixed - Uses `dismiss(None)` now |

### Medium Priority (Should Fix)

| # | File | Lines | Issue | Status |
|---|------|-------|-------|--------|
| 5 | catalog/app.py | Multiple | Missing `get_current_worker().is_cancelled` checks | ✅ Fixed - Both workers now check worker cancellation |
| 6 | widgets.py | 239-272 | LoadingModal should cache widget refs in `on_mount()` | ✅ Fixed - Caches `_progress_bar` and `_status_widget` |
| 7 | test_tui_workflows.py | 140-141, etc | typing+enter could use pause between | ✅ Fixed - Added pause after typing |

### Low Priority (Nice to Have)

| # | File | Lines | Issue | Status |
|---|------|-------|-------|--------|
| 8 | widgets.py | 84, 115 | SaveDialog/JumpDialog missing generic type | ✅ Fixed - Added `ModalScreen[str \| None]` |
| 9 | catalog/actions.py | 63 | ActionMenu missing generic type | ✅ Fixed - Added `ModalScreen[tuple[str, dict] \| None]` |

---

## Detailed Findings from Agent Reviews

### 1. Worker/Async Patterns Review

**File**: `src/cis_bench/cli/commands/tui/catalog/app.py`

**What was correct:**

- ✓ `@work(exclusive=True, thread=True)` decorator prevents race conditions
- ✓ ALL UI updates use `call_from_thread()` - no direct modifications
- ✓ Modal cleanup with proper try/except
- ✓ Early return pattern on cancellation checks

**What needed fixing:**

- ⚠️ Missing `get_current_worker().is_cancelled` checks
  - Only checked `modal.is_cancelled` (UI state)
  - Should also check worker's own cancellation status

**Best Practice Pattern:**
```python
from textual.worker import get_current_worker

@work(exclusive=True, thread=True)
def _start_view_worker(self, benchmark_id: str) -> None:
    worker = get_current_worker()  # Get worker reference
    modal = getattr(self, "_loading_modal", None)

    # Check worker cancellation before long operations
    if worker.is_cancelled:
        return

    # Check both worker and modal after long operations
    if worker.is_cancelled or (modal and modal.is_cancelled):
        return

    # Only update UI if not cancelled
    if not worker.is_cancelled:
        self.call_from_thread(self.update_ui)
```

### 2. Screen/Navigation Patterns Review

**File**: `src/cis_bench/cli/commands/tui/widgets.py`

**What was correct:**

- ✓ ModalScreen used for dialogs
- ✓ `dismiss()` used in SaveDialog and JumpDialog
- ✓ Screen stack managed correctly

**What needed fixing:**

- ⚠️ HelpScreen used `self.app.pop_screen()` instead of `self.dismiss(None)`
- ⚠️ Modal screens missing generic type annotations

**Best Practice Pattern:**
```python
# Correct: Use dismiss() to close ModalScreen
class HelpScreen(ModalScreen[None]):  # Generic type annotation
    def action_dismiss(self) -> None:
        self.dismiss(None)  # Not self.app.pop_screen()

class SaveDialog(ModalScreen[str | None]):  # Type annotation
    def action_cancel(self) -> None:
        self.dismiss(None)
```

**Widget access pattern:**
```python
def on_mount(self) -> None:
    # Cache widget references for thread-safe access
    self._progress_bar = self.query_one("#loading-progress", ProgressBar)
    self._status_widget = self.query_one("#loading-status", Static)
    self._mounted = True

def update_progress(self, progress: int, status: str = "") -> None:
    if not self._mounted:
        return
    # Use cached references instead of querying each time
    self._progress_bar.update(progress=progress)
```

### 3. Testing Patterns Review

**File**: `tests/integration/test_tui_workflows.py`

**What was correct:**

- ✓ Uses `async with app.run_test() as pilot`
- ✓ CSS selectors for precise targeting (`#changes-table`, `#detail-view`)
- ✓ Type hints on query operations
- ✓ Unit tests properly use mocking

**What needed fixing:**

- ⚠️ Missing pause BETWEEN multi-step state changes
- ⚠️ Loop without pause inside (rapid-fire backspace)
- ⚠️ Typing + submit without intermediate pause

**Best Practice Patterns:**

```python
# WRONG: No pause between dependent actions
await pilot.press("down")
await pilot.press("space")  # May select wrong item
await pilot.pause()

# CORRECT: Pause between dependent actions
await pilot.press("down")
await pilot.pause()  # Ensure cursor moved
await pilot.press("space")
await pilot.pause()  # Ensure selection processed

# WRONG: Loop without pauses
for _ in range(10):
    await pilot.press("backspace")
await pilot.press("enter")

# CORRECT: Atomic multi-key or pause between
await pilot.press(
    "backspace", "backspace", "backspace", "backspace", "backspace",
    "backspace", "backspace", "backspace", "backspace", "backspace"
)
await pilot.pause()  # Pause before submit
await pilot.press("enter")

# WRONG: Type then immediately submit
await pilot.press("u", "b", "u", "n", "t", "u")
await pilot.press("enter")

# CORRECT: Pause after typing, before submit
await pilot.press("u", "b", "u", "n", "t", "u")
await pilot.pause()  # Let filter apply
await pilot.press("enter")
await pilot.pause()
```

---

## Key Patterns to Follow

### 1. Always Pause After Interactions
```python
await pilot.press("key")
await pilot.pause()  # ALWAYS before assertions
assert widget.state == expected
```

### 2. Pause Between Dependent Actions
```python
await pilot.press("down")   # Move cursor
await pilot.pause()          # Wait for move
await pilot.press("space")   # Then select
await pilot.pause()          # Wait for select
```

### 3. Use Worker Cancellation Checks
```python
worker = get_current_worker()
if worker.is_cancelled:
    return  # Early exit
```

### 4. Use dismiss() for ModalScreen
```python
self.dismiss(result)  # NOT self.app.pop_screen()
```

### 5. Add Generic Type Annotations
```python
class MyModal(ModalScreen[ReturnType]):
    pass
```

### 6. Cache Widget References
```python
def on_mount(self):
    self._widget = self.query_one("#id", WidgetType)
```

---

## Verification

All 1349 tests pass after fixes:
```
=========== 1349 passed, 2 xfailed, 26 warnings in 84.50s ============
```

Files modified:

- `tests/integration/test_tui_workflows.py` - Testing pattern fixes
- `src/cis_bench/cli/commands/tui/widgets.py` - Modal patterns, caching
- `src/cis_bench/cli/commands/tui/catalog/app.py` - Worker cancellation
- `src/cis_bench/cli/commands/tui/catalog/actions.py` - Type annotation
- `src/cis_bench/cli/commands/tui/screens.py` - Inheritance refactor (earlier)
