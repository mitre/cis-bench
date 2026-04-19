# TUI User Stories

This document captures the complete user workflows for the cis-bench TUI.

## Design Principles

- **CLI** = Granular commands for scripting (separate steps for automation)
- **TUI** = Streamlined UX (combines steps transparently)
- **Catalog Browser** = Home base, navigate to other screens and back
- **Back navigation** = Preserve state (position, selection, filters)

---

## Data Interaction

### US-1: View Single Benchmark
**As a** user browsing the catalog
**I want to** view a benchmark's full details
**So that** I can read recommendations, audit steps, remediation

**Flow:**
```
Catalog Browser → scroll/filter → Enter → View Screen → Esc → Back to Catalog
```

**Acceptance:**

- [ ] Enter opens ViewApp with selected benchmark
- [ ] Content fetched transparently if not cached
- [ ] Esc returns to catalog at same position

---

### US-2: Compare Two Versions (Diff)
**As a** user
**I want to** compare two benchmark versions
**So that** I can see what changed between releases

**Flow:**
```
Catalog Browser → filter "AWS" → space (select v2) → space (select v1) → "d" → Diff Screen → Esc → Back
```

**Acceptance:**

- [ ] Space toggles selection (visual indicator)
- [ ] "d" validates exactly 2 selected
- [ ] Error message if not exactly 2
- [ ] DiffApp shows comparison
- [ ] Esc returns to catalog

---

### US-3: Export Single Benchmark
**As a** user
**I want to** save a benchmark in a useful format
**So that** I can use it in other tools (XCCDF for STIG Viewer, etc.)

**Flow:**
```
Catalog Browser → find benchmark → "s" or "e" → Export Dialog → pick format → pick path → Save → Back
```

**Acceptance:**

- [ ] "s" or "e" opens export dialog
- [ ] Format options: JSON, YAML, CSV, Markdown, XCCDF
- [ ] XCCDF shows style sub-option (CIS, DISA)
- [ ] Default filename suggested
- [ ] Content fetched transparently if not cached
- [ ] Success notification

---

### US-4: Batch Export
**As a** user
**I want to** export multiple benchmarks at once
**So that** I can save time on bulk operations

**Flow:**
```
Catalog Browser → filter → select multiple → "s" → Export Dialog → pick format → pick directory → Save all
```

**Acceptance:**

- [ ] Multiple selections supported
- [ ] Export dialog shows count
- [ ] Progress indicator for batch
- [ ] Files saved with appropriate names

---

### US-5: Export While Viewing
**As a** user viewing a benchmark
**I want to** export it without going back
**So that** I can save what I'm looking at

**Flow:**
```
View Screen → "s" → Export Dialog → Save
```

**Acceptance:**

- [ ] "s" works in View screen
- [ ] Same export dialog as catalog

---

### US-6: Export Diff Results
**As a** user viewing a diff
**I want to** save the comparison
**So that** I can share or document changes

**Flow:**
```
Diff Screen → "s" → Export Dialog → Save
```

**Acceptance:**

- [ ] "s" works in Diff screen
- [ ] Exports diff summary/details

---

## Discovery & Search

### US-7: Filter by Text
**As a** user
**I want to** quickly filter the catalog
**So that** I can find relevant benchmarks

**Flow:**
```
Catalog Browser → "/" → type query → results filter live → Esc to clear
```

**Acceptance:**

- [ ] "/" opens search input
- [ ] Live filtering as you type
- [ ] Matches title, platform, description
- [ ] Esc clears filter and closes search
- [ ] Enter keeps filter and returns to list

---

### US-8: Filter by Platform
**As a** user
**I want to** filter by platform type
**So that** I can see only AWS, Ubuntu, Windows, etc.

**Flow:**
```
Catalog Browser → platform filter → select platform → filtered results
```

**Acceptance:**

- [ ] Platform filter option (key TBD)
- [ ] Shows available platforms
- [ ] Multiple platform selection?

---

### US-9: Jump to ID
**As a** user who knows the benchmark ID
**I want to** jump directly to it
**So that** I don't have to scroll/search

**Flow:**
```
Catalog Browser → "g" → enter ID → jump to row
```

**Acceptance:**

- [ ] "g" opens jump dialog
- [ ] Partial match support?
- [ ] Error if not found

---

### US-10: Sort Results
**As a** user
**I want to** sort the catalog differently
**So that** I can find newest, or alphabetical, etc.

**Flow:**
```
Catalog Browser → "r" (reverse) or sort key → reordered list
```

**Acceptance:**

- [ ] "r" reverses current sort
- [ ] Sort by: date, title, platform
- [ ] Visual indicator of current sort

---

## Catalog Maintenance

### US-11: Refresh Catalog
**As a** user
**I want to** update the catalog from CIS WorkBench
**So that** I have the latest benchmarks

**Flow:**
```
Catalog Browser → refresh action → progress → updated catalog
```

**Acceptance:**

- [ ] Refresh keybinding or menu option
- [ ] Progress indicator
- [ ] Shows new/updated count
- [ ] Requires valid auth

---

### US-12: Refresh Authentication
**As a** user with expired cookies
**I want to** re-authenticate
**So that** I can download/refresh

**Flow:**
```
Action fails → auth error shown → refresh auth option → re-auth → retry
```

