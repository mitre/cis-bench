# XCCDF Export Refactoring Plan - Generic Structure Handlers

**Date:** December 16, 2025
**Goal:** Make ALL structure generation config-driven, not hard-coded
**Scope:** DISA and CIS exports working with zero hard-coded structures

---

## Problem Statement

### Design Principle Violation

**Our Design Philosophy (design-philosophy.md):**
> "Config-Driven Over Hard-Coded... Clear separation between data (YAML) and logic (Python)"

**Current Violation:**
- CIS Controls metadata generation is HARD-CODED in `build_cis_controls()` method
- MITRE metadata was HARD-CODED in `_inject_enhanced_metadata()`
- Structure logic embedded in Python instead of YAML config

**Impact:**
- Adding PCI-DSS, ISO 27001 requires CODE changes
- Cannot test structure generation independently
- Violates DRY - specific methods instead of generic

---

## Current State Analysis

### Existing Structure Handlers

| Handler | Purpose | Status | Action |
|---------|---------|--------|--------|
| `embedded_xml_tags` | VulnDiscussion tags | Used by DISA | **Keep** (DISA-specific) |
| `nested` | check/check-content | Used by both | **Keep** (simple nesting) |
| `dublin_core` | NIST references | Used by both | **Keep** (DC standard) |
| `ident_from_list` | Generic ident generation | NEW ✓ | **Done** ✓ |
| `cis_controls_ident` | CIS idents (old) | DELETED | **Done** ✓ |
| `official_cis_controls` | CIS metadata (old) | DELETED | **Replace with generic** |
| `enhanced_namespace` | MITRE metadata (old) | DELETED | **Replace with generic** |
| `custom_namespace` | Generic metadata (old) | DELETED | **Replace with generic** |

### What CIS Needs (vs DISA)

| Data | DISA Format | CIS Format |
|------|-------------|------------|
| CIS Controls | `<ident system="...">8:3.14</ident>` | `<ident>` + `<metadata><cis_controls>...</cis_controls></metadata>` |
| MITRE ATT&CK | `<ident system="...">T1565</ident>` | Same (use ident) |
| Profiles | `<Profile>` at Benchmark | `<Profile>` at Benchmark |

**CIS needs CIS Controls in BOTH ident AND metadata (dual representation)**

---

## Design Solution

### Generic Structure Handler: `metadata_from_config`

**Principle:** Build ANY nested XML structure from YAML specification

**Config Pattern:**
```yaml
field_name:
  target_element: "metadata"
  structure: "metadata_from_config"
  source_field: "cis_controls"
  metadata_spec:
    root_element: "cis_controls"
    namespace: "http://cisecurity.org/controls"
    group_by: "item.version"  # Group items by version
    levels:
      - element: "framework"
        attributes:
          urn: "urn:cisecurity.org:controls:{group_key}"
        children:
          - element: "safeguard"
            for_each: "group_items"
            attributes:
              title: "{item.title}"
              urn: "urn:cisecurity.org:controls:{item.version}:{item.control}"
            children:
              - element: "implementation_groups"
                attributes:
                  ig1: "{item.ig1}"
                  ig2: "{item.ig2}"
                  ig3: "{item.ig3}"
              - element: "asset_type"
                content: "Unknown"
              - element: "security_function"
                content: "Protect"
```

**One Generic Implementation:**
```python
def generate_metadata_from_config(
    self,
    recommendation: Recommendation,
    field_mapping: dict
) -> Any:
    """Build ANY nested XML metadata structure from YAML config.

    Works for:
    - CIS Controls nested structure
    - MITRE ATT&CK (if we wanted metadata instead of idents)
    - PCI-DSS requirements hierarchy
    - ISO 27001 controls
    - Any future framework
    """
```

---

## Implementation Plan

### PHASE 0: Design & Validation (BEFORE coding)

