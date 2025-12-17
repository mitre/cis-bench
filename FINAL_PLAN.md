# FINAL IMPLEMENTATION PLAN - XCCDF Generic Structure Handlers

**Date Created:** December 16, 2025
**Branch:** `fix/xccdf-namespace-ident-refactor`
**Goal:** Fix XCCDF exports to be fully config-driven, resolve Vulcan import issues
**Scope:** Both DISA and CIS exports working perfectly

---

## Architecture Decision Record

### Decision: Use 4 Generic Handlers Only

**Approved:** December 16, 2025
**Decided By:** Aaron Lippold + System Architecture Review

**Final Handler Set:**

1. **ident_from_list** ✅ DONE
   - Purpose: Generate `<ident>` elements from any list
   - Handles: CCIs, CIS Controls, MITRE, PCI-DSS, ISO 27001, etc.
   - Status: Implemented and tested

2. **metadata_from_config** ❌ TO BUILD
   - Purpose: Generate ANY nested XML structure
   - Handles: CIS Controls metadata, VulnDiscussion, check-content, all nesting
   - Modes: Simple nesting, grouping, embedded tags
   - Replaces: embedded_xml_tags, nested, official_cis_controls, enhanced_namespace, custom_namespace
   - Status: Not implemented

3. **generate_profiles_from_rules** ✅ DONE
   - Purpose: Generate Benchmark-level Profile elements
   - Handles: CIS Levels, DISA MAC, any applicability system
   - Status: Implemented and tested

4. **dublin_core** ✅ KEEP
   - Purpose: NIST references with Dublin Core
   - Handles: W3C Dublin Core standard
   - Status: Existing, keep as-is

**Rationale:**
- Follows "Config-Driven Over Hard-Coded" design principle
- Enables zero-code framework addition (PCI-DSS, ISO 27001, HIPAA via YAML only)
- More stable (fix once, works everywhere)
- Easier for contributors (YAML knowledge only)
- One-time complexity investment for forever benefits

---

## Current State (As of Dec 16, 2025 - 2:30 PM)

### ✅ Completed Work

**Code:**
- ✅ `generate_idents_from_config()` implemented in mapping_engine.py
- ✅ `_get_nested_field()` helper implemented
- ✅ `ident_from_list` handler added to mapping loop
- ✅ `generate_profiles_from_rules()` implemented
- ✅ Profile handler added to map_benchmark()
- ✅ Old methods deleted: generate_cis_idents, build_cis_controls
- ✅ Old injection methods deleted: _inject_cis_controls_metadata, _inject_enhanced_metadata
- ✅ Old handlers deleted/deprecated: custom_namespace, enhanced_namespace, official_cis_controls

**Configuration:**
- ✅ disa_style.yaml fully updated (idents + profiles)
- ✅ DISA config uses only generic patterns

**Tests:**
- ✅ tests/integration/test_profile_generation.py created
- ✅ DISA integration tests passing (9 passed, 2 skipped)
- ✅ Profile tests passing (4 tests)

**Tools:**
- ✅ LibCST installed for safe code manipulation

### ❌ Not Completed

**Code:**
- ❌ `generate_metadata_from_config()` not implemented
- ❌ `metadata_from_config` handler not in mapping loop
- ❌ CIS post-processor still placeholder

**Configuration:**
- ❌ cis_style.yaml still uses old patterns
- ❌ base_style.yaml not documented

**Tests:**
- ❌ CIS integration tests FAILING
- ❌ Unit tests for new generic methods don't exist
- ❌ Regression tests don't exist

**Documentation:**
- ❌ Design docs not updated
- ❌ Guides not updated
- ❌ Example configs don't exist

**Validation:**
- ❌ Vulcan import not tested

---

## 10-Phase Implementation Plan

### PHASE 0: Final Design Review ⏱️ 30 min

**Objective:** Confirm architecture before implementation

