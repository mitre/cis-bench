# Glossary

**Comprehensive terminology reference for CIS Benchmark CLI**

---

## CIS Benchmark Terminology

### Benchmark
A complete set of security configuration recommendations for a specific platform (e.g., "CIS AlmaLinux OS 10 Benchmark").

**Examples:**

- CIS Ubuntu 22.04 LTS Benchmark
- CIS Oracle Cloud Infrastructure Foundations Benchmark
- CIS Kubernetes Benchmark

**Not to be confused with:** XCCDF Benchmark (XML element)

### Recommendation
A single security control within a CIS Benchmark (e.g., "1.1.1 Ensure mounting of cramfs filesystems is disabled").

**Also called:** Control, Check, Security recommendation

**Contains:** Description, rationale, audit procedure, remediation steps, compliance mappings

### Profile
A subset of recommendations grouped by implementation difficulty or environment type.

**Examples:**

- Level 1 - Server
- Level 2 - Workstation
- Level 1 - Baseline

**Usage:** Systems can implement Level 1 for basic security, Level 2 for enhanced security

### Assessment Status
Whether a recommendation can be checked automatically or requires manual verification.

**Values:**

- **Automated** - Can be verified with scripts
- **Manual** - Requires human judgment

---

## XCCDF Terminology

### XCCDF
eXtensible Configuration Checklist Description Format - NIST standard for security checklists.

**Specifications:**

- XCCDF 1.1.4 - Used by DISA STIGs
- XCCDF 1.2 - Latest standard, used by CIS

**Purpose:** Standardized format for compliance tools (OpenSCAP, SCC, Nessus)

### XCCDF Benchmark
The root XML element containing all groups, rules, and profiles.

**Not to be confused with:** CIS Benchmark (the source content)

**Structure:**
```xml
<Benchmark id="xccdf_benchmark_23598">
<title>CIS AlmaLinux 10 Benchmark</title>
<Group>...</Group>
<Profile>...</Profile>
</Benchmark>
```

### Rule
An XCCDF element representing a single security check (maps to CIS Recommendation).

**Structure:**
```xml
<Rule id="xccdf_rule_1_1_1" severity="medium">
<title>...</title>
<description>...</description>
<ident>...</ident>
<fix>...</fix>
<check>...</check>
</Rule>
```

### Group
An XCCDF element for organizing related rules.

**Examples:**

- Initial Setup
- Services
- Network Configuration

**Structure:**
```xml
<Group id="xccdf_group_1">
<title>Initial Setup</title>
<Rule>...</Rule>
<Rule>...</Rule>
</Group>
```

### Ident
An XCCDF element linking rules to external control frameworks (like CCIs, CIS Controls).

**Examples:**
```xml
<ident system="http://cyber.mil/cci">CCI-000381</ident>
<ident system="http://cisecurity.org/20-cc/v8.0" cc8:controlURI="...">4.8</ident>
```

### Profile (XCCDF)
An XCCDF element defining a compliance profile (which rules are selected).

**Not to be confused with:** CIS Profile (Level 1/2)

**Example:**
```xml
<Profile id="xccdf_profile_level_1">
<title>Level 1 - Server</title>
<select idref="xccdf_rule_1_1_1" selected="true"/>
</Profile>
```

---

## Compliance and Standards Terminology

### CCI
Control Correlation Identifier - DoD standard for mapping NIST 800-53 controls to actionable checks.

**Format:** CCI-XXXXXX (6 digits)

**Examples:**

- CCI-000381 - CM-7.1 (Configure for essential capabilities only)
- CCI-000389 - CM-8.1 (Inventory management)

**Usage:** Required for DISA STIG format, maps CIS recommendations to NIST controls

### NIST SP 800-53
National Institute of Standards and Technology Special Publication 800-53 - Security and Privacy Controls catalog.

**Examples:**

- CM-7 - Least Functionality
- AC-2 - Account Management
- SI-4 - System Monitoring

**Relationship:** CIS Controls NIST 800-53 CCIs

### CIS Controls v8
Framework of 18 top-level security controls published by Center for Internet Security.

**Examples:**

- 4.1 - Establish and Maintain Secure Configuration Process
- 4.8 - Uninstall or Disable Unnecessary Services

**Implementation Groups:**

- IG1 - Basic cyber hygiene (essential)
- IG2 - Helps enterprises manage sensitive data
- IG3 - Advanced security for critical infrastructure