**Task 0.1:** Review all existing structure handlers
- [x] `ident_from_list` - Generic idents (DONE)
- [ ] `embedded_xml_tags` - Can this be generalized?
- [ ] `nested` - Can this be generalized?
- [ ] `dublin_core` - Can this be generalized?

**Task 0.2:** Create unified specification
- [ ] Document `metadata_from_config` pattern
- [ ] Document how it handles grouping (group_by)
- [ ] Document how it handles nesting (levels/children)
- [ ] Document attribute templates
- [ ] Document content templates

**Task 0.3:** Map all use cases to generic patterns
- [ ] CIS Controls → `metadata_from_config`
- [ ] MITRE (if metadata needed) → `metadata_from_config`
- [ ] VulnDiscussion → Keep `embedded_xml_tags` (too specific)
- [ ] Check/check-content → Can use `metadata_from_config` with nesting?
- [ ] Dublin Core → Can use `metadata_from_config`?

**Task 0.4:** Review design with user
- [ ] Present complete design
- [ ] Get approval before coding
- [ ] Ensure no missing cases

---

### PHASE 1: Implement Generic Handlers (TDD)

**Task 1.1:** Write tests FIRST for `metadata_from_config`
- [ ] Test simple nested structure
- [ ] Test grouping by field (group_by)
- [ ] Test attribute substitution
- [ ] Test content substitution
- [ ] Test CIS Controls structure specifically
- [ ] Test with mock PCI-DSS data

**Task 1.2:** Implement `generate_metadata_from_config()` method
- [ ] Handle source_field extraction
- [ ] Handle grouping logic (group_by)
- [ ] Handle nested children recursively
- [ ] Handle attribute templates
- [ ] Handle content templates
- [ ] Use existing VariableSubstituter

**Task 1.3:** Add handler to mapping loop
- [ ] Add `if structure == "metadata_from_config":` block
- [ ] Call generic method
- [ ] Store result appropriately

**Task 1.4:** Verify tests pass
- [ ] All new tests GREEN
- [ ] No regressions

---

### PHASE 2: Update Configurations

**Task 2.1:** Update cis_style.yaml
- [ ] Add CIS Controls as ident (with cc7/cc8 attributes)
- [ ] Add CIS Controls as metadata (nested structure)
- [ ] Add MITRE as ident (not metadata)
- [ ] Add Profiles config
- [ ] Remove old structure references

**Task 2.2:** Verify disa_style.yaml
- [ ] Already uses ident_from_list ✓
- [ ] Already has profiles ✓
- [ ] No metadata for compliance data ✓

**Task 2.3:** Update base_style.yaml
- [ ] Document all generic patterns
- [ ] Add examples for each handler type

---

### PHASE 3: Integration Testing

**Task 3.1:** Test DISA exports
- [ ] Generate export
- [ ] Verify structure: idents only, no metadata
- [ ] Verify profiles at benchmark level
- [ ] Verify namespace: single declaration at root
- [ ] Count idents: CCI, CIS Controls, MITRE
- [ ] All DISA tests pass

**Task 3.2:** Test CIS exports
- [ ] Generate export
- [ ] Verify structure: idents AND metadata
- [ ] Verify profiles at benchmark level
- [ ] Verify namespaces properly declared
- [ ] Compare to official CIS XCCDF structure
- [ ] All CIS tests pass

**Task 3.3:** Verify both styles work
- [ ] Run full integration test suite
- [ ] No test failures
- [ ] No skipped tests that should pass

---

### PHASE 4: Add Comprehensive Regression Tests

**Task 4.1:** DISA structure tests
- [ ] Test: DISA has zero metadata elements
- [ ] Test: DISA has CIS/MITRE as idents
- [ ] Test: DISA namespace declared once at root
- [ ] Test: DISA structure matches official STIG pattern
- [ ] Test: DISA profiles match CIS Level mappings