**Tasks:**
1. [ ] Review SYSTEM_ANALYSIS.md together
2. [ ] Confirm metadata_from_config will handle ALL nesting (embedded tags, simple nesting, grouping)
3. [ ] Confirm 4-handler final architecture
4. [ ] Identify any missing use cases
5. [ ] Get explicit approval to proceed

**Deliverable:** Signed-off architecture, ready to code

**Checkpoint:** User approves design before writing code

---

### PHASE 1: Implement metadata_from_config ⏱️ 3 hours

**Objective:** Generic nested XML handler working and tested

**1.1: Write Unit Tests FIRST (TDD - RED)**

Create `tests/unit/test_metadata_generation.py`:
```python
def test_metadata_simple_children()
def test_metadata_with_grouping()
def test_metadata_cis_controls_structure()
def test_metadata_empty_allowed()
def test_metadata_attribute_templates()
def test_metadata_content_templates()
def test_metadata_recursive_nesting()
```

Run tests → All FAIL (expected)

**1.2: Implement generate_metadata_from_config()**

Add to mapping_engine.py:
```python
def generate_metadata_from_config(
    self,
    recommendation: Recommendation,
    field_mapping: dict
) -> Any:
    """Build nested XML metadata from YAML config.

    Supports:
    - Simple nesting (parent > child)
    - Grouping (group items by field)
    - Multiple items per group
    - Recursive children (unlimited depth)
    - Attribute templates
    - Content templates
    - Empty elements
    - Custom namespaces
    """
```

Algorithm:
1. Extract source data
2. Check for grouping (group_by)
3. If grouping: build groups, then items per group
4. If simple: build children directly
5. Recursively handle nested children
6. Apply templates (attributes, content)
7. Return xsdata metadata object

**1.3: Add Handler to Mapping Loop**

In map_rule(), add:
```python
if structure == "metadata_from_config":
    metadata_obj = self.generate_metadata_from_config(rec, field_mapping)
    if metadata_obj:
        existing = rule_fields.get(target_element, [])
        rule_fields[target_element] = existing + [metadata_obj]
    continue
```

**1.4: Make Tests GREEN**
- [ ] All unit tests pass
- [ ] No regressions in DISA tests

**Deliverable:** Generic metadata handler working

**Checkpoint:** Unit tests GREEN before proceeding

---

### PHASE 2: Update All Configurations ⏱️ 1 hour

**Objective:** All configs use only generic patterns

**2.1: Update cis_style.yaml**

Replace old patterns:
```yaml
# OLD (DELETE):
cis_controls_metadata:
  structure: "official_cis_controls"

enhanced_metadata:
  structure: "enhanced_namespace"

cis_controls_ident:
  structure: "cis_controls_ident"
```

With new generic patterns:
```yaml
# NEW (ADD):
cis_controls_ident:
  target_element: "ident"
  structure: "ident_from_list"
  source_field: "cis_controls"
  ident_spec:
    system_template: "https://www.cisecurity.org/controls/v{item.version}"
    value_template: "{item.version}:{item.control}"
    attributes:
      - name: "controlURI"
        template: "http://cisecurity.org/20-cc/v{item.version}/control/..."
        namespace_prefix: "cc{item.version}"

cis_controls_metadata:
  target_element: "metadata"
  structure: "metadata_from_config"
  source_field: "cis_controls"
  metadata_spec:
    root_element: "cis_controls"
    namespace: "http://cisecurity.org/controls"
    namespace_prefix: "controls"
    allow_empty: true
    group_by: "item.version"
    group_element:
      element: "framework"
      attributes:
        urn: "urn:cisecurity.org:controls:{group_key}"
      item_element:
        element: "safeguard"
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

mitre_techniques:
  target_element: "ident"
  structure: "ident_from_list"
  source_field: "mitre_mapping.techniques"
  ident_spec:
    system_template: "https://attack.mitre.org/techniques"
    value_template: "{item}"

# Similar for mitre_tactics, mitre_mitigations
```

**2.2: Update base_style.yaml**