### MITRE ATT&CK
Knowledge base of adversary tactics, techniques, and mitigations.

**Components:**

- **Tactics** - "What" adversaries want (e.g., Persistence, Privilege Escalation)
- **Techniques** - "How" they achieve it (e.g., T1078 - Valid Accounts)
- **Mitigations** - How to prevent techniques (e.g., M1026 - Privileged Account Management)

**Usage:** CIS recommendations mapped to MITRE techniques they help prevent

### SCAP
Security Content Automation Protocol - Suite of standards for automated security compliance.

**Components:**

- XCCDF - Checklists
- OVAL - Technical checks
- CPE - Platform naming
- CCE - Configuration enumeration

**Tools:** OpenSCAP, DISA SCC, Nessus

### STIG
Security Technical Implementation Guide - DoD security configuration standard.

**Format:** XCCDF 1.1.4 with specific conventions (VulnDiscussion, CCIs, etc.)

**Publisher:** DISA (Defense Information Systems Agency)

---

## CIS Benchmark CLI System Components

### WorkbenchScraper
Component that fetches and parses CIS Benchmark HTML from CIS WorkBench.

**Location:** `src/cis_bench/fetcher/workbench.py`

**Purpose:** Extract 19 fields per recommendation from HTML

**Uses:** Strategy pattern for HTML adaptation

### Strategy
A parsing approach for extracting data from CIS WorkBench HTML.

**Current:** `v1_current.py`

**Purpose:** Adapts to HTML structure changes without modifying core scraper

**When to add new strategy:** CIS WorkBench updates HTML structure

### MappingEngine
Configuration-driven transformation system that converts Pydantic models to xsdata XCCDF models.

**Location:** `src/cis_bench/exporters/mapping_engine.py`

**Purpose:** Read YAML configs and apply field mappings

**Key Feature:** Change XCCDF structure by editing YAML, not code

### Style
A specific XCCDF output format configuration.

**Available:**

- **disa** - DISA STIG-compatible (XCCDF 1.1.4, CCIs, VulnDiscussion)
- **cis** - CIS native (XCCDF 1.2, full metadata)

**Defined in:** YAML files in `src/cis_bench/exporters/configs/`

**Not to be confused with:** Format (yaml, csv, etc.)

### Format
Output file type for exports.

**Available:**

- json - Machine-readable structured data
- yaml - Human-readable structured data
- csv - Spreadsheet compatible
- markdown - Documentation
- xccdf - NIST XCCDF XML (requires --style)

**Usage:** `cis-bench export 23598 --format xccdf --style disa`

### Catalog
Local SQLite database containing metadata for 1,300+ CIS benchmarks from CIS WorkBench.

**Location:** `~/.cis-bench/catalog.db`

**Features:**

- FTS5 full-text search
- Platform taxonomy
- Download tracking
- Update detection

**Built with:** `cis-bench catalog refresh`

### Platform Type
High-level category for grouping benchmarks.

**Values:**

- cloud
- os
- database
- container
- application

**Example:** "CIS Oracle Cloud" has platform_type="cloud"

### Platform
Specific technology platform.

**Examples:**

- aws, azure, google-cloud, oracle-cloud (cloud platforms)
- ubuntu, almalinux, rhel, windows-server (operating systems)
- mysql, postgresql, oracle-database (databases)
- kubernetes, docker (containers)

**Inferred automatically from benchmark title**

---

## Data Model Terminology

### Pydantic Model
Python class with type validation and serialization.

**Used for:**

- `Benchmark` - Complete CIS Benchmark
- `Recommendation` - Single security control

**Purpose:** Validate scraped data, provide type safety

### xsdata Model
Python class auto-generated from XSD schema.

**Used for:** XCCDF elements (Benchmark, Rule, Group, etc.)

**Generated from:** NIST XCCDF schema files

**Purpose:** Ensure XCCDF structure compliance

### Field Mapping
Configuration defining how a Pydantic field maps to an XCCDF element.

**Example:**
```yaml
title:
target_element: "title" # XCCDF element name
source_field: "title" # Pydantic field name
transform: "strip_html" # Transformation to apply
```

### Transformation
A function that modifies field values during export.

**Available:**

- `strip_html` - Remove all HTML tags
- `strip_html_keep_code` - Remove HTML but preserve code blocks
- `html_to_markdown` - Convert HTML to Markdown
- `none` - Pass through unchanged