**Task 4.2:** CIS structure tests
- [ ] Test: CIS has metadata for CIS Controls
- [ ] Test: CIS has idents for CIS Controls (dual representation)
- [ ] Test: CIS has idents for MITRE (not metadata)
- [ ] Test: CIS structure matches official CIS XCCDF
- [ ] Test: CIS profiles generated correctly

**Task 4.3:** Generic pattern tests
- [ ] Test: ident_from_list with mock PCI-DSS data
- [ ] Test: metadata_from_config with mock ISO 27001 data
- [ ] Test: Extensibility (add new framework via config only)

**Task 4.4:** Architecture compliance tests
- [ ] Test: No hard-coded structure names in code
- [ ] Test: All structures come from config
- [ ] Test: Adding new framework requires zero code changes

---

### PHASE 5: Update Documentation

**Task 5.1:** Update design-philosophy.md
- [ ] Document DISA uses idents only
- [ ] Document CIS uses idents + metadata
- [ ] Explain dual representation pattern
- [ ] Update architecture diagrams

**Task 5.2:** Update mapping-engine-design.md
- [ ] Document `ident_from_list` pattern fully
- [ ] Document `metadata_from_config` pattern fully
- [ ] Document `generate_profiles_from_rules` pattern
- [ ] Add flowcharts for each handler

**Task 5.3:** Update mapping-engine-guide.md
- [ ] Add "How to use ident_from_list" section
- [ ] Add "How to use metadata_from_config" section
- [ ] Add "How to generate Profiles" section
- [ ] Add complete examples

**Task 5.4:** Add framework extension guide
- [ ] "How to Add PCI-DSS" complete example
- [ ] "How to Add ISO 27001" example
- [ ] "How to Add HIPAA" example
- [ ] Show zero code changes needed

---

### PHASE 6: Create Example Configurations

**Task 6.1:** Create example_generic_framework.yaml
- [ ] Show all handler types
- [ ] Document all ident_spec options
- [ ] Document all metadata_spec options
- [ ] Document all profile options
- [ ] Include PCI-DSS example
- [ ] Include ISO 27001 example

**Task 6.2:** Add inline documentation
- [ ] Comment every config option
- [ ] Explain templates
- [ ] Explain grouping
- [ ] Explain nesting

---

### PHASE 7: Cleanup & Validation

**Task 7.1:** Remove ALL orphaned code
- [ ] Use LibCST to find unused methods
- [ ] Delete unused imports
- [ ] Delete unused variables
- [ ] Clean up comments

**Task 7.2:** Update logging
- [ ] Remove misleading messages
- [ ] Add ident counts
- [ ] Add profile counts
- [ ] Add metadata counts (for CIS)

**Task 7.3:** Run linters
- [ ] ruff check .
- [ ] ruff format .
- [ ] Fix all issues

**Task 7.4:** Run security scan
- [ ] bandit -c pyproject.toml -r src/
- [ ] Fix any issues

---

### PHASE 8: Full Test Suite

**Task 8.1:** Run all tests
- [ ] pytest tests/ -v
- [ ] All tests pass
- [ ] No skipped tests
- [ ] No warnings

**Task 8.2:** Check coverage
- [ ] pytest --cov=src --cov-report=term
- [ ] Coverage > 80%
- [ ] New code covered

---

### PHASE 9: Real-World Validation (Vulcan)

**Task 9.1:** Export DISA XCCDF
- [ ] Generate from AlmaLinux benchmark
- [ ] Save to issue/ folder for Vulcan testing

**Task 9.2:** Import to Vulcan
- [ ] Upload XCCDF to Vulcan
- [ ] Verify no import errors
- [ ] Check "undefined method 'plaintext'" is fixed
- [ ] Check "rules failed to import" is fixed

**Task 9.3:** Verify InSpec profile
- [ ] Check profile structure
- [ ] Verify tags present: cci, cis_controls, mitre, profiles
- [ ] Verify tag values correct
- [ ] Document any issues

---

### PHASE 10: Final Documentation & PR