Add handler documentation:
```yaml
# Generic Structure Handlers
#
# 1. ident_from_list - Simple indices/taxonomies
#    Use for: CCIs, CIS Controls, MITRE, PCI-DSS, any flat list
#
# 2. metadata_from_config - Nested XML structures
#    Use for: CIS Controls metadata, hierarchies, embedded tags
#    Supports: grouping, nesting, attributes, content, empty elements
#
# 3. dublin_core - Dublin Core references (W3C standard)
#    Use for: NIST references
#
# 4. embedded_xml_tags - DEPRECATED (use metadata_from_config)
# 5. nested - DEPRECATED (use metadata_from_config)
```

**2.3: Update rule_elements sections**

Remove:
```yaml
cis_controls_metadata:
  xccdf_type: "MetadataType"
  description: "Old hard-coded way"
```

Ensure proper types for all new fields.

**Deliverable:** All configs use generic patterns

**Checkpoint:** Configs validated before testing

---

### PHASE 3: Integration Testing ⏱️ 1 hour

**Objective:** Verify both DISA and CIS work perfectly

**3.1: Test DISA Export**
```bash
uv run cis-bench export tests/fixtures/benchmarks/almalinux_complete.json \
  --format xccdf -o /tmp/disa_final.xml

# Validate structure
xmllint --xpath "count(//*[local-name()='metadata'])" /tmp/disa_final.xml
# Expected: 0

xmllint --xpath "count(//*[local-name()='ident'])" /tmp/disa_final.xml
# Expected: ~2800 (CCI + CIS + MITRE)

xmllint --xpath "count(//*[local-name()='Profile'])" /tmp/disa_final.xml
# Expected: 4 (Level 1/2 × Server/Workstation)

# Check namespace
grep -c "xmlns:ns" /tmp/disa_final.xml
# Expected: 1 (single declaration at root)
```

**3.2: Test CIS Export**
```bash
uv run cis-bench export tests/fixtures/benchmarks/almalinux_complete.json \
  --format xccdf --style cis -o /tmp/cis_final.xml

# Validate structure
xmllint --xpath "count(//*[local-name()='metadata'])" /tmp/cis_final.xml
# Expected: ~322 (one per rule with CIS Controls)

xmllint --xpath "count(//*[local-name()='ident'])" /tmp/cis_final.xml
# Expected: ~2800 (CIS + MITRE as idents)

# Check CIS Controls in both places
xmllint --xpath "count(//*[local-name()='ident'][@system='https://www.cisecurity.org/controls/v8'])" /tmp/cis_final.xml
# Expected: ~322

xmllint --xpath "count(//*[local-name()='metadata']//*[local-name()='cis_controls'])" /tmp/cis_final.xml
# Expected: ~322 (dual representation)
```

**3.3: Run Integration Tests**
```bash
uv run python -m pytest tests/integration/test_disa_xccdf.py -v
# Expected: All pass

uv run python -m pytest tests/integration/test_cis_xccdf.py -v
# Expected: All pass (currently failing - will fix)

uv run python -m pytest tests/integration/test_profile_generation.py -v
# Expected: All pass
```

**3.4: Compare to Official XCCDFs**
- Side-by-side structure comparison
- Verify namespace handling matches
- Verify grouping matches

**Deliverable:** Both exports working, tests GREEN

**Checkpoint:** Integration tests pass before adding regression tests

---

### PHASE 4: Add Comprehensive Regression Tests ⏱️ 1 hour

**Objective:** Prevent future regressions with architecture compliance tests

**4.1: Create tests/regression/test_structure_compliance.py**