**Acceptance:**

- [ ] Clear error message when auth fails
- [ ] Option to refresh auth
- [ ] Instructions for browser login
- [ ] Retry after re-auth

---

### US-13: View Catalog Stats
**As a** user
**I want to** see catalog status
**So that** I know how current my data is

**Flow:**
```
Catalog Browser → shows in header/footer: count, last refresh date
```

**Acceptance:**

- [ ] Total benchmark count visible
- [ ] Last refresh date visible
- [ ] Cached/downloaded count?

---

### US-14: Clear Cache
**As a** user
**I want to** clear downloaded content
**So that** I can free space or force re-download

**Flow:**
```
Maintenance action → confirm → cache cleared
```

**Acceptance:**

- [ ] Clear cache option
- [ ] Confirmation required
- [ ] Shows space freed

---

## Batch Operations

### US-15: Select All Filtered
**As a** user
**I want to** select all matching my filter
**So that** I can batch operate on them

**Flow:**
```
Catalog Browser → filter → "a" (select all) → all visible selected
```

**Acceptance:**

- [ ] "a" selects all visible/filtered items
- [ ] "A" or similar deselects all?
- [ ] Count shown in header

---

### US-16: Batch Download for Offline
**As a** user
**I want to** pre-cache multiple benchmarks
**So that** I can work offline later

**Flow:**
```
Catalog Browser → select multiple → cache action → progress → cached
```

**Acceptance:**

- [ ] Cache/pre-fetch action
- [ ] Progress for multiple items
- [ ] Works offline after caching

---

## Navigation

### US-17: Back Navigation (Preserve State)
**As a** user
**I want to** go back and find things as I left them
**So that** I don't lose my place

**Acceptance:**

- [ ] Esc returns to previous screen
- [ ] Cursor position preserved
- [ ] Selection preserved
- [ ] Filter preserved
- [ ] Scroll position preserved

---

### US-18: Help Screen
**As a** user
**I want to** see available keyboard shortcuts
**So that** I can learn the interface

**Flow:**
```
Any screen → "?" → Help overlay → any key → back
```

**Acceptance:**

- [x] "?" shows help (DONE - implemented)
- [x] Shows all bindings
- [x] Context-sensitive (screen-specific bindings)

---

### US-19: Quit
**As a** user
**I want to** exit the TUI
**So that** I can return to my terminal

**Flow:**
```
Any screen → "q" → exit
```

**Acceptance:**

- [x] "q" exits (DONE - implemented)
- [ ] Confirm if unsaved changes?

---

## Gap Analysis

| Story | Status | Beads Card | Notes |
|-------|--------|------------|-------|
| **Data Interaction** |
| US-1: View single | 🔨 In Progress | ep9.8 | Add view action |
| US-2: Diff two | 📋 Open | ep9.9 | Add diff action |
| US-3: Export single | 📋 Open | ep9.7 | Save/Export action |
| US-4: Batch export | ❌ Gap | - | Need new card |
| US-5: Export from View | ❌ Gap | - | 's' key in ViewApp |
| US-6: Export from Diff | ❌ Gap | - | 's' key in DiffApp |
| **Discovery & Search** |
| US-7: Filter by text | ✅ Done | - | Already implemented (/) |
| US-8: Filter by platform | ❌ Gap | - | Platform-specific filter |
| US-9: Jump to ID | ✅ Done | - | Already implemented (g) |
| US-10: Sort results | ✅ Done | - | Already implemented (r) |
| **Catalog Maintenance** |
| US-11: Refresh catalog | ❌ Gap | - | Need TUI trigger |
| US-12: Refresh auth | ❌ Gap | - | Need TUI flow |
| US-13: Catalog stats | ⚠️ Partial | - | Shows count, need date |
| US-14: Clear cache | ❌ Gap | - | Need new card |
| **Batch Operations** |
| US-15: Select all filtered | ❌ Gap | - | Need 'a' binding |
| US-16: Batch download | ❌ Gap | - | Pre-cache for offline |
| **Navigation** |
| US-17: Back (preserve) | ⚠️ Partial | - | Need state preservation |
| US-18: Help | ✅ Done | - | Already implemented (?) |
| US-19: Quit | ✅ Done | - | Already implemented (q) |
| **Other Open Cards** |
| Version grouping | 📋 Open | ep9.11 | Groups versions together |
| Version timeline | 📋 Open | ep9.12 | Timeline visualization |
| Side-by-side diff | 📋 Open | ep9.13 | Enhanced diff view |

## Priority Assessment

**Core Workflow (P1)** - Must have for basic TUI usefulness:

- US-1: View (ep9.8) 🔨
- US-2: Diff (ep9.9)
- US-3: Export (ep9.7)
- US-17: Back navigation with state

**Enhanced Workflow (P2)** - Better UX:

- US-4: Batch export
- US-5/6: Export from View/Diff screens
- US-15: Select all filtered
- ep9.11: Version grouping

**Maintenance (P3)** - Nice to have:

- US-11: Refresh catalog in TUI
- US-12: Auth refresh flow
- US-8: Platform filter
- US-14: Clear cache

**Advanced (P4)** - Future:

- ep9.12: Version timeline
- ep9.13: Side-by-side diff
- US-16: Batch pre-cache