**Defined in:** `base_style.yaml` transformations section

---

## Authentication and Session Terminology

### Session
Authenticated connection to CIS WorkBench using cookies.

**Storage:** `~/.cis-bench/session.cookies` (MozillaCookieJar format)

**Created by:** `cis-bench auth login --browser chrome`

**Used by:** All commands that access CIS WorkBench

### Browser Cookie Extraction
Process of reading authentication cookies from your browser's cookie store.

**Library:** browser-cookie3

**Supported:** Chrome, Firefox, Edge, Safari

**Requirement:** You must be logged into workbench.cisecurity.org in browser

### Session Validation
Testing if saved cookies still work with CIS WorkBench.

**Checks:**
1. Cookies exist
2. Request to /benchmarks doesn't redirect to login
3. Response is not the login page HTML

**Happens:** Automatically before catalog operations

---

## CLI Terminology

### Command
A CLI action (download, export, search, etc.).

**Syntax:** `cis-bench <command> [options] [arguments]`

**Top-level commands:**

- auth, download, export, get, list, info, search, catalog

### Subcommand
A command nested under another command.

**Example:** `catalog` has subcommands (refresh, update, search, platforms, stats)

**Syntax:** `cis-bench catalog refresh`

### Flag
An optional command-line parameter.

**Types:**

- **Boolean flags:** `--force`, `--verbose`, `--latest`
- **Value flags:** `--format xccdf`, `--style disa`, `--browser chrome`

### Output Format
How data is displayed to the user.

**For query commands:**

- table (default) - Human-readable table
- json - Machine-readable JSON
- csv - Spreadsheet-compatible CSV
- yaml - YAML format

**Usage:** `--output-format json`

**Not to be confused with:** Export format (for benchmarks)

---

## Database and Storage Terminology

### Catalog Database
SQLite database storing benchmark metadata.

**Location:** `~/.cis-bench/catalog.db`

**Tables:**

- catalog_benchmarks - Metadata for 1,300+ benchmarks
- downloaded_benchmarks - Cached benchmark JSON
- platforms, communities, owners - Lookup tables
- benchmarks_fts - FTS5 full-text search index

### FTS5
SQLite Full-Text Search version 5 - Fast text search engine.

**Usage:** Powers catalog search with fuzzy matching

**Example:** `cis-bench search "oracle cloud"` uses FTS5 to find matches

### Downloaded Benchmarks Table
Database table storing complete benchmark JSON after download.

**Purpose:** Cache benchmarks for instant re-export

**Benefit:** Export to different formats without re-downloading

---

## Technical Implementation Terminology

### Strategy Pattern
Design pattern allowing different HTML parsing implementations to coexist.

**Purpose:** Adapt to CIS WorkBench HTML changes without modifying core code

**Components:**

- `ScraperStrategy` (base class)
- `v1_current.py` (current implementation)
- `StrategyDetector` (auto-selection)

### Factory Pattern
Design pattern for creating objects without specifying exact class.

**Used in:** `ExporterFactory`

**Purpose:** Create exporters by name ("yaml", "csv", "xccdf")

**Benefit:** Add new exporters by registration, not code modification

### Config-Driven
Architecture where behavior is defined in configuration files (YAML), not code.

**Applied to:** XCCDF export via MappingEngine

**Benefit:** Change XCCDF structure by editing YAML config

### Loop-Driven Architecture
Processing fields by iterating through configuration, not hard-coded lists.

**Example:**
```python
# Loop-driven (GOOD)
for field_name, mapping in config['field_mappings'].items():
value = apply_mapping(recommendation, mapping)

# Hard-coded (BAD)
title = recommendation.title
description = recommendation.description
# ... manually list 50 fields
```

**Benefit:** Add/remove fields in config automatically updates export

---

## Compliance Tool Terminology

### OpenSCAP
Open Source SCAP scanner for Linux/Unix systems.

**Usage:** `oscap xccdf eval --profile Level_1 benchmark.xml`

**Input:** XCCDF XML files

**Output:** Compliance scan results (HTML reports, XML results)

### SCC
SCAP Compliance Checker - DISA's official SCAP validation tool.

**Purpose:** Validate XCCDF structure and run compliance scans

**Requirement:** XCCDF must follow DISA STIG conventions

**Input:** XCCDF 1.1.4 with CCIs and VulnDiscussion

### STIG Viewer
DISA tool for viewing and managing STIG checklists.