```python
"""Architecture compliance tests - prevent regressions."""

def test_disa_has_no_metadata_elements():
    """DISA exports MUST have zero metadata elements."""
    xml = export_disa()
    assert count_xpath(xml, ".//*[local-name()='metadata']") == 0

def test_disa_structure_matches_official_stig():
    """Our DISA structure must match official DISA STIGs."""
    official = load("tests/fixtures/xccdf/official/disa/U_RHEL_9_STIG_V2R5_Manual-xccdf.xml")
    ours = export_disa()

    # Same element types
    assert get_element_types(official) == get_element_types(ours)
    # Same namespace strategy
    assert count_namespace_declarations(official) == count_namespace_declarations(ours)

def test_cis_structure_matches_official_cis():
    """Our CIS structure must match official CIS XCCDFs."""
    official = load("tests/fixtures/xccdf/official/cis/CIS_Google_Chrome_Benchmark_v2.1.0-xccdf.xml")
    ours = export_cis()

    # CIS Controls in both ident and metadata
    assert count_cis_idents(ours) > 0
    assert count_cis_metadata(ours) > 0

def test_cis_controls_dual_representation():
    """CIS must have CIS Controls in BOTH ident and metadata."""
    xml = export_cis()
    ident_count = count_xpath(xml, ".//*[local-name()='ident'][@system='https://www.cisecurity.org/controls/v8']")
    metadata_count = count_xpath(xml, ".//*[local-name()='metadata']//*[local-name()='cis_controls']")

    assert ident_count > 0, "CIS Controls must be in idents"
    assert metadata_count > 0, "CIS Controls must be in metadata"
    # Should be roughly equal (both representations)
    assert abs(ident_count - metadata_count) < 50

def test_namespace_declared_once_at_root():
    """No namespace redeclarations in child elements."""
    for style in ["disa", "cis"]:
        xml = export(style)

        # Count xmlns declarations
        ns_declarations = count_xmlns_declarations(xml)

        # Should only be at root Benchmark element
        assert ns_declarations["root"] > 0, "Root must declare namespaces"
        assert ns_declarations["children"] == 0, "Children must NOT redeclare namespaces"
```

**4.2: Create tests/regression/test_architecture_compliance.py**

```python
"""Test that code follows architecture principles."""

def test_no_hard_coded_structure_names_in_code():
    """Ensure no organization names hard-coded in Python."""
    # Scan mapping_engine.py for "CIS", "MITRE", "PCI", "DISA" in logic
    # Should only be in comments, not code

def test_all_structures_from_config():
    """Verify all structures come from YAML, not code."""
    # Check that map_rule() only loops through config

def test_adding_framework_needs_no_code():
    """Test that adding PCI-DSS requires only YAML config."""
    # Create mock pci_dss_style.yaml
    # Export should work without code changes
```

**4.3: Create tests/unit/test_generic_handlers.py**

```python
"""Unit tests for generic structure handlers."""

def test_generate_idents_from_config_simple():
def test_generate_idents_from_config_with_attributes():
def test_generate_metadata_from_config_simple_nesting():
def test_generate_metadata_from_config_with_grouping():
def test_generate_metadata_from_config_cis_controls():
def test_generate_profiles_from_rules():
```

**Deliverable:** Comprehensive regression test suite

**Checkpoint:** All regression tests pass

---

### PHASE 5: Update All Documentation ⏱️ 2 hours

**Objective:** Complete, accurate documentation

**5.1: Update docs/about/design-philosophy.md**

Changes needed:
- [ ] Update "Enhanced XCCDF Format" section
- [ ] Explain DISA uses idents only (no metadata)
- [ ] Explain CIS uses dual representation (ident + metadata)
- [ ] Document namespace handling (root only)
- [ ] Update implementation approach section
- [ ] Add architecture diagram showing 4 handlers

**5.2: Update docs/technical-reference/mapping-engine-design.md**

Add sections:
- [ ] "ident_from_list Handler" - Full specification
- [ ] "metadata_from_config Handler" - Full specification
- [ ] "generate_profiles_from_rules" - Full specification
- [ ] "dublin_core Handler" - Document why we keep it
- [ ] Handler flowcharts
- [ ] Config schema reference

**5.3: Update docs/developer-guide/mapping-engine-guide.md**

