# XCCDF Mapping Design

!!! info "Documentation Path"
    **You are here:** Design Documents > XCCDF Mapping Design

    - **For usage guide:** See [MappingEngine Guide](../developer-guide/mapping-engine-guide.md)
    - **For handler reference:** See [Handler Reference](handler-reference.md)

This document explains the design decisions behind the config-driven XCCDF mapping system.

---

## Problem Statement

### Design Principle Violation (Before Refactor)

**Our Design Philosophy states:**

> "Config-Driven Over Hard-Coded... Clear separation between data (YAML) and logic (Python)"

**Previous Violation:**

- CIS Controls metadata generation was hard-coded in `build_cis_controls()` method
- MITRE metadata was hard-coded in `_inject_enhanced_metadata()`
- Structure logic embedded in Python instead of YAML config

**Impact:**

- Adding PCI-DSS, ISO 27001 required code changes
- Structure generation couldn't be tested independently
- Violated DRY - specific methods instead of generic

---

## Solution: Generic Structure Handlers

### Handler Architecture

Instead of organization-specific methods, we use 3 generic handlers:

| Handler | Purpose | Works For |
|---------|---------|-----------|
| `ident_from_list` | Generate `<ident>` elements | CCIs, CIS, MITRE, PCI-DSS, ISO 27001 |
| `metadata_from_config` | Build nested XML structures | CIS Controls metadata, hierarchies |
| `generate_profiles_from_rules` | Create `<Profile>` elements | CIS Levels, DISA MAC, tiers |

### DISA vs CIS Output Differences

| Data | DISA Format | CIS Format |
|------|-------------|------------|
| CIS Controls | `<ident>` only | `<ident>` + `<metadata>` (dual) |
| MITRE ATT&CK | `<ident>` only | `<ident>` only |
| Profiles | `<Profile>` at Benchmark | `<Profile>` at Benchmark |
| Metadata | None (clean) | CIS Controls structure |

**Key Insight:** CIS needs CIS Controls in both ident AND metadata (dual representation) to match official CIS XCCDF structure.

---

## metadata_from_config Specification

The most complex handler - builds any nested XML from YAML.

### Capabilities

1. **Simple nesting:** Parent > Child
2. **Grouping:** Group items by field (e.g., by version)
3. **Multiple items per group:** Framework > multiple Safeguards
4. **Attributes:** Template-based attribute generation
5. **Content:** Static or template-based content
6. **Empty handling:** Generate empty element if no data
7. **Namespace support:** Custom namespace per structure
8. **Recursive children:** Unlimited nesting depth

### Config Schema

```yaml
field_name:
  target_element: "metadata"
  structure: "metadata_from_config"
  source_field: "cis_controls"
  requires_post_processing: true  # Complex nesting needs lxml injection
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
```

### Use Cases

**CIS Controls (with grouping):**

- Group by version → framework elements
- Multiple safeguards per framework
- Nested children (implementation_groups, asset_type, etc.)

**check > check-content (simple nesting):**

```yaml
check:
  structure: "metadata_from_config"
  metadata_spec:
    root_element: "check"
    children:

      - element: "check-content"
        source_field: "audit"
```

---

## Why Generic Handlers?

### Benefits

1. **DRY** - One implementation, any organization
2. **Extensible** - Add PCI-DSS via YAML only
3. **Testable** - Generic tests, not per-org
4. **Maintainable** - Fix once, works everywhere
5. **Config-Driven** - Follows design principles

### Before vs After

**Before (Hard-coded):**
```python
def build_cis_controls(self, recommendation):
    """Build CIS Controls metadata."""  # Organization-specific!
    for control in recommendation.cis_controls:
        # Hard-coded structure
```

**After (Generic):**
```python
def generate_metadata_from_config(self, recommendation, field_mapping):
    """Build ANY nested XML from YAML config."""
    spec = field_mapping["metadata_spec"]
    # Generic - reads structure from config
```

---

## Design Decisions

### Decision 1: CIS Controls in Dual Format

**Why:** Official CIS XCCDFs use both ident and metadata for CIS Controls.

**Implementation:** Two field mappings (cis_controls_ident, cis_controls_metadata)

### Decision 2: MITRE as Ident Only

**Why:** Simpler, consistent with DISA, no namespace pollution.

**Implementation:** Use ident_from_list for techniques/tactics/mitigations

### Decision 3: Profiles at Benchmark Level

**Why:** XCCDF standard, matches DISA and CIS official exports.

**Implementation:** `generate_profiles_from_rules` from recommendation.profiles

### Decision 4: No Metadata for DISA

**Why:** Real DISA STIGs don't use metadata elements.

**Implementation:** DISA style uses ident elements only.

---

## Testing Strategy

### Unit Tests

```python
def test_generate_idents_from_config()    # Generic ident generation
def test_generate_metadata_from_config()  # Generic metadata generation
def test_generate_profiles_from_rules()   # Profile generation
def test_metadata_grouping()              # group_by logic
def test_metadata_nesting()               # Recursive children
```

### Integration Tests

```python
def test_disa_xccdf()  # Verify: idents only, no metadata
def test_cis_xccdf()   # Verify: idents + metadata
def test_profile_generation()  # Verify: Profiles at Benchmark
```

### Architecture Compliance Tests

```python
def test_no_hard_coded_structures()     # No org names in code
def test_all_structures_from_config()   # All from YAML
def test_generic_extensibility()        # Mock PCI-DSS works
```

---

## Validation Criteria

### DISA Export

- 0 metadata elements
- ~2800 ident elements (CCI + CIS + MITRE)
- 4 Profile elements (Level 1/2 × Server/Workstation)
- 1 namespace declaration (root only)

### CIS Export

- ~322 metadata elements (CIS Controls)
- ~2800 ident elements (CIS + MITRE)
- 4 Profile elements
- Proper namespaces at root

### Both

- Match official XCCDF structures
- No namespace pollution in children
- All tests pass
- Coverage > 80%

---

## Related Documentation

- [Design Principles](design-principles.md) - Architectural rules
- [Handler Reference](handler-reference.md) - Handler specifications
- [Architecture Decisions](architecture-decisions.md) - ADR format decisions
- [MappingEngine Guide](../developer-guide/mapping-engine-guide.md) - Practical usage
