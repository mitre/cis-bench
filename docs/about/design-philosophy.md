# Design Philosophy

**Why we built CIS Benchmark CLI the way we did**

This document explains our architectural choices and design philosophy to help contributors understand the framework and build on it effectively.

---

## Core Principles

### 1. Config-Driven Over Hard-Coded

**Decision:** XCCDF field mappings defined in YAML configuration files, not Python code.

**Rationale:**

- Adding new XCCDF styles doesn't require code changes
- Field mappings can be tested independently
- Non-developers can create custom export formats
- Clear separation between data (YAML) and logic (Python)

**See:** [MappingEngine User Guide](../developer-guide/mapping-engine-guide.md)

---

### 2. Enhanced XCCDF Format - Preserving All Available Data

**What we do:** CIS-style XCCDF exports include MITRE ATT&CK and NIST mappings in addition to standard CIS Controls.

**Why:** CIS WorkBench contains valuable compliance data (MITRE ATT&CK, NIST SP 800-53) that official CIS XCCDF exports don't include yet. We preserve this data using XCCDF's extensibility mechanism.

**How it works:**

**1. Data Source**

The MITRE and NIST mappings are **official CIS data** - they exist on the WorkBench website. We extract and preserve this data in our XCCDF exports.

**2. Standards Compliance**

From **NIST SP 800-126 Rev. 3** (XCCDF Specification):

> "XCCDF was designed to be extended through the use of XML namespaces.
> Benchmark authors may add elements from other namespaces to extend
> XCCDF documents with additional metadata or functionality."

**Best Practice**: Use separate namespaces for extensions so:

- Standard parsers can validate core XCCDF
- Tools can ignore unknown elements gracefully
- Extensions don't break compatibility

**3. Industry Precedent**

XCCDF extensions are standard practice in the industry:

- **DISA STIGs**: Add `<VulnDiscussion>` and CCI mappings (not in base XCCDF)
- **CIS themselves**: Add custom `controls:cis_controls` namespace
- **Red Hat**: Adds CPE applicability extensions
- **SCAP tools**: Add tool-specific metadata blocks

**4. Implementation Approach**

We follow XML/XCCDF best practices for extensions:

**Use proper namespaces** for extensions
```xml
xmlns:enhanced="http://cisecurity.org/xccdf/enhanced/1.0"
```

**Keep core XCCDF valid** - Base structure follows spec
```xml
<xccdf:Benchmark xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2">
<!-- Standard XCCDF elements -->
</xccdf:Benchmark>
```

**DISA exports** - Use ident elements only (no metadata pollution)
```xml
<Rule>
  <ident system="http://cyber.mil/cci">CCI-000123</ident>
  <ident system="https://www.cisecurity.org/controls/v8">8:3.14</ident>
  <ident system="https://attack.mitre.org/techniques">T1565</ident>
  <!-- NO metadata elements - fixes Vulcan import issues -->
</Rule>
```

**CIS exports** - Dual representation (ident + metadata)
```xml
<Rule>
  <!-- CIS Controls as idents -->
  <ident system="http://cisecurity.org/20-cc/v8"/>
  <!-- MITRE as idents (not metadata - cleaner) -->
  <ident system="https://attack.mitre.org/techniques">T1565</ident>

  <!-- CIS Controls ALSO in metadata (official structure) -->
  <metadata>
    <controls:cis_controls>...</controls:cis_controls>
  </metadata>
</Rule>
```

**Graceful degradation** - Tools process what they understand

- Vulcan: Parses idents → InSpec tags (no namespace errors)
- CIS-CAT: Reads CIS Controls metadata
- OpenSCAP: Validates XCCDF structure
- SCC: Processes all ident elements

**5. What Users Get**

Our enhanced format provides more comprehensive data:

| Feature | CIS Official | Our Enhanced |
|---------|--------------|--------------|
| CIS Controls v7/v8 | | |
| XCCDF 1.2 structure | | |
| CIS Profiles | | |
| MITRE ATT&CK | | |
| NIST SP 800-53 | (mostly) | |
| DoD RMF compatible | | |
| Works with CIS-CAT | | |

**We're more comprehensive** without breaking compatibility.

---

## How We Implemented It

### Namespace Design

```xml
<xccdf:Benchmark
xmlns:xccdf="http://checklists.nist.gov/xccdf/1.2"
xmlns:xhtml="http://www.w3.org/1999/xhtml"
xmlns:controls="http://cisecurity.org/controls"
xmlns:cc7="http://cisecurity.org/20-cc/v7.0"
xmlns:cc8="http://cisecurity.org/20-cc/v8.0"
xmlns:dc="http://purl.org/dc/elements/1.1/">

<!-- Profiles at Benchmark level (proper XCCDF standard) -->
<xccdf:Profile id="level-1-server">
  <xccdf:title>Level 1 - Server</xccdf:title>
  <xccdf:select idref="rule-6.1.1" selected="true"/>
</xccdf:Profile>
```