Add practical guides:
- [ ] "How to Use ident_from_list" with examples
- [ ] "How to Use metadata_from_config" with examples
- [ ] "How to Generate Profiles" with examples
- [ ] "Handler Selection Guide" - Which handler for which use case

**5.4: Create framework extension guides**

New files:
- [ ] docs/developer-guide/adding-pci-dss.md - Complete walkthrough
- [ ] docs/developer-guide/adding-iso27001.md - Complete walkthrough
- [ ] docs/developer-guide/adding-custom-framework.md - Generic guide

Show zero code changes needed!

**Deliverable:** Complete documentation

**Checkpoint:** Docs reviewed for accuracy

---

### PHASE 6: Create Example Configurations ⏱️ 1 hour

**Objective:** Reference configs showing all capabilities

**6.1: Create docs/examples/example_generic_framework.yaml**

```yaml
# Complete Reference - Generic Framework Mapping
# Shows ALL handler capabilities and options
#
# Use this as a template for adding new compliance frameworks
# (PCI-DSS, ISO 27001, HIPAA, FedRAMP, etc.)

metadata:
  style_name: "example_generic"
  description: "Example showing all generic handler capabilities"

# Example 1: ident_from_list - Simple indices
framework_controls:
  target_element: "ident"
  structure: "ident_from_list"
  source_field: "custom_controls"
  ident_spec:
    system_template: "https://example.org/framework/v{item.version}"
    value_template: "{item.id}"
    attributes:  # Optional
      - name: "controlURI"
        template: "https://example.org/controls/{item.id}"
        namespace_prefix: "fw{item.version}"

# Example 2: metadata_from_config - Nested structure with grouping
framework_metadata:
  target_element: "metadata"
  structure: "metadata_from_config"
  source_field: "custom_controls"
  metadata_spec:
    root_element: "framework_controls"
    namespace: "https://example.org/schema"
    namespace_prefix: "fw"
    allow_empty: true
    group_by: "item.version"
    group_element:
      element: "control_family"
      attributes:
        version: "{group_key}"
      item_element:
        element: "control"
        attributes:
          id: "{item.id}"
          title: "{item.title}"
        children:
          - element: "implementation_level"
            content: "{item.level}"
          - element: "category"
            content: "{item.category}"

# Example 3: Profiles
profiles:
  generate_from_rules: true
  profile_mappings:
    - match: "High Security"
      id: "high-security"
      title: "High Security Profile"
```

**6.2: Create framework-specific examples**
- [ ] docs/examples/pci_dss_v4_mapping.yaml
- [ ] docs/examples/iso27001_2022_mapping.yaml
- [ ] docs/examples/hipaa_security_rule_mapping.yaml

**Deliverable:** Complete example library

**Checkpoint:** Examples tested and working

---

### PHASE 7: Code Cleanup & Linting ⏱️ 30 min

**Objective:** Clean, production-quality code

**7.1: Find and Remove Orphaned Code**

Use LibCST:
```python
# Scan for unused methods
# Delete unused imports
# Remove orphaned variables
# Clean up TODO comments
```

**7.2: Run Formatters**
```bash
uv run ruff format .
# Auto-format all code

uv run ruff check . --fix
# Auto-fix linting issues
```

**7.3: Security Scan**
```bash
uv run bandit -c pyproject.toml -r src/cis_bench/
# Ensure no security issues
```

**7.4: Update Logging**

Replace:
```python
logger.info("cis_controls=0, enhanced=0")  # Misleading!
```

With:
```python
logger.info(f"Generated {ident_count} idents, {metadata_count} metadata elements, {profile_count} profiles")
```

**Deliverable:** Clean, lint-passing code

**Checkpoint:** All linters pass

---

### PHASE 8: Full Test Suite ⏱️ 30 min

**Objective:** All tests GREEN

**8.1: Run Complete Test Suite**
```bash
uv run python -m pytest tests/ -v --cov=src/cis_bench --cov-report=term-missing
```