**Task 10.1:** Update CHANGELOG.md
- [ ] Document breaking changes
- [ ] Document new generic patterns
- [ ] Document migration guide

**Task 10.2:** Update README.md
- [ ] Update examples if needed
- [ ] Add note about namespace fix

**Task 10.3:** Create comprehensive PR
- [ ] Write detailed description
- [ ] Include before/after XML examples
- [ ] Document architecture decisions
- [ ] Link to issue from user
- [ ] Explain Vulcan compatibility fix

**Task 10.4:** Push and create PR
- [ ] git add files
- [ ] git commit with proper message
- [ ] git push origin fix/xccdf-namespace-ident-refactor
- [ ] gh pr create

---

## Key Checkpoints (MUST PASS)

**After Phase 1:**
- [ ] New generic handlers implemented
- [ ] Unit tests for handlers pass
- [ ] TDD cycle complete (RED → GREEN)

**After Phase 2:**
- [ ] All YAML configs updated
- [ ] No references to deleted code
- [ ] Configs use only generic patterns

**After Phase 3:**
- [ ] DISA export works perfectly
- [ ] CIS export works perfectly
- [ ] Integration tests pass

**Before Phase 9:**
- [ ] All code complete
- [ ] All tests pass
- [ ] All docs updated
- [ ] No tech debt
- [ ] No orphaned code

**Before Phase 10:**
- [ ] Vulcan import successful
- [ ] User's issue resolved
- [ ] Production-ready

---

## Architecture Decision Record

### Why Generic Handlers?

**Problem:** Hard-coded methods for each organization (CIS, MITRE, etc.)

**Solution:** Config-driven generic handlers

**Benefits:**
1. DRY - One implementation, any organization
2. Extensible - Add PCI-DSS via YAML only
3. Testable - Generic tests, not per-org
4. Maintainable - Fix once, works everywhere
5. Config-Driven - Follows our design principles

### Handler Types Needed

1. **ident_from_list** - Simple ident elements ✓ DONE
2. **metadata_from_config** - Nested XML in metadata (NEW)
3. **embedded_xml_tags** - Keep (DISA VulnDiscussion specific)
4. **nested** - Keep (check/check-content)
5. **dublin_core** - Keep (W3C standard)

### Design Decisions

**Decision 1:** CIS Controls in dual format
- **Why:** Official CIS XCCDFs use both ident and metadata
- **Implementation:** Two field mappings (cis_controls_ident, cis_controls_metadata)

**Decision 2:** MITRE as ident only
- **Why:** Simpler, consistent with DISA, no namespace pollution
- **Implementation:** Use ident_from_list for techniques/tactics/mitigations

**Decision 3:** Profiles at Benchmark level
- **Why:** XCCDF standard, matches DISA and CIS official
- **Implementation:** `generate_profiles_from_rules` from recommendation.profiles

**Decision 4:** No metadata for DISA
- **Why:** Real DISA STIGs don't use metadata
- **Implementation:** ident elements only

---

## Testing Strategy

### Unit Tests (New)
- `test_generate_idents_from_config()` - Generic ident generation
- `test_generate_metadata_from_config()` - Generic metadata generation
- `test_generate_profiles_from_rules()` - Profile generation
- `test_metadata_grouping()` - group_by logic
- `test_metadata_nesting()` - Recursive children

### Integration Tests (Update)
- `test_disa_xccdf.py` - Update for idents only
- `test_cis_xccdf.py` - Update for idents + metadata
- `test_profile_generation.py` - Already done ✓

### Regression Tests (New)
- `test_no_hard_coded_structures.py` - Architecture compliance
- `test_namespace_handling.py` - No redeclarations
- `test_structure_comparison.py` - Compare to official XCCDFs
- `test_generic_extensibility.py` - Mock PCI-DSS/ISO tests

---

## Documentation Updates Needed