**Breakdown:**

- `xccdf`, `xhtml` - Standard NIST namespaces (required)
- `controls` - CIS official namespace (for metadata structure)
- `cc7`, `cc8` - CIS Controls version namespaces
- `dc` - Dublin Core for NIST references (W3C standard)
- No custom namespaces needed - MITRE uses ident elements

### Structure

```xml
<xccdf:Rule id="...">
<xccdf:title>...</xccdf:title>
<xccdf:description>...</xccdf:description>

<!-- NIST references (using standard Dublin Core) -->
<xccdf:reference href="https://csrc.nist.gov/...">
<dc:title>NIST SP 800-53</dc:title>
<dc:identifier>AU-2</dc:identifier>
</xccdf:reference>

<xccdf:metadata>
<!-- CIS official structure (100% compatible) -->
<controls:cis_controls xmlns:controls="http://cisecurity.org/controls">
<controls:framework urn="urn:cisecurity.org:controls:8.0">
<controls:safeguard title="..." urn="...">
<controls:implementation_groups ig1="true" ig2="true" ig3="true"/>
<controls:asset_type>Users</controls:asset_type>
<controls:security_function>Protect</controls:security_function>
</controls:safeguard>
</controls:framework>
</controls:cis_controls>

</xccdf:metadata>

<!-- MITRE as ident elements (not metadata - cleaner, no namespace pollution) -->
<xccdf:ident system="https://attack.mitre.org/techniques">T1565</xccdf:ident>
<xccdf:ident system="https://attack.mitre.org/techniques">T1565.001</xccdf:ident>
<xccdf:ident system="https://attack.mitre.org/tactics">TA0040</xccdf:ident>
<xccdf:ident system="https://attack.mitre.org/mitigations">M1022</xccdf:ident>

<!-- CIS Controls also as ident elements (dual representation) -->
<xccdf:ident system="http://cisecurity.org/20-cc/v8"/>
<xccdf:ident system="http://cisecurity.org/20-cc/v7"/>

<xccdf:rationale>...</xccdf:rationale>
<xccdf:fixtext>...</xccdf:fixtext>
</xccdf:Rule>
```

### Compatibility Testing

**Tools to test against:**
1. **xmllint**: Validate XML structure
2. **OpenSCAP**: Validate XCCDF 1.2 schema
3. **CIS-CAT**: Import and assess (if available)
4. **SCAP Validator**: NIST validation tool
5. **SCC (SCAP Compliance Checker)**: DoD tool

**Expected results:**

- Core XCCDF validates
- CIS Controls structure recognized
- Unknown elements ignored gracefully
- No validation errors

---

## Standards References

### XCCDF Specification (NIST SP 800-126 Rev. 3)
**Section 6.1: Extensibility**

> "XCCDF supports extensibility through several mechanisms:
> - Use of foreign namespaces in metadata blocks
> - Custom elements from other namespaces
> - Custom attributes on existing elements
>
> Tools should ignore elements and attributes they do not understand."

**Section 6.2.5: metadata Element**

> "The metadata element is a general-purpose container for additional
> information about a benchmark or rule. It may contain any number of
> elements from any namespace."

### XML Namespaces Best Practices (W3C)

