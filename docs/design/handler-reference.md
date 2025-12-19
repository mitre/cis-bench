# Structure Handler Reference

!!! info "Documentation Path"
    **You are here:** Design Documents > Structure Handler Reference

    - **For usage guide:** See [MappingEngine Guide](../developer-guide/mapping-engine-guide.md)
    - **For technical design:** See [MappingEngine Design](../technical-reference/mapping-engine-design.md)

Quick reference for all XCCDF structure handlers in the MappingEngine.

---

## Handler Summary

| Handler | Purpose | Used By | Code Location |
|---------|---------|---------|---------------|
| `ident_from_list` | Generate `<ident>` elements from lists | DISA, CIS | `generate_idents_from_config()` |
| `metadata_from_config` | Build nested XML structures | CIS | `generate_metadata_from_config()` |
| `generate_profiles_from_rules` | Create `<Profile>` elements | Both | `generate_profiles_from_rules()` |
| `dublin_core` | NIST references with DC standard | Both | Built-in |
| `embedded_xml_tags` | VulnDiscussion tags | DISA | Built-in |
| `nested` | check/check-content structure | Both | Built-in |

---

## Generic Handlers (Preferred)

### ident_from_list

Generate `<ident>` elements from any compliance framework list.

**Supports:** CCIs, CIS Controls, MITRE ATT&CK, PCI-DSS, ISO 27001, HIPAA

**Config:**
```yaml
field_name:
  target_element: "ident"
  structure: "ident_from_list"
  source_field: "cis_controls"  # or "mitre_mapping.techniques"
  ident_spec:
    system_template: "https://org.com/framework/v{item.version}"
    value_template: "{item.id}"  # or "{item}" for simple lists
    attributes:  # Optional

      - name: "controlURI"
        template: "https://org.com/controls/{item.id}"
        namespace_prefix: "fw{item.version}"
```

**Template Variables:**

- `{item}` - For simple string lists
- `{item.field}` - For object lists (version, control, title, etc.)
- `{group_key}` - When used with grouping

**Output:**
```xml
<ident system="https://www.cisecurity.org/controls/v8">8:3.14</ident>
<ident system="https://attack.mitre.org/techniques">T1565</ident>
```

**Implementation:** `MappingEngine.generate_idents_from_config()`

---

### metadata_from_config

Build any nested XML structure from YAML specification.

**Supports:** CIS Controls metadata, PCI-DSS hierarchies, ISO 27001 families

**Config:**
```yaml
field_name:
  target_element: "metadata"
  structure: "metadata_from_config"
  source_field: "cis_controls"
  requires_post_processing: true  # lxml injection after xsdata
  metadata_spec:
    root_element: "cis_controls"
    namespace: "http://cisecurity.org/controls"
    namespace_prefix: "controls"
    allow_empty: true

    group_by: "item.version"  # Optional grouping

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
            content: "Unknown"  # Static content
```

**Features:**

- **Grouping:** Group items by field value
- **Nesting:** Unlimited depth via recursive children
- **Attributes:** Template-based substitution
- **Content:** Static or template-based
- **Empty handling:** Optional empty element generation

**Output:**
```xml
<metadata>
  <controls:cis_controls>
    <controls:framework urn="urn:cisecurity.org:controls:8">
      <controls:safeguard title="Log Sensitive Data Access">
        <controls:implementation_groups ig1="false" ig2="false" ig3="true"/>
        <controls:asset_type>Unknown</controls:asset_type>
      </controls:safeguard>
    </controls:framework>
  </controls:cis_controls>
</metadata>
```

**Implementation:**

- `MappingEngine.generate_metadata_from_config()`
- `MappingEngine._build_config_item()`
- `MappingEngine._build_config_child()`
- `XCCDFUnifiedExporter._inject_metadata_from_config()`

---

### generate_profiles_from_rules

Generate Benchmark-level `<Profile>` elements from rule applicability.

**Supports:** CIS Levels, DISA MAC, PCI-DSS tiers

**Config:**
```yaml
benchmark:
  profiles:
    generate_from_rules: true
    profile_mappings:

      - match: "Level 1 - Server"
        id: "level-1-server"
        title: "Level 1 - Server"
        description: "CIS Level 1 for server environments"

      - match: "Level 2 - Server"
        id: "level-2-server"
        title: "Level 2 - Server"
```

**How It Works:**

1. Scans all recommendations
2. For each profile mapping, finds rules where `match` is in `recommendation.profiles`
3. Creates Profile element with select list of matching rule IDs
4. Adds to Benchmark (not Rules)

**Output:**
```xml
<Profile id="level-1-server">
  <title>Level 1 - Server</title>
  <description>CIS Level 1 for server environments</description>
  <select idref="xccdf_cis_rule_6_1_1" selected="true"/>
  <select idref="xccdf_cis_rule_6_1_2" selected="true"/>
</Profile>
```

**Implementation:** `MappingEngine.generate_profiles_from_rules()`

---

## Specialized Handlers (Legacy)

### dublin_core

W3C Dublin Core standard for NIST references.

**Config:**
```yaml
reference:
  target_element: "reference"
  structure: "dublin_core"
  source_field: "nist_controls"
```

**Output:**
```xml
<reference href="https://csrc.nist.gov/...">
  <dc:title>NIST SP 800-53</dc:title>
  <dc:identifier>AU-2</dc:identifier>
</reference>
```

**Note:** Keep as-is (W3C standard), could be replaced by metadata_from_config later.

---

### embedded_xml_tags

DISA VulnDiscussion embedded XML tags.

**Config:**
```yaml
description:
  structure: "embedded_xml_tags"
  components:

    - tag: "VulnDiscussion"
      sources:

        - field: "description"
        - field: "rationale"
      separator: "\n\n"

    - tag: "FalsePositives"
      content: ""
```

**Output:**
```xml
<description>
  <VulnDiscussion>Description text...

Rationale text...</VulnDiscussion>
  <FalsePositives></FalsePositives>
</description>
```

---

### nested

Simple parent-child nesting (check/check-content).

**Config:**
```yaml
check:
  structure: "nested"
  attributes:
    system: "C-{ref_normalized}"
  children:

    - element: "check-content"
      source_field: "audit"
      transform: "strip_html_keep_code"
```

**Output:**
```xml
<check system="C-1_1_1">
  <check-content>modprobe -n -v cramfs</check-content>
</check>
```

---

## Handler Selection Guide

| Data Type | Handler | Example |
|-----------|---------|---------|
| Flat list → multiple elements | `ident_from_list` | CCIs, MITRE techniques |
| Hierarchical/grouped data | `metadata_from_config` | CIS Controls structure |
| Rule applicability | `generate_profiles_from_rules` | Level 1/2 profiles |
| W3C Dublin Core | `dublin_core` | NIST references |
| DISA embedded tags | `embedded_xml_tags` | VulnDiscussion |
| Simple nesting | `nested` | check/check-content |

---

## Adding New Handlers

If existing handlers don't meet your needs:

1. **Evaluate if `metadata_from_config` can handle it** - It's very flexible
2. **If not, create new handler method** in `mapping_engine.py`
3. **Add structure name** to the handler dispatch logic
4. **Document in this reference**
5. **Add tests** in `tests/unit/test_mapping_engine.py`

---

## Related Documentation

- [MappingEngine Guide](../developer-guide/mapping-engine-guide.md) - Practical usage
- [MappingEngine Design](../technical-reference/mapping-engine-design.md) - Technical architecture
- [YAML Config Reference](../technical-reference/yaml-config-reference.md) - Complete syntax
