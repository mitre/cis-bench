# Architecture Decision Records

!!! info "Documentation Path"
    **You are here:** Design Documents > Architecture Decision Records (ADRs)

    - **For design philosophy:** See [Design Philosophy](../about/design-philosophy.md)
    - **For mapping design:** See [XCCDF Mapping Design](xccdf-mapping-design.md)

This document records significant architectural decisions made during cis-bench development.

---

## ADR-001: Config-Driven XCCDF Export

**Status:** Accepted (October 2024)

### Context

CIS benchmarks need to be exported to XCCDF format for compliance tools (OpenSCAP, SCAP Workbench, SCC). Different organizations need different XCCDF styles:

- **DISA:** STIG-compatible with CCIs and VulnDiscussion
- **CIS:** Native format with CIS Controls metadata

### Decision

Use a **configuration-driven approach** where YAML files define field mappings, not Python code.

### Consequences

**Benefits:**

- Add new XCCDF styles without code changes
- Non-developers can create custom formats
- Easier testing and maintenance

**Trade-offs:**

- More complex initial design
- YAML parsing overhead (negligible)
- Learning curve for config syntax

---

## ADR-002: Generic Structure Handlers

**Status:** Accepted (December 2024)

### Context

Initial implementation had organization-specific handlers (`build_cis_controls()`, `_inject_mitre_metadata()`). This violated the config-driven design principle.

### Decision

Replace organization-specific handlers with three generic handlers:

1. `ident_from_list` - Any identifier list
2. `metadata_from_config` - Any nested XML structure
3. `generate_profiles_from_rules` - Any profile system

### Consequences

**Benefits:**

- Add PCI-DSS, ISO 27001 via YAML only
- Single implementation for all frameworks
- Easier to test and maintain

**Trade-offs:**

- More complex config schema
- Handler code is more abstract

---

## ADR-003: SQLite for Catalog Database

**Status:** Accepted (November 2024)

### Context

Need to store catalog metadata (benchmark listings) and downloaded benchmark data locally for offline access and fast re-exports.

### Decision

Use SQLite with:

- **SQLModel** for ORM (Pydantic + SQLAlchemy)
- **FTS5** for full-text search
- **Alembic** for schema migrations

### Consequences

**Benefits:**

- Zero dependencies (stdlib sqlite3)
- Fast full-text search
- Preserves user data across upgrades

**Trade-offs:**

- Schema migrations required for changes
- Single-writer (not an issue for CLI)

---

## ADR-004: xsdata for XCCDF Models

**Status:** Accepted (September 2024)

### Context

Need to generate valid XCCDF XML that conforms to NIST schemas. Options:

1. Hand-craft XML strings
2. Use lxml ElementTree
3. Use xsdata-generated models from XSD

### Decision

Use **xsdata** to generate Python dataclasses from NIST XCCDF XSD schemas.

### Consequences

**Benefits:**

- Type-safe XCCDF generation
- Schema validation built-in
- IDE autocomplete support

**Trade-offs:**

- Generated code is verbose (~10K lines)
- xsdata quirks (namespace handling)
- Need two sets of models (XCCDF 1.1.4 and 1.2)

---

## ADR-005: Strategy Pattern for HTML Parsing

**Status:** Accepted (September 2024)

### Context

CIS WorkBench HTML structure may change. Need to handle different versions without breaking existing functionality.

### Decision

Use **Strategy Pattern** with versioned parser implementations:

- `v1_current.py` - Current HTML structure
- `v2_future.py` - Future structure (when needed)
- Auto-detection selects correct strategy

### Consequences

**Benefits:**

- Backward compatibility
- Easy to add new parsers
- Old benchmarks still work

**Trade-offs:**

- Multiple parser implementations to maintain
- Strategy selection logic

---

## ADR-006: Browser Cookie Authentication

**Status:** Accepted (September 2024)

### Context

CIS WorkBench requires authentication. Options:

1. Username/password (insecure)
2. OAuth/API key (not available)
3. Browser cookies (session reuse)

### Decision

Use **browser-cookie3** to extract session cookies from user's browser.

### Consequences

**Benefits:**

- No credentials stored
- Uses existing browser session
- Works with MFA-protected accounts

**Trade-offs:**

- Requires user to log in via browser first
- Browser database format may change
- Cross-platform complexity

---

## ADR-007: DISA vs CIS Style Separation

**Status:** Accepted (October 2024)

### Context

DISA STIGs and CIS XCCDFs have different structures:

- **DISA:** VulnDiscussion embedded tags, CCIs, no metadata
- **CIS:** CIS Controls in both ident and metadata (dual)

### Decision

Maintain two separate YAML style configs:

- `disa_style.yaml` - STIG-compatible format
- `cis_style.yaml` - Native CIS format

Both use the same generic handlers, just different configs.

### Consequences

**Benefits:**

- Clear separation of concerns
- Each style optimized for its target
- Users choose appropriate style

**Trade-offs:**

- Some duplication in configs
- Two configurations to maintain

---

## ADR-008: CIS Controls Dual Representation

**Status:** Accepted (December 2024)

### Context

Official CIS XCCDF exports include CIS Controls in two places:

1. `<ident>` elements (for tool compatibility)
2. `<metadata>` structure (official CIS format)

### Decision

Implement **dual representation** in CIS style:

- CIS Controls as ident elements (cc7/cc8 URIs)
- CIS Controls in metadata (official nested structure)

### Consequences

**Benefits:**

- Matches official CIS format
- Maximum tool compatibility
- All data preserved

**Trade-offs:**

- Slightly larger XML output
- More complex config

---

## ADR-009: MITRE as Ident Only

**Status:** Accepted (December 2024)

### Context

MITRE ATT&CK data (techniques, tactics, mitigations) could be represented as:

1. Metadata elements with namespace
2. Ident elements with system URIs

### Decision

Use **ident elements only** for MITRE data.

### Consequences

**Benefits:**

- Cleaner XML (no metadata namespace pollution)
- Consistent with DISA approach
- Simpler implementation

**Trade-offs:**

- No hierarchical MITRE structure
- Less semantic richness

---

## ADR-010: Profiles at Benchmark Level

**Status:** Accepted (October 2024)

### Context

XCCDF Profiles (Level 1/2, Server/Workstation) can be placed at:

1. Rule level (per-rule profile attribute)
2. Benchmark level (Profile elements with select lists)

### Decision

Generate **Profiles at Benchmark level** from `recommendation.profiles` field.

### Consequences

**Benefits:**

- Matches XCCDF standard
- Consistent with official exports
- Better tool compatibility

**Trade-offs:**

- Requires scanning all rules to build profiles
- Profile data duplicated (in rule and benchmark)

---

## Related Documentation

- [Design Philosophy](../about/design-philosophy.md) - Design rationale
- [Design Principles](design-principles.md) - Enforcement rules
- [XCCDF Mapping Design](xccdf-mapping-design.md) - Implementation details
- [MappingEngine Design](../technical-reference/mapping-engine-design.md) - Technical architecture