**Must pass:**
- [ ] All unit tests (new + existing)
- [ ] All integration tests (DISA + CIS)
- [ ] All regression tests (structure + architecture)
- [ ] Code coverage > 80%
- [ ] No skipped tests
- [ ] No warnings

**8.2: Fix Any Failures**
- [ ] Debug failures
- [ ] Fix root cause
- [ ] Re-run until GREEN

**Deliverable:** Complete test suite passing

**Checkpoint:** 100% tests GREEN before Vulcan validation

---

### PHASE 9: Vulcan Validation (Real-World) ⏱️ 1 hour

**Objective:** Resolve user's reported issue

**9.1: Generate DISA XCCDF for Vulcan**
```bash
uv run cis-bench export tests/fixtures/benchmarks/almalinux_complete.json \
  --format xccdf -o issue/cis-almalinux-disa-FIXED.xml

# Save both old and new for comparison
cp /tmp/test_disa.xml issue/cis-almalinux-disa-OLD.xml
cp /tmp/disa_final.xml issue/cis-almalinux-disa-NEW.xml
```

**9.2: Import to Vulcan**

Test in Vulcan:
- [ ] Upload cis-almalinux-disa-FIXED.xml
- [ ] Verify import succeeds (no errors)
- [ ] Check specific errors are gone:
  - ❌ "undefined method 'plaintext' for nil:NilClass"
  - ❌ "some rules failed to import successfully"

**9.3: Inspect Generated InSpec Profile**

Expected tags in each control:
```ruby
tag cci: ['CCI-000123', 'CCI-002447']
tag cis_controls_v8: ['8:3.14']
tag cis_controls_v7: ['7:14.9']
tag mitre_techniques: ['T1565', 'T1565.001']
tag mitre_tactics: ['TA0001']
tag mitre_mitigations: ['M1022']
tag profiles: ['Level 1 - Server', 'Level 1 - Workstation']
```

Verify:
- [ ] All tags present
- [ ] Tag values correct
- [ ] No parsing errors
- [ ] Profile structure correct

**9.4: Document Results**
- [ ] Take screenshots of successful import
- [ ] Save generated InSpec profile
- [ ] Document any issues or warnings
- [ ] Get user confirmation issue is resolved

**Deliverable:** Vulcan import successful, issue resolved

**Checkpoint:** User confirms issue fixed

---

### PHASE 10: Create PR & Ship ⏱️ 30 min

**Objective:** Merge to main

**10.1: Update CHANGELOG.md**

```markdown
## [0.3.0] - 2025-12-16

### Changed (BREAKING)
- **XCCDF exports now use generic config-driven structure handlers**
- **DISA exports use ident elements only** (no metadata pollution)
- **CIS exports use dual representation** (ident + metadata for CIS Controls)
- **Profiles generated at Benchmark level** (proper XCCDF standard)
- **Namespace declared once at root** (no child redeclarations)

### Added
- Generic `ident_from_list` handler for any compliance framework
- Generic `metadata_from_config` handler for nested XML structures
- Profile generation from recommendation.profiles field
- Support for CIS Level 3 profiles
- Regression tests for structure compliance
- Architecture compliance tests

### Fixed
- **Namespace redeclaration issue** causing Vulcan import failures
- **'undefined method plaintext' error** in Vulcan XCCDF parser
- **Rules failing to import** in Vulcan due to metadata parsing
- Hard-coded structure generation (now config-driven)

### Removed
- Hard-coded CIS Controls metadata generation
- Hard-coded MITRE metadata generation
- Organization-specific structure handlers (cis_controls_ident, official_cis_controls, etc.)
- Metadata elements from DISA exports

### Migration Guide
If using custom YAML configs, update:
- Replace `official_cis_controls` → `metadata_from_config`
- Replace `cis_controls_ident` → `ident_from_list`
- Replace `enhanced_namespace` → `ident_from_list`
- See docs/examples/example_generic_framework.yaml for patterns

### Developer Impact
Adding new compliance frameworks (PCI-DSS, ISO 27001, HIPAA):
- **Before:** Required Python code changes (~3-5 hours)
- **After:** YAML config only (~30 minutes)
- See docs/developer-guide/adding-custom-framework.md
```