**Format:** XCCDF or CKL (checklist) files

**Usage:** Review STIG compliance results

### InSpec
Chef's compliance testing framework using Ruby DSL.

**Relationship to this CLI:**
1. Export CIS Benchmark to XCCDF
2. Convert XCCDF to InSpec using SAF CLI
3. Run InSpec scans with generated profile

**Example:** See [Workflows - Scenario 4](../user-guide/workflows.md#scenario-4)

---

## XML and Schema Terminology

### xsdata
Python library that generates dataclasses from XSD schemas.

**Usage:** Generate Python classes for XCCDF elements

**Command:** `xsdata schemas/xccdf_1.2.xsd --package models.xccdf`

**Result:** Typed Python classes matching XCCDF schema

### XSD
XML Schema Definition - Defines structure and rules for XML documents.

**XCCDF schemas:**

- `xccdf-1.1.4.xsd` - DISA STIG version
- `xccdf-1.2.xsd` - Latest XCCDF version

**Used for:** Generating xsdata models, validating XML output

### Namespace
XML namespace - Identifies a set of element names to avoid conflicts.

**XCCDF namespaces:**

- `http://checklists.nist.gov/xccdf/1.2` - Core XCCDF
- `http://purl.org/dc/elements/1.1/` - Dublin Core metadata
- `http://cisecurity.org/controls` - CIS Controls
- `http://cisecurity.org/20-cc/v8.0` - CIS Controls v8

### Embedded XML Tags
XML elements inside another element's text content (DISA STIG pattern).

**Example:**
```xml
<description>
<VulnDiscussion>Discussion text...</VulnDiscussion>
<FalsePositives>None</FalsePositives>
</description>
```

**Not standard XCCDF** - DISA convention for backward compatibility

---

## Export Terminology

### Export Style
Specific XCCDF format configuration (DISA vs CIS).

**See:** Style (above)

### Export Format
Output file type (yaml, csv, markdown, xccdf, json).

**See:** Format (above)

### Field Mapping
How Pydantic model fields map to XCCDF elements.

**Defined in:** YAML config files

**Types:**

- Simple (1:1 mapping)
- Composite (multiple sources one target)
- Embedded XML (nested tags)
- List (one source multiple elements)

### Transformation
Function applied to field values during export.

**See:** Transformation (above)

### Variable Substitution
Replacing placeholders like `{ref}` with actual values.

**Examples:**

- `{ref}` "1.1.1"
- `{ref_normalized}` "1_1_1"
- `{benchmark.title}` "CIS AlmaLinux 10 Benchmark"

**Usage:** Dynamic attributes in YAML configs

---

## CLI Workflow Terminology

### Unified Get Command
Single command that searches, downloads, and exports in one step.

**Syntax:** `cis-bench get "query" --format xccdf --style cis`

**Steps:**
1. Search catalog for query
2. Interactive selection (if multiple matches)
3. Download benchmark (or use cache)
4. Export to requested format
5. Return file path

### Interactive Mode
CLI presents a menu for user selection (uses questionary library).

**Example:** When `get` command finds multiple benchmarks

**Disable with:** `--non-interactive` flag

### Cache
Stored data to avoid re-downloading or re-processing.

**Types:**
1. **Session cache** - Saved authentication cookies
2. **Catalog cache** - Benchmark metadata database
3. **Download cache** - Full benchmark JSON in database

### Force Flag
Override cache and re-download/re-process.

**Usage:** `cis-bench download 23598 --force`

**Purpose:** Get latest version even if already cached

---

## Platform and Discovery Terminology

### Platform Taxonomy
Two-level system for categorizing benchmarks.

**Level 1:** platform_type (category)

- cloud, os, database, container, application

**Level 2:** platform (specific)

- aws, ubuntu, mysql, kubernetes, nginx

**Inferred from:** Benchmark title using pattern matching

### Full-Text Search (FTS5)
SQLite feature enabling fast fuzzy text search.

**Usage:** Catalog search uses FTS5 on benchmark titles

**Example:** Search "oracl" finds "Oracle Cloud Infrastructure"

---

## File and Directory Terminology

### Data Directory
Where CIS Benchmark CLI stores its data.

**Locations:**

- Production: `~/.cis-bench/`
- Development: `~/.cis-bench-dev/`
- Test: `/tmp/cis-bench-test/`

**Controlled by:** `CIS_BENCH_ENV` environment variable

### Session File
MozillaCookieJar file containing authentication cookies.

**Location:** `~/.cis-bench/session.cookies`

**Created by:** `cis-bench auth login`

**Format:** Netscape HTTP Cookie File

### Benchmark JSON
Downloaded benchmark in JSON format with all 19 fields.

**Example:** `almalinux10-v1.0.0-23598.json`

**Contains:** Complete Pydantic Benchmark model serialized to JSON

**Stored:**
1. File in output directory
2. JSON in catalog database (downloaded_benchmarks table)

---

## Development Terminology

### Fixture
Test data file used in automated tests.

**Location:** `tests/fixtures/`

**Types:**

- HTML fixtures (sample catalog pages, login page)
- Benchmark JSON (sample CIS benchmarks)
- XCCDF XML (reference outputs)

### Unit Test
Test of a single function/method in isolation.

**Location:** `tests/unit/`

**Example:** Testing that `strip_html()` removes HTML tags

### Integration Test
Test of multiple components working together.

**Location:** `tests/integration/`

**Example:** Testing complete XCCDF export pipeline

### E2E Test
End-to-end test of complete CLI workflow.

**Location:** `tests/e2e/`

**Example:** Testing `cis-bench download 23598 && cis-bench export 23598 --format xccdf`

---

## Acronyms

| Acronym | Full Name | Description |
|---------|-----------|-------------|
| CIS | Center for Internet Security | Publisher of security benchmarks |
| DISA | Defense Information Systems Agency | DoD cybersecurity agency |
| DoD | Department of Defense | U.S. military department |
| NIST | National Institute of Standards and Technology | U.S. standards agency |
| SCAP | Security Content Automation Protocol | Suite of security standards |
| XCCDF | eXtensible Configuration Checklist Description Format | SCAP checklist format |
| OVAL | Open Vulnerability and Assessment Language | SCAP technical checks |
| CPE | Common Platform Enumeration | Platform naming standard |
| CCE | Common Configuration Enumeration | Configuration naming |
| CCI | Control Correlation Identifier | DoD/NIST control mapping |
| STIG | Security Technical Implementation Guide | DoD security standard |
| SCC | SCAP Compliance Checker | DISA validation tool |
| IG | Implementation Group | CIS Controls grouping (IG1/IG2/IG3) |
| ATT&CK | Adversarial Tactics, Techniques, and Common Knowledge | MITRE threat framework |
| FTS | Full-Text Search | SQLite search feature |
| CLI | Command-Line Interface | Terminal-based interface |
| XSD | XML Schema Definition | XML structure definition |
| YAML | YAML Ain't Markup Language | Human-readable config format |

---

## Common Confusions

### Benchmark vs Benchmark

- **CIS Benchmark** - The source content from CIS WorkBench
- **XCCDF Benchmark** - The XML root element in XCCDF output

**Context matters!**

### Rule vs Recommendation

- **Recommendation** - CIS terminology (input)
- **Rule** - XCCDF terminology (output)
- **They map 1:1** - Each recommendation becomes one rule

### Style vs Format

- **Format** - File type (yaml, csv, xccdf)
- **Style** - XCCDF variant (disa, cis) - only applies to xccdf format

**Usage:** `--format xccdf --style disa`

### Profile vs Profile

- **CIS Profile** - Level 1/2, Server/Workstation (input)
- **XCCDF Profile** - Checklist configuration (output)

**Related but different!**

### Catalog vs Database

- **Catalog** - Logical concept (searchable list of benchmarks)
- **Database** - Physical implementation (catalog.db SQLite file)

**Often used interchangeably in docs**

---

## Related Documentation

- [Data Flow Pipeline](../developer-guide/data-flow-pipeline.md) - How data transforms through the system
- [MappingEngine Guide](../developer-guide/mapping-engine-guide.md) - Configuration-driven transformations
- [Data Model](../technical-reference/DATA_MODEL.md) - Pydantic model definitions
- [XCCDF Styles](../technical-reference/XCCDF_STYLES.md) - DISA vs CIS comparison
- [Commands Reference](../user-guide/commands-reference.md) - Complete CLI syntax

---

## Contributing to Glossary

Found a term that's unclear? Submit a PR adding it to this glossary, or open an issue requesting clarification.

**Guidelines:**

- Keep definitions concise (1-3 sentences)
- Include examples when helpful
- Link to related terms
- Note common confusions