**Use URIs that you control**
```xml
xmlns:enhanced="http://cisecurity.org/xccdf/enhanced/1.0"
```
(We're positioning this as a CIS-aligned extension)

**Document your schema**
Create `enhanced-metadata.xsd` defining our extensions

**Version your namespace**
`/1.0` allows for future evolution

### Dublin Core for References (RFC 5013)

**Standard metadata vocabulary** for references
```xml
<dc:title>NIST SP 800-53</dc:title>
<dc:identifier>AU-2</dc:identifier>
<dc:publisher>NIST</dc:publisher>
```

**Current Implementation:**

**DISA Exports:**

- All compliance data as ident elements (CCI, CIS Controls, MITRE)
- No metadata elements (fixes Vulcan import issues)
- Profiles at Benchmark level
- Single namespace declaration (no pollution)

**CIS Exports:**

- CIS Controls in BOTH ident and metadata (dual representation)
- MITRE as ident elements (not metadata - cleaner)
- Profiles at Benchmark level
- Official `controls:` namespace for metadata structure
- Dublin Core for NIST references
- Tested with OpenSCAP, SCC, Vulcan

**Result:** DISA-compatible and CIS-compatible while maintaining full data preservation.

---

### 3. Strategy Pattern for HTML Adaptation

**What we built:** Pluggable HTML parsing strategies that adapt to CIS WorkBench HTML changes without modifying core code.

**Why:**
CIS WorkBench updates their HTML structure periodically. Hard-coding the parser would break when HTML changes.

**How it works:**

- Abstract interface (`ScraperStrategy`)
- Versioned implementations (`v1_current.py`, `v2_january2026.py`, etc.)
- Auto-detection selects correct strategy
- Old benchmarks still work with old strategies

**Benefit:** HTML changes don't break existing functionality.

**See:** [Data Flow Pipeline - Stage 1](../developer-guide/data-flow-pipeline.md#stage-1-html-extraction)

---

### 4. Factory Pattern for Exporters

**What we built:** Factory Pattern for runtime exporter selection.

**Why:**

- Easy to add new export formats
- Consistent interface (BaseExporter)
- Runtime format selection
- Testable in isolation

**Implementation:**
```python
exporter = ExporterFactory.create('xccdf', style='disa')
exporter.export(benchmark, output_path)
```

**Benefit:** Add CSV, JSON, Markdown, XCCDF without modifying core code.

---

### 5. Session-Based Authentication

**What we built:** One-time login with persistent session cookies.

**Why:**

- UX improvement (no `--browser` on every command)
- Faster (no repeated cookie extraction)
- More reliable (validates session before use)

**Implementation:**

- `cis-bench auth login` saves to `~/.cis-bench/session.cookies`
- All commands auto-load saved session
- Validates on use, prompts to re-auth if expired

**Benefit:** Better user experience, fewer failures.

**See:** [Workflows - Scenario 1](../user-guide/workflows.md#scenario-1-export-almalinux-10-for-openscap-scanning)

---

### 6. Database Caching for Instant Re-Export

**What we built:** SQLite database that caches downloaded benchmarks for instant re-export.

**Why:**

- Export to multiple formats without re-downloading
- Instant re-export (2 seconds vs 2 minutes)
- Track what's downloaded
- Support export by ID (`cis-bench export 23598 --format xccdf`)

**Implementation:**

- SQLite database at `~/.cis-bench/catalog.db`
- `downloaded_benchmarks` table with full JSON
- Export command checks database first

**Benefit:** Dramatically faster workflow for multi-format exports.

---

### 7. Parallel Processing Where It Matters

**What we built:** Threaded catalog scraping with sequential exports.

**Why:**

- Catalog scraping is network-bound (66 pages, ~10 min sequential)
- Threading reduces time to ~2 min (5x faster)
- Exports are CPU-bound and fast enough (~2 sec/benchmark)
- No need to complicate with threading overhead

**Implementation:**

- 10 pages per batch
- 5 concurrent threads
- Retry logic with exponential backoff
- Failure threshold (abort if >10% fail)

**Benefit:** Catalog refresh is fast, code stays simple.

---

### 8. Validation at Multiple Layers

**What we built:** Five-layer validation pipeline.

**Validation layers:**
1. **HTML parsing** - Strategy validates structure
2. **Pydantic models** - Field validation and type checking
3. **xsdata models** - XCCDF structure compliance
4. **XML schema** - Optional xmllint validation
5. **DISA conventions** - STIG requirement checking

**Rationale:**

- Catch errors early (fail fast)
- Clear error messages (which stage failed)
- Confidence in output quality
- Easier debugging

**Benefit:** Invalid data never reaches output.

---

## Extensibility Framework

The system is designed for extension without modification:

**Adding Features:**

- **New export format** Create exporter class, register with factory
- **New XCCDF style** Create YAML config file only
- **New transformation** Register in base_style.yaml
- **New HTML version** Create strategy class
- **New field** Add to Pydantic model + YAML config

**NOT needed:**

- Modify core exporter code
- Change MappingEngine logic
- Update WorkbenchScraper
- Rewrite tests

**See:** [MappingEngine User Guide](../developer-guide/mapping-engine-guide.md) for how-to guides

---

## Testing Philosophy

**Principle:** Test behavior, not implementation.

**Approach:**

- Unit tests: Isolated functions
- Integration tests: Component interactions
- E2E tests: Complete workflows
- Architecture tests: Validate patterns (no hard-coded fields, etc.)

**Coverage:** 512 tests, all passing

**See:** [Testing Guide](../developer-guide/TESTING.md)

---

## Summary

The CIS Benchmark CLI is built on these principles:

1. **Config-Driven** - Behavior defined in YAML, not code
2. **Standards-Compliant** - XCCDF, Dublin Core, XML namespaces
3. **Extensible** - Add features without modifying core
4. **Validated** - Multiple validation layers
5. **User-Focused** - Session persistence, caching, progress bars
6. **Maintainable** - Clear patterns, comprehensive tests
7. **Enhanced** - Include all available data (MITRE, NIST)

These decisions create a **professional, maintainable, extensible** system that provides more value than alternatives while maintaining compatibility with standard tools.

---

## Related Documentation

- [Architecture Overview](../developer-guide/architecture.md) - System design
- [Data Flow Pipeline](../developer-guide/data-flow-pipeline.md) - Complete transformation process
- [MappingEngine User Guide](../developer-guide/mapping-engine-guide.md) - Config-driven exports
- [Contributing](../developer-guide/contributing.md) - How to extend the system