**10.2: Create Comprehensive PR Description**

```markdown
# Fix XCCDF Namespace Pollution and Implement Generic Structure Handlers

## Problem

User reported Vulcan import failures with our XCCDF exports:
1. `undefined method 'plaintext' for nil:NilClass`
2. `some rules failed to import successfully`
3. Raw XCCDF has namespace pollution (`ns*:` redeclarations)

**Root Cause:**
- DISA exports included metadata elements (real DISA STIGs don't use metadata)
- Namespace redeclarations in nested structures confused Vulcan's Ruby XML parser
- Hard-coded structure generation violated our design principles

## Solution

Implemented fully generic, config-driven structure handlers:

### Architecture Changes

**4 Generic Handlers (Down from 8+):**
1. `ident_from_list` - ANY compliance framework index
2. `metadata_from_config` - ANY nested XML structure
3. `generate_profiles_from_rules` - ANY applicability system
4. `dublin_core` - W3C standard (kept)

**Replaced 5+ specialized handlers with 2 generic ones.**

### DISA Export Changes

**Before:**
```xml
<ns0:Rule xmlns:ns0="http://xccdf/1.1">
  <ns0:metadata xmlns:ns0="http://xccdf/1.2">  <!-- REDECLARATION! -->
    <ns0:cis_controls xmlns:ns0="http://cis/controls">  <!-- REDECLARATION! -->
```

**After:**
```xml
<Benchmark xmlns="http://xccdf/1.1">
  <Rule>
    <ident system="http://cyber.mil/cci">CCI-000123</ident>
    <ident system="https://www.cisecurity.org/controls/v8">8:3.14</ident>
    <ident system="https://attack.mitre.org/techniques">T1565</ident>
    <!-- NO metadata, clean namespaces -->
  </Rule>
</Benchmark>
```

### CIS Export Changes

**CIS Controls now in BOTH formats (like official CIS):**
- `<ident>` elements (for indexing)
- `<metadata>` with nested structure (for detailed info)

**MITRE now as idents only** (cleaner, no namespace pollution)

### Benefits

1. ✅ **Vulcan import works** - No namespace pollution
2. ✅ **Follows design principles** - Config-driven, DRY
3. ✅ **Extensible** - Add PCI-DSS via YAML only
4. ✅ **Maintainable** - Fix once, works everywhere
5. ✅ **Tested** - Comprehensive regression suite

## Testing

- ✅ 9 DISA integration tests passing
- ✅ 4 Profile generation tests passing
- ✅ CIS integration tests passing
- ✅ Regression tests added
- ✅ Architecture compliance tests added
- ✅ Validated with Vulcan import (issue resolved)

## Files Changed

**Code:** (see commit)
- src/cis_bench/exporters/mapping_engine.py
- src/cis_bench/exporters/xccdf_unified_exporter.py

**Config:**
- src/cis_bench/exporters/configs/*.yaml

**Tests:**
- tests/integration/test_profile_generation.py (new)
- tests/regression/ (new)
- tests/unit/test_generic_handlers.py (new)

**Docs:**
- docs/about/design-philosophy.md
- docs/technical-reference/mapping-engine-design.md
- docs/developer-guide/*.md
- docs/examples/*.yaml (new)

## Validation

Tested with Vulcan:
- [x] XCCDF imports successfully
- [x] No "plaintext" error
- [x] All rules import correctly
- [x] InSpec profile has all tags (cci, cis_controls, mitre, profiles)

Resolves user's reported issue.
```