### Technical Docs
- [ ] design-philosophy.md - Update with generic patterns
- [ ] mapping-engine-design.md - Add handler specifications
- [ ] mapping-engine-guide.md - Add how-to guides
- [ ] ARCHITECTURE.md - Update if exists

### User Guides
- [ ] Add "Adding a New Framework" guide
- [ ] Update YAML config examples
- [ ] Add troubleshooting section

### Examples
- [ ] example_generic_framework.yaml - Complete reference
- [ ] example_pci_dss.yaml - PCI-DSS mapping
- [ ] example_iso27001.yaml - ISO 27001 mapping

---

## File Changes Summary

### Code Files Modified
1. `src/cis_bench/exporters/mapping_engine.py`
   - Add `generate_idents_from_config()` ✓
   - Add `generate_metadata_from_config()` (NEW)
   - Add `generate_profiles_from_rules()` ✓
   - Add `_get_nested_field()` ✓
   - Delete `build_cis_controls()` ✓
   - Delete `generate_cis_idents()` ✓
   - Delete old structure handlers ✓

2. `src/cis_bench/exporters/xccdf_unified_exporter.py`
   - Delete `_inject_cis_controls_metadata()` ✓
   - Delete `_inject_enhanced_metadata()` ✓
   - Update `_apply_cis_post_processors()` ✓
   - Update `_apply_disa_post_processors()` ✓
   - Update logging ✓

### Config Files Modified
1. `src/cis_bench/exporters/configs/disa_style.yaml`
   - Add ident_from_list for CIS Controls ✓
   - Add ident_from_list for MITRE ✓
   - Add profiles configuration ✓
   - Remove metadata references ✓

2. `src/cis_bench/exporters/configs/cis_style.yaml`
   - Add ident_from_list for MITRE (NEW)
   - Add metadata_from_config for CIS Controls (NEW)
   - Add profiles configuration (NEW)
   - Remove old structure references (NEW)

3. `src/cis_bench/exporters/configs/base_style.yaml`
   - Document generic patterns (NEW)
   - Add handler type reference (NEW)

### Test Files Modified
1. `tests/integration/test_profile_generation.py` - NEW ✓
2. `tests/integration/test_disa_xccdf.py` - Update assertions (NEW)
3. `tests/integration/test_cis_xccdf.py` - Update assertions (NEW)
4. `tests/unit/test_mapping_engine.py` - Add new method tests (NEW)
5. `tests/regression/test_structure_compliance.py` - NEW file (NEW)

### Documentation Files Modified
1. `docs/about/design-philosophy.md` - Update patterns
2. `docs/technical-reference/mapping-engine-design.md` - Add handlers
3. `docs/developer-guide/mapping-engine-guide.md` - Add guides
4. `docs/examples/example_generic_framework.yaml` - NEW
5. `docs/examples/adding-pci-dss.md` - NEW
6. `CHANGELOG.md` - Document changes
7. `README.md` - Update if needed

---

## Estimated Work

**Phase 0 (Design):** 30 min - Review and plan
**Phase 1 (Implementation):** 2-3 hours - Generic handlers + tests
**Phase 2 (Configuration):** 1 hour - Update all YAMLs
**Phase 3 (Integration Testing):** 1 hour - Both styles working
**Phase 4 (Regression Tests):** 1 hour - Prevent future breaks
**Phase 5 (Documentation):** 2 hours - Complete docs
**Phase 6 (Examples):** 1 hour - Reference configs
**Phase 7 (Cleanup):** 30 min - Polish
**Phase 8 (Full Suite):** 30 min - All tests
**Phase 9 (Vulcan):** 1 hour - Real-world validation
**Phase 10 (PR):** 30 min - Ship it

**Total: ~10-11 hours of focused work**

---

## Review Checklist Before User Returns

- [x] Identified all structure handlers
- [x] Documented current state
- [x] Designed generic solution
- [x] Created phased plan
- [ ] Ready to review with user