**10.3: Push and Create PR**
```bash
# Review all changes
git status
git diff

# Stage changes
git add src/cis_bench/exporters/
git add src/cis_bench/exporters/configs/
git add tests/
git add docs/
git add CHANGELOG.md

# Commit
git commit -m "fix: refactor XCCDF exports to use generic config-driven handlers

Implements generic structure handlers to fix Vulcan import issues
and follow config-driven design principles.

Changes:
- Add generic ident_from_list for any compliance framework
- Add generic metadata_from_config for nested XML structures
- Add Profile generation at Benchmark level
- Remove all hard-coded structure generation
- Fix namespace pollution (single declaration at root)

DISA exports:
- All compliance data as ident elements (no metadata)
- Fixes Vulcan namespace parsing errors
- Matches official DISA STIG structure

CIS exports:
- CIS Controls in dual format (ident + metadata)
- MITRE as idents only (cleaner)
- Maintains CIS-CAT compatibility

Architecture:
- Zero hard-coded structures (fully config-driven)
- Add frameworks via YAML only (no code changes)
- Comprehensive regression test suite

Fixes Vulcan import errors reported by user.

Authored by: Aaron Lippold <lippold@gmail.com>"

# Push
git push origin fix/xccdf-namespace-ident-refactor

# Create PR
gh pr create --title "Fix XCCDF namespace pollution and implement generic structure handlers" \
  --body-file PR_DESCRIPTION.md
```

**Deliverable:** PR created and ready

**Checkpoint:** PR passes CI before merging

---

## Critical Success Criteria

**ALL must be true before merging:**

### Technical Validation ✓
- [ ] DISA export: 0 metadata elements
- [ ] DISA export: ~2800 ident elements
- [ ] DISA export: 4 Profile elements
- [ ] DISA export: 1 namespace declaration only
- [ ] CIS export: ~322 metadata elements
- [ ] CIS export: ~2800 ident elements
- [ ] CIS export: 4 Profile elements
- [ ] CIS export: Proper namespaces at root
- [ ] Both match official XCCDF structures

### Code Quality ✓
- [ ] All tests pass (unit + integration + regression)
- [ ] ruff check passes (no linting errors)
- [ ] ruff format passes (code formatted)
- [ ] bandit passes (no security issues)
- [ ] Code coverage > 80%
- [ ] No hard-coded structure names in code
- [ ] No orphaned code
- [ ] No tech debt

### Real-World Validation ✓
- [ ] Vulcan imports DISA XCCDF (no errors)
- [ ] No "undefined method 'plaintext'" error
- [ ] No "rules failed to import" error
- [ ] InSpec profile has all tags
- [ ] Tags contain correct data
- [ ] User confirms issue resolved

### Documentation ✓
- [ ] design-philosophy.md updated
- [ ] mapping-engine-design.md updated
- [ ] mapping-engine-guide.md updated
- [ ] Example configs exist and work
- [ ] Framework extension guides exist
- [ ] CHANGELOG.md updated
- [ ] README.md updated if needed

### Architecture ✓
- [ ] Zero hard-coded structures
- [ ] Adding PCI-DSS requires only YAML
- [ ] All handlers generic (or standard)
- [ ] Follows design principles
- [ ] Extensible without code changes

**No exceptions. No shortcuts. Done correctly.**

---

## Session Recovery Instructions

If context is lost, resume by:

1. Read this FINAL_PLAN.md
2. Check current phase in task list
3. Read SYSTEM_ANALYSIS.md for context
4. Review git status to see what's committed
5. Run tests to verify current state
6. Continue from current phase

---

## Tools We're Using

1. **LibCST** - Safe code refactoring (installed ✓)
2. **ast-grep** - Code structure search (installed ✓)
3. **pytest** - Testing framework
4. **ruff** - Linting and formatting
5. **bandit** - Security scanning
6. **xmllint** - XML validation and querying

---

## Estimated Timeline

**Focused work:** ~11.5 hours
**With breaks/debugging:** ~15 hours
**Spread over:** 2-3 sessions

**Current session progress:** ~2 hours (Phase 0-1 partial)

**Worth it?**

YES - Fixes architecture properly, enables zero-code extensibility, resolves user's issue completely.

---

**Status:** Ready for Phase 0 execution when user returns from meeting.
