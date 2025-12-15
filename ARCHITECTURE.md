# CIS Benchmark CLI - Architecture and Implementation Plan

## Project Vision

**CIS Benchmark CLI** - A comprehensive command-line tool for fetching, managing, converting, and analyzing CIS benchmarks from CIS WorkBench.

### What It Is

- **Primary**: CLI tool for downloading CIS benchmarks
- **Secondary**: Format converter (JSON YAML/CSV/Markdown/XCCDF)
- **Future**: Benchmark analysis, diff, compliance checking

### What It is NOT (Yet)

- Not a compliance scanner
- Not a benchmark authoring tool
- Not a remediation tool

## Current State vs Target State

### Current State (v0.1-alpha)
```
Single-directory scripts:

- fetch.py (monolithic scraper)
- cli.py (basic commands)
- exporter.py (hand-rolled XML)
- Not installable
- Not schema-compliant
```

### Target State (v1.0)
```
Professional Python package:

- Installable: pip install cis-benchmark-cli
- CLI: cis-bench command available system-wide
- Schema-compliant XCCDF export
- Extensible architecture
- Well-tested
- Well-documented
```

## Architecture

### Visual Overview

#### Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ CIS Benchmark CLI │
│ (cis-bench) │
└─────────────────────────────────────────────────────────────────┘
 │
 ┌────────────────┼────────────────┐
 │ │ │
 ▼ ▼ ▼
 ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
 │ Fetcher │ │ Exporters │ │ CLI │
 │ Module │ │ Module │ │ Module │
 └──────────────┘ └──────────────┘ └──────────────┘
 │ │ │
 ┌───────┴────────┐ │ ┌───────┴────────┐
 │ │ │ │ │
 ▼ ▼ │ ▼ ▼
 ┌──────────┐ ┌──────────┐ │ ┌──────────┐ ┌──────────┐
 │WorkBench │ │Strategies│ │ │ Commands │ │ Output │
 │ Scraper │◄───│ Pattern │ │ │ (Click) │ │ (Rich) │
 └──────────┘ └──────────┘ │ └──────────┘ └──────────┘
 │ │ │
 │ ┌────┴────┐ │
 │ │ v1_2025 │ │
 │ │ Future │ │
 │ └─────────┘ │
 │ │
 ▼ ▼
 ┌──────────┐ ┌──────────────┐
 │ Auth │ │ Factory │
 │ Manager │ │ Pattern │
 └──────────┘ └──────────────┘
 │ │
 │ ┌────┴─────┐
 │ │ │
 │ ▼ ▼
 │ ┌─────────┐ ┌─────────┐
 ▼ │ YAML │ │ XCCDF │
 ┌──────────┐ │ CSV │ │(xsdata) │
 │ browser- │ │Markdown │ └─────────┘
 │ cookie3 │ └─────────┘
 └──────────┘
 │
 ▼
 ┌──────────┐
 │ Chrome │
 │ Firefox │
 │ Safari │
 └──────────┘
```

#### Configuration-Based XCCDF Mapping Layer

The CIS Benchmark CLI employs a configuration-driven approach to XCCDF mapping, allowing flexibility and adaptability as security frameworks and conventions evolve. Rather than hard-coding field mappings and transformations directly in the codebase, mapping logic is externalized into versioned YAML configuration files.

**Why Configuration-Based Mapping?**

- Mappings evolve as security frameworks change
- Different organizations may require different output styles
- Adjust mappings without code changes
- Version control for mapping conventions
- Clear separation of concerns

**Architecture Flow:**
```
Pydantic Benchmark Config (YAML) MappingEngine XCCDF Models XML
 (Native CIS) (Rules) (Transforms) (xsdata) (Valid)
```

**Available Configurations:**

- `configs/disa_style.yaml` - DISA STIG-compatible (CCI, VulnDiscussion, etc.)
- `configs/cis_native_style.yaml` - Clean CIS-centric (separate rationale, metadata)

**Configuration Structure:**
```yaml
field_mappings:
 title:
 target_element: "title"
 source_field: "title"
 transform: "strip_html"

 description: # Complex mapping
 target_element: "description"
 structure: "embedded_xml_tags"
 components:

 - tag: "VulnDiscussion"
 sources: ["description", "rationale"]

cci_deduplication:
 enabled: true
 algorithm: "use_cci_where_available"
```

**Benefits:**

- No hard-coded mappings
- Easy to adjust conventions
- Versioned (v1.0, v2.0)
- Testable configurations
- Extensible for custom styles

See: `docs/MAPPING_ENGINE_DESIGN.md` for complete specification

**XCCDF Version Handling:**

- DISA style: Uses XCCDF 1.1.4 (what real STIGs use)
 - Simple IDs allowed: `CIS-6_1_1`, `CIS-6_1_1_rule`
 - Models: `cis_bench/models/xccdf_v1_1/`
- CIS Native style: Uses XCCDF 1.2 (modern standard)
 - Pattern IDs required: `xccdf_org.cisecurity_rule_*`
 - Models: `cis_bench/models/xccdf/`
- Config specifies version: `xccdf_version: "1.1.4"` or `"1.2"`
- MappingEngine loads appropriate models automatically

**DISA Conventions:**

- Documented: `schemas/disa_conventions/v1.10.0.yaml`
- Reverse-engineered from RHEL 9 + Ubuntu 24.04 STIGs
- Specifies required elements, order, CCI format, etc.
- Version-tracked for DISA evolution

#### Data Flow with JSON Schema (Canonical Format)

```
User Command: cis-bench download 22605 --browser chrome --format xccdf
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. CLI Layer (Click) │
│ - Parse arguments │
│ - Validate options │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Auth Manager │
│ - Extract cookies from Chrome via browser-cookie3 │
│ - Create authenticated requests.Session │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. WorkbenchScraper │
│ a. GET benchmark page Extract title │
│ b. GET navtree API Parse JSON Get rec URLs │
│ c. For each recommendation: │
│ - GET recommendation page │
│ - Detect HTML strategy (auto) │
│ - Extract fields using strategy │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Strategy Pattern │
│ ┌──────────────────────────────────────────┐ │
│ │ StrategyDetector.detect_strategy(html) │ │
│ │ Checks v1_2025_10.is_compatible() │ │
│ │ Returns WorkbenchV1Strategy │ │
│ └──────────────────────────────────────────┘ │
│ │ │
│ ▼ │
│ ┌──────────────────────────────────────────┐ │
│ │ WorkbenchV1Strategy.extract_data(html) │ │
│ │ Uses element ID selectors │ │
│ │ Returns: {assessment, description, │ │
│ │ rationale, audit, ...} │ │
│ └──────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Data Aggregation and Validation │
│ - Combine navtree metadata + scraped content │
│ - Result: List[Recommendation] │
│ - VALIDATE against our JSON Schema │
│ - Save as JSON (canonical format) │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5a. JSON Schema Validation (cis_bench/models/schema.json) │
│ │
│ { │
│ "$schema": "http://json-schema.org/draft-07/schema#", │
│ "type": "object", │
│ "properties": { │
│ "title": {"type": "string"}, │
│ "benchmark_id": {"type": "string"}, │
│ "recommendations": { │
│ "type": "array", │
│ "items": { │
│ "type": "object", │
│ "required": ["ref", "title", "url"], │
│ "properties": { │
│ "ref": {"type": "string"}, │
│ "title": {"type": "string"}, │
│ "description": {"type": ["string", "null"]}, │
│ # ... all fields defined │
│ } │
│ } │
│ } │
│ } │
│ } │
│ │
│ Data validates Proceed to export │
│ Validation fails Error with details │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Export via Factory (Maps from our schema target format) │
│ ExporterFactory.create('xccdf') │
│ │ │
│ ▼ │
│ XCCDFExporter (uses xsdata models) │
│ │ │
│ ▼ │
│ cis_bench.models.xccdf.Benchmark (from NIST XSD) │
│ │ │
│ ▼ │
│ benchmark.to_xml() Valid XCCDF 1.2 XML │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ 7. Output (Rich) │
│ - Progress bars during download │
│ - Success message with file path │
│ - Table showing benchmark stats │
└─────────────────────────────────────────────────────────────────┘
```

#### Strategy Pattern Flow (HTML Adaptation)

```
When CIS WorkBench HTML Changes:
════════════════════════════════════════════════════════════════

OLD APPROACH (Breaks immediately):
 HTML Change Element IDs different Scraper fails

NEW APPROACH (Resilient):

┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Create New Strategy │
│ │
│ class WorkbenchV2Strategy(ScraperStrategy): │
│ version = "v2_2026_01" │
│ selectors = { │
│ "assessment": {"class": "new-assessment-class"}, │
│ # ... new selectors │
│ } │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Register Strategy │
│ │
│ # In strategies/__init__.py │
│ from .v2_new import WorkbenchV2Strategy │
│ │
│ # Auto-registered via import │
│ StrategyDetector.strategies = [ │
│ WorkbenchV2Strategy(), # Newest first │
│ WorkbenchV1Strategy(), # Fallback │
│ ] │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Auto-Detection │
│ │
│ scraper.fetch_recommendation(url) │
│ │ │
│ ▼ │
│ StrategyDetector.detect_strategy(html) │
│ │ │
│ ├─► Try v2.is_compatible(html) YES │
│ │ Use WorkbenchV2Strategy │
│ │ │
│ ├─► Try v1.is_compatible(html) NO │
│ │ Skip │
│ │ │
│ ▼ │
│ Return: WorkbenchV2Strategy instance │
└─────────────────────────────────────────────────────────────────┘

Result: Tool continues working with new HTML!
```

#### Factory Pattern Flow (Export Formats)

```
Adding New Export Format:
════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Create Exporter Class │
│ │
│ class PDFExporter(BaseExporter): │
│ def export(self, data, output_path): │
│ # Convert to PDF │
│ pass │
│ │
│ def get_file_extension(self): │
│ return "pdf" │
│ │
│ def format_name(self): │
│ return "PDF" │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Register with Factory │
│ │
│ # At bottom of pdf_exporter.py │
│ ExporterFactory.register('pdf', PDFExporter) │
└─────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Automatically Available in CLI │
│ │
│ $ cis-bench export benchmark.json --format pdf │
│ │
│ CLI automatically knows about PDF format! │
│ No CLI code changes needed! │
└─────────────────────────────────────────────────────────────────┘

Current Registered Formats:
 ┌────────────────────────────────────────┐
 │ ExporterFactory._exporters = { │
 │ 'json': JSONExporter, │
 │ 'yaml': YAMLExporter, │
 │ 'csv': CSVExporter, │
 │ 'markdown': MarkdownExporter, │
 │ 'md': MarkdownExporter, │
 │ 'xccdf': XCCDFExporter, │
 │ 'xml': XCCDFExporter, │
 │ 'pdf': PDFExporter, New! │
 │ } │
 └────────────────────────────────────────┘
```

#### Package Dependency Graph

```
┌─────────────────────────────────────────────────────────────────┐
│ cis_bench Package │
└─────────────────────────────────────────────────────────────────┘
 │
 ┌────────────────────────┼────────────────────────┐
 │ │ │
 ▼ ▼ ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ models │ │ fetcher │ │ exporters │
│ │ │ │ │ │
│ benchmark │ │ workbench │ │ base │
│ ├─xccdf/ │◄───────│ ├─auth │ │ ├─json │
│ └─*.py │ │ └─strat/ │ │ ├─yaml │
│ (xsdata │ │ ├─base│ │ ├─csv │
│ generated) │ │ ├─v1 │ │ ├─md │
└──────────────┘ │ └─det │ │ └─xccdf──┼──┐
 ▲ └──────────────┘ └──────────────┘ │
 │ │ │ │
 │ │ │ │
 └────────────────────────┴────────────────────────┴───────┘
 │
 ▼
 ┌──────────────┐
 │ cli │
 │ │
 │ app │
 │ commands/ │
 │ ├─download │
 │ ├─export │
 │ ├─list │
 │ └─info │
 └──────────────┘
 │
 ▼
 ┌──────────────┐
 │ User │
 │ (Terminal) │
 └──────────────┘

External Dependencies:
 ┌──────────────────────────────────────────────────┐
 │ requests, beautifulsoup4, browser-cookie3 │
 │ click, rich, questionary │
 │ xsdata, lxml, pyyaml │
 └──────────────────────────────────────────────────┘
```

#### Complete Workflow Sequence

```
User runs: cis-bench download 22605 --browser chrome --format xccdf
═══════════════════════════════════════════════════════════════════════

┌─ Phase 1: Authentication ─────────────────────────────────────────┐
│ │
│ CLI AuthManager.get_session(browser='chrome') │
│ │ │
│ ├─ browser_cookie3.chrome(domain='workbench.cisecurity') │
│ │ │
│ ├─ Read Chrome SQLite DB │
│ │ ~/.../Chrome/Default/Cookies │
│ │ │
│ └─ Return authenticated requests.Session │
│ │
└───────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─ Phase 2: Fetch Benchmark ────────────────────────────────────────┐
│ │
│ WorkbenchScraper(session) │
│ │ │
│ ├─ GET /benchmarks/22605 │
│ │ └─ Extract: "CIS Amazon EKS Benchmark v1.8.0" │
│ │ │
│ ├─ GET /api/v1/benchmarks/22605/navtree │
│ │ └─ Parse JSON 50 recommendation URLs │
│ │ │
│ └─ For each recommendation (with Rich progress bar): │
│ ┌───────────────────────────────────────────────────┐ │
│ │ GET /sections/X/recommendations/Y │ │
│ │ │ │ │
│ │ ├─ HTML response │ │
│ │ │ │ │
│ │ ├─ StrategyDetector.detect_strategy(html) │ │
│ │ │ ├─ Check v1_2025_10.is_compatible() │ │
│ │ │ └─ Use WorkbenchV1Strategy │ │
│ │ │ │ │
│ │ └─ strategy.extract_recommendation(html) │ │
│ │ └─ Find elements by ID │ │
│ │ └─ Return: {assessment, description, ...} │ │
│ └───────────────────────────────────────────────────┘ │
│ │
│ Result: {title, recommendations: [...50 items...]} │
│ │
└───────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─ Phase 3: Export via Factory ─────────────────────────────────────┐
│ │
│ ExporterFactory.create('xccdf') │
│ │ │
│ └─ Returns: XCCDFExporter instance │
│ │
│ XCCDFExporter.export(data, 'output.xml') │
│ │ │
│ ├─ Map our data xsdata XCCDF models │
│ │ from cis_bench.models.xccdf import Benchmark, Rule │
│ │ │
│ │ benchmark = Benchmark( │
│ │ id="cis_eks", │
│ │ status=[Status("draft")], │
│ │ title="CIS Amazon EKS...", │
│ │ version="1.8.0" │
│ │ ) │
│ │ │
│ │ For each recommendation: │
│ │ rule = Rule(id=..., title=..., description=...) │
│ │ benchmark.rule.append(rule) │
│ │ │
│ └─ benchmark.to_xml(pretty_print=True) │
│ └─ NIST XCCDF 1.2 compliant XML │
│ │
└───────────────────────────────────────────────────────────────────┘
 │
 ▼
┌─ Phase 4: Output ─────────────────────────────────────────────────┐
│ │
│ Rich Console Output: │
│ │
│ Downloaded 50 recommendations │
│ Exported to XCCDF: output.xml (245 KB) │
│ Validated against NIST schema │
│ │
└───────────────────────────────────────────────────────────────────┘
```

#### Strategy Pattern in Action

```
Scenario: CIS WorkBench updates HTML (element IDs change)
═══════════════════════════════════════════════════════════════

BEFORE (Old element IDs):
 <div id="description-recommendation-data">...</div>

AFTER (New structure):
 <div class="recommendation-description" data-field="desc">...</div>

─────────────────────────────────────────────────────────────────

Our Response:

1. Create new strategy file:
 ┌──────────────────────────────────────────────────┐
 │ cis_bench/fetcher/strategies/v2_2026_01.py │
 │ │
 │ class WorkbenchV2Strategy(ScraperStrategy): │
 │ version = "v2_2026_01" │
 │ │
 │ selectors = { │
 │ "description": { │
 │ "class": "recommendation-description" │
 │ } │
 │ } │
 │ │
 │ def is_compatible(self, html): │
 │ # Check for new structure markers │
 │ return 'recommendation-description' in html│
 └────────────────────────────────────────────────── ┘

2. Register in detector:
 ┌──────────────────────────────────────────────────┐
 │ strategies/detector.py │
 │ │
 │ _strategies = [ │
 │ WorkbenchV2Strategy(), # NEW (highest) │
 │ WorkbenchV1Strategy(), # OLD (fallback) │
 │ ] │
 └──────────────────────────────────────────────────┘

3. Tool automatically adapts:
 ┌──────────────────────────────────────────────────┐
 │ User runs: cis-bench download 22605 │
 │ │
 │ StrategyDetector checks: │
 │ ├─ v2.is_compatible(html)? YES │
 │ └─ Use WorkbenchV2Strategy │
 │ │
 │ Download succeeds! No user action needed! │
 └──────────────────────────────────────────────────┘

4. Old benchmarks still work:
 ┌──────────────────────────────────────────────────┐
 │ Downloading archived benchmark (old HTML): │
 │ │
 │ StrategyDetector checks: │
 │ ├─ v2.is_compatible(html)? NO │
 │ ├─ v1.is_compatible(html)? YES │
 │ └─ Use WorkbenchV1Strategy │
 │ │
 │ Still works! Backward compatible! │
 └──────────────────────────────────────────────────┘

Time to fix when HTML changes: 15-30 minutes

 - Create new strategy class
 - Test compatibility detection
 - Deploy
```

#### XCCDF Generation Flow (xsdata)

```
Using xsdata for Schema-Compliant XCCDF:
═══════════════════════════════════════════════════════════════

┌─ One-Time Setup ──────────────────────────────────────────────┐
│ │
│ 1. Download NIST schema: │
│ xccdf_1.2.xsd from csrc.nist.gov │
│ │
│ 2. Generate Python models: │
│ $ xsdata xccdf_1.2.xsd --package cis_bench.models.xccdf │
│ │
│ 3. Result: Python dataclasses with XML serialization │
│ ┌────────────────────────────────────────────────┐ │
│ │ cis_bench/models/xccdf/xccdf_1_2.py │ │
│ │ │ │
│ │ @dataclass │ │
│ │ class Benchmark: │ │
│ │ id: str │ │
│ │ status: List[Status] │ │
│ │ title: str │ │
│ │ version: str │ │
│ │ rule: List[Rule] = field(default_factory=list)│ │
│ │ │ │
│ │ def to_xml(self) -> str: │ │
│ │ # Auto-generated serialization │ │
│ └────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
 │
 ▼
┌─ Runtime Usage ───────────────────────────────────────────────┐
│ │
│ from cis_bench.models.xccdf import Benchmark, Rule, Status │
│ │
│ # Create schema-compliant objects │
│ benchmark = Benchmark( │
│ id="cis_eks_benchmark", │
│ status=[Status(value="draft")], │
│ title="CIS Amazon EKS Benchmark v1.8.0", │
│ version="1.8.0" │
│ ) │
│ │
│ # Add rules (auto-validated by dataclass) │
│ for rec in recommendations: │
│ rule = Rule( │
│ id=f"rule_{rec['ref'].replace('.', '_')}", │
│ title=rec['title'], │
│ description=rec['description'] │
│ ) │
│ benchmark.rule.append(rule) │
│ │
│ # Export to XML (xsdata handles serialization) │
│ xml_output = benchmark.to_xml(pretty_print=True) │
│ │
│ # Result: Valid XCCDF 1.2 XML │
│ │
└───────────────────────────────────────────────────────────────┘
 │
 ▼
┌─ Validation ──────────────────────────────────────────────────┐
│ │
│ $ xmllint --schema xccdf_1.2.xsd output.xml --noout │
│ │
│ output.xml validates │
│ │
│ Compatible with: │
│ - OpenSCAP │
│ - SCAP Compliance Checker (SCC) │
│ - Nessus │
│ - Any XCCDF 1.2 compliant tool │
│ │
└───────────────────────────────────────────────────────────────┘
```

### High-Level Design Principles

1. **Separation of Concerns**: Fetching, parsing, exporting, CLI are separate
2. **SOLID Principles**: Single responsibility, Open/Closed, Dependency injection
3. **Factory Pattern**: Exporters are pluggable
4. **Schema-First**: Use official NIST XCCDF schema (xsdata generated)
5. **Testability**: All components independently testable
6. **Extensibility**: Easy to add new formats, sources, features

### Package Structure

```
cis-benchmark-cli/
├── cis_bench/ # Main package (renamed for clarity)
│ ├── __init__.py # Package version, exports
│ │
│ ├── models/ # Data models
│ │ ├── __init__.py
│ │ ├── benchmark.py # Internal benchmark data model (dataclasses)
│ │ ├── schema.json # JSON Schema - OUR CANONICAL FORMAT
│ │ └── xccdf/ # XCCDF schema models (xsdata generated)
│ │ ├── __init__.py
│ │ └── xccdf_1_2.py # Generated from NIST XSD
│ │
│ ├── fetcher/ # Downloading/scraping CIS WorkBench
│ │ ├── __init__.py
│ │ ├── workbench.py # CIS WorkBench scraper (uses strategies)
│ │ ├── auth.py # Cookie management (browser-cookie3)
│ │ ├── http.py # HTTP session wrapper
│ │ └── strategies/ # Scraper strategies (HTML version adapters)
│ │ ├── __init__.py
│ │ ├── base.py # ScraperStrategy ABC
│ │ ├── detector.py # StrategyDetector (auto-select)
│ │ ├── v1_current.py # Current HTML version (2025-10)
│ │ └── config/ # Optional: YAML configs for selectors
│ │ └── workbench_v1.yaml
│ │
│ ├── exporters/ # Export to different formats
│ │ ├── __init__.py
│ │ ├── base.py # BaseExporter (ABC), ExporterFactory
│ │ ├── json.py # JSON exporter (our native format)
│ │ ├── yaml.py # YAML exporter
│ │ ├── csv.py # CSV exporter
│ │ ├── markdown.py # Markdown exporter
│ │ └── xccdf.py # XCCDF exporter (uses xsdata models)
│ │
│ ├── utils/ # Shared utilities
│ │ ├── __init__.py
│ │ ├── logging.py # Logging setup
│ │ └── validation.py # Data validation helpers
│ │
│ └── cli/ # CLI interface
│ ├── __init__.py
│ ├── app.py # Main Click app
│ ├── commands/ # Command modules
│ │ ├── __init__.py
│ │ ├── download.py # Download command
│ │ ├── export.py # Export command
│ │ ├── list.py # List command
│ │ └── info.py # Info command
│ └── output.py # Rich console output helpers
│
├── tests/ # Test suite
│ ├── __init__.py
│ ├── test_fetcher.py
│ ├── test_exporters.py
│ ├── test_xccdf_schema_compliance.py
│ ├── test_cli.py
│ └── fixtures/
│ ├── sample_navtree.json
│ ├── sample_recommendation.html
│ └── expected_xccdf.xml
│
├── scripts/ # Development/build scripts
│ ├── generate_xccdf_models.sh # Regenerate XCCDF models from XSD
│ └── download_schemas.sh # Download NIST schemas
│
├── docs/ # Documentation
│ ├── README.md # User documentation
│ ├── ARCHITECTURE.md # This file
│ ├── CLAUDE.md # Developer guide for Claude Code
│ ├── CONTRIBUTING.md # Contribution guidelines
│ └── examples/ # Usage examples
│ ├── basic_usage.md
│ └── advanced_usage.md
│
├── setup.py # Package installation
├── requirements.txt # Runtime dependencies
├── requirements-dev.txt # Development dependencies
├── pytest.ini # Pytest configuration
├── .gitignore
└── LICENSE # Apache 2.0 License
```

### Component Design

#### 1. Models

**Purpose**: Define data structures

```python
# benchmark.py
@dataclass
class Recommendation:
 ref: str
 title: str
 description: Optional[str]
 rationale: Optional[str]
 audit: Optional[str]
 remediation: Optional[str]
 # ... other fields

@dataclass
class Benchmark:
 title: str
 version: str
 recommendations: List[Recommendation]
 metadata: Dict[str, Any]
```

**XCCDF Models**: Auto-generated from NIST schema using xsdata

- Type-safe
- Schema-compliant
- Bi-directional XML ↔ Python

#### 2. Fetcher (Strategy Pattern for HTML Changes)

**Purpose**: Download benchmarks from CIS WorkBench with adaptable scraping strategies

**Problem**: CIS WorkBench HTML structure can change, breaking our selectors

**Solution**: Strategy pattern + configuration-based selectors

```python
# strategies/base.py
class ScraperStrategy(ABC):
 """Base class for scraper strategies (different HTML versions)."""

 @property
 @abstractmethod
 def version(self) -> str:
 """Strategy version identifier."""
 pass

 @property
 @abstractmethod
 def selectors(self) -> dict:
 """CSS/XPath selectors for this HTML version."""
 pass

 @abstractmethod
 def extract_recommendation(self, html: str) -> dict:
 """Extract recommendation data from HTML."""
 pass

 def is_compatible(self, html: str) -> bool:
 """Check if this strategy works with given HTML."""
 # Look for version indicators in HTML
 pass

# strategies/v1_current.py
class WorkbenchV1Strategy(ScraperStrategy):
 """Current CIS WorkBench HTML structure (as of 2025-10)."""

 version = "v1_2025_10"

 selectors = {
 "assessment": {"id": "automated_scoring-recommendation-data"},
 "description": {"id": "description-recommendation-data"},
 "rationale": {"id": "rationale_statement-recommendation-data"},
 # ... other selectors
 }

 def extract_recommendation(self, html: str) -> dict:
 soup = BeautifulSoup(html, 'html.parser')
 data = {}

 for field, selector in self.selectors.items():
 if 'id' in selector:
 elem = soup.find(id=selector['id'])
 elif 'class' in selector:
 elem = soup.find(class_=selector['class'])
 elif 'xpath' in selector:
 # Use lxml for XPath
 elem = soup.xpath(selector['xpath'])

 data[field] = elem.decode_contents().strip() if elem else None

 return data

 def is_compatible(self, html: str) -> bool:
 # Check for known element that only exists in this version
 soup = BeautifulSoup(html, 'html.parser')
 return soup.find(id="automated_scoring-recommendation-data") is not None

# strategies/factory.py
class StrategyDetector:
 """Auto-detects and selects the correct scraper strategy."""

 strategies = [
 WorkbenchV1Strategy(),
 # WorkbenchV2Strategy(), # Add when site changes
 # WorkbenchLegacyStrategy(), # Fallback for old benchmarks
 ]

 @classmethod
 def detect_strategy(cls, html: str) -> ScraperStrategy:
 """Auto-detect which strategy to use."""
 for strategy in cls.strategies:
 if strategy.is_compatible(html):
 logger.info(f"Using scraper strategy: {strategy.version}")
 return strategy

 raise ValueError("No compatible scraper strategy found. CIS WorkBench HTML may have changed.")

 @classmethod
 def register_strategy(cls, strategy: ScraperStrategy):
 """Register custom strategy (for testing or new versions)."""
 cls.strategies.insert(0, strategy) # Prepend (check newest first)

# workbench.py
class WorkbenchScraper:
 def __init__(self, session: requests.Session, strategy: ScraperStrategy = None):
 self.session = session
 self.strategy = strategy # Allow manual override
 self._detected_strategy = None

 def fetch_recommendation(self, rec_url: str) -> dict:
 """Fetch single recommendation with auto-strategy detection."""
 html = self._fetch_html(rec_url)

 # Auto-detect strategy on first fetch (or use override)
 if not self._detected_strategy and not self.strategy:
 self._detected_strategy = StrategyDetector.detect_strategy(html)

 strategy = self.strategy or self._detected_strategy
 return strategy.extract_recommendation(html)

 def fetch_benchmark(self, benchmark_id: str) -> Benchmark:
 """Fetch complete benchmark."""
 pass

 def fetch_navtree(self, benchmark_id: str) -> dict:
 """Fetch navigation tree."""
 pass

# auth.py
class AuthManager:
 @staticmethod
 def get_session(browser: str = None,
 cookies_file: str = None) -> requests.Session:
 """Get authenticated session."""
 pass
```

**Configuration File Support** (Optional Enhancement):

```yaml
# ~/.cis-bench/scrapers/workbench_v1.yaml
version: "v1_2025_10"
name: "CIS WorkBench Current"
compatibility_check:
 element_id: "automated_scoring-recommendation-data"

selectors:
 assessment:
 type: id
 value: "automated_scoring-recommendation-data"
 description:
 type: id
 value: "description-recommendation-data"
 rationale:
 type: id
 value: "rationale_statement-recommendation-data"
 impact:
 type: id
 value: "impact_statement-recommendation-data"
 audit:
 type: id
 value: "audit_procedure-recommendation-data"
 remediation:
 type: id
 value: "remediation_procedure-recommendation-data"
 default_value:
 type: id
 value: "default_value-recommendation-data"
 artifact_eq:
 type: id
 value: "artifact_equation-recommendation-data"
 mitre_mapping:
 type: id
 value: "mitre_mappings-recommendation-data"
 references:
 type: id
 value: "references-recommendation-data"
```

**Benefits**:

- **When HTML changes**: Create new strategy, register it
- **Auto-detection**: Automatically uses correct strategy
- **Override**: Can force specific strategy for testing
- **Versioned**: Track which HTML version we're scraping
- **Configurable**: Selectors in config files (optional)
- **Extensible**: Easy to add new strategies
- **Debuggable**: Know which strategy is being used

#### 3. Exporters (Factory Pattern)

**Purpose**: Convert benchmarks to various formats

```python
# base.py
class BaseExporter(ABC):
 @abstractmethod
 def export(self, benchmark: Benchmark, output_path: str) -> str:
 """Export benchmark to file. Returns output path."""
 pass

 @abstractmethod
 def get_file_extension(self) -> str:
 """Get default file extension for this format."""
 pass

class ExporterFactory:
 _exporters = {
 'json': JSONExporter,
 'yaml': YAMLExporter,
 'csv': CSVExporter,
 'markdown': MarkdownExporter,
 'xccdf': XCCDFExporter,
 }

 @classmethod
 def create(cls, format_type: str) -> BaseExporter:
 """Create exporter for given format."""
 if format_type not in cls._exporters:
 raise ValueError(f"Unsupported format: {format_type}")
 return cls._exporters[format_type]()

 @classmethod
 def register(cls, format_type: str, exporter_class: Type[BaseExporter]):
 """Register custom exporter (for plugins)."""
 cls._exporters[format_type] = exporter_class

# xccdf.py
class XCCDFExporter(BaseExporter):
 def export(self, benchmark: Benchmark, output_path: str) -> str:
 # Use xsdata-generated models
 from cis_bench.models.xccdf import Benchmark as XCCDFBenchmark
 from cis_bench.models.xccdf import Rule, Status

 xccdf = XCCDFBenchmark(
 id="cis_benchmark",
 status=[Status(value="draft")],
 # ... map our data to XCCDF models
 )

 # xsdata handles XML serialization
 xml_output = xccdf.to_xml()
 with open(output_path, 'w') as f:
 f.write(xml_output)

 return output_path
```

#### 4. CLI

**Purpose**: User interface

```python
# app.py
@click.group()
@click.version_option(version='1.0.0')
@click.option('--verbose', '-v', is_flag=True)
def cli(verbose):
 """CIS Benchmark CLI - Fetch and manage CIS benchmarks."""
 setup_logging(verbose)

# commands/download.py
@cli.command()
@click.argument('benchmark_ids', nargs=-1)
@click.option('--browser', type=click.Choice(['chrome', 'firefox', 'edge', 'safari']))
@click.option('--output-dir', '-o', default='./benchmarks')
@click.option('--format', '-f', multiple=True, default=['json'])
def download(benchmark_ids, browser, output_dir, format):
 """Download CIS benchmarks."""
 # Use Rich progress bars
 # Use WorkbenchScraper
 # Use ExporterFactory for each format
 pass
```

## Detailed Implementation Order

### Phase 1: Foundation and Schema Generation (45-60 min)

**Goal**: Set up proper package structure with XCCDF models

1. **Install xsdata**
 ```bash
 pip install xsdata[cli]
 ```

2. **Generate XCCDF models from NIST schema**
 ```bash
 # Download XSD
 curl -o xccdf_1.2.xsd https://csrc.nist.gov/schema/xccdf/1.2/xccdf_1.2.xsd

 # Generate Python models
 xsdata xccdf_1.2.xsd --package cis_bench.models.xccdf
 ```

3. **Create package structure**
 ```bash
 mkdir -p cis_bench/{models/xccdf,fetcher,exporters,cli/commands,utils}
 touch cis_bench/__init__.py
 # ... create all __init__.py files
 ```

4. **Create base exporter pattern**

 - `cis_bench/exporters/base.py` - BaseExporter ABC
 - `cis_bench/exporters/__init__.py` - ExporterFactory

5. **Move existing code into new structure**

 - `fetch.py` `cis_bench/fetcher/workbench.py`
 - `cookies_manager.py` `cis_bench/fetcher/auth.py`

### Phase 2: Implement Exporters (45 min)

**Goal**: All exporters using factory pattern, XCCDF using xsdata

6. **Implement each exporter**

 - JSON (simple, native format)
 - YAML (using PyYAML)
 - CSV (using csv module)
 - Markdown (template-based)
 - **XCCDF (using xsdata models)**

7. **Test each exporter**

 - Unit tests with fixtures
 - XCCDF validation against schema

### Phase 3: CLI Refactor (45 min)

**Goal**: Professional CLI with all commands

8. **Refactor CLI to use new architecture**

 - Split commands into separate modules
 - Use Rich for all output
 - Implement download with progress bars

9. **Create setup.py**
 ```python
 setup(
 name='cis-benchmark-cli',
 version='1.0.0',
 packages=find_packages(),
 entry_points={
 'console_scripts': [
 'cis-bench=cis_bench.cli.app:cli',
 ],
 },
 )
 ```

10. **Test installation**
 ```bash
 pip install -e .
 cis-bench --help
 ```

### Phase 4: Testing and Documentation (45 min)

**Goal**: Production-ready quality

11. **Write tests**

 - Unit tests for each component
 - Integration tests for CLI
 - XCCDF schema validation tests

12. **Update documentation**

 - README.md with examples
 - CLAUDE.md with architecture
 - Inline docstrings

13. **End-to-end testing**

 - Download benchmark
 - Export to all formats
 - Validate XCCDF output

## Future Capabilities (Post v1.0)

### v1.1 - Enhanced Management

- `cis-bench diff <bench1> <bench2>` - Compare benchmarks
- `cis-bench search <keyword>` - Search within benchmarks
- `cis-bench merge <bench1> <bench2>` - Merge benchmarks

### v1.2 - Analysis

- `cis-bench analyze <benchmark>` - Benchmark statistics
- `cis-bench validate <xccdf>` - Validate XCCDF against schema
- `cis-bench report <benchmark>` - Generate HTML reports

### v1.3 - Integration

- `cis-bench import <file>` - Import from other formats
- `cis-bench sync <source>` - Sync from multiple sources
- API server mode for CI/CD integration

### v2.0 - Compliance

- Integration with scanning tools (InSpec, SCAP)
- Compliance mapping (CIS NIST 800-53, etc.)
- Benchmark customization/tailoring

## Design Decisions and Rationale

### Why xsdata over manual XML?

- Schema compliance guaranteed
- Type safety
- Automatic validation
- Less code to maintain
- Bi-directional (can read XCCDF too in future)

### Why Factory Pattern for exporters?

- Easy to add new formats
- Plugin architecture (register custom exporters)
- Testable in isolation
- Clean separation of concerns

### Why separate CLI commands into modules?

- Each command is independently testable
- Easier to maintain
- Can be extended by plugins
- Clear ownership

### Why browser-cookie3 over manual cookies?

- Better UX (no manual cookie export)
- Works on all platforms
- Automatic cookie refresh

## Success Criteria

### v1.0 Must Have

- Installable via pip
- `cis-bench` command works system-wide
- Download benchmarks from CIS WorkBench
- Export to JSON, YAML, CSV, Markdown, **XCCDF**
- XCCDF validates against NIST schema
- Progress bars for downloads
- Unit tests for core components
- Documentation (README, inline docs)

### v1.0 Nice to Have

- Interactive mode with questionary
- Config file support (.cis-bench.yaml)
- Comprehensive logging
- Integration tests

## Technical Debt to Avoid

 **Don't**:

- Mix concerns (fetching in exporters, etc.)
- Hard-code paths or URLs
- Skip error handling
- Ignore schema validation
- Skip tests for "later"
- Use global state

 **Do**:

- Use dependency injection
- Handle errors gracefully
- Log appropriately
- Validate inputs
- Write tests as you go
- Use type hints

## Tools and Technologies

### Runtime Dependencies

- **click**: CLI framework
- **rich**: Terminal styling, progress bars
- **questionary**: Interactive prompts
- **requests**: HTTP client
- **beautifulsoup4**: HTML parsing
- **browser-cookie3**: Browser cookie extraction
- **pyyaml**: YAML export
- **xsdata[cli]**: XCCDF models generation
- **lxml**: XML processing (required by xsdata)

### Development Dependencies

- **pytest**: Testing framework
- **pytest-mock**: Mocking
- **black**: Code formatting
- **mypy**: Type checking
- **flake8**: Linting

## Naming Conventions

### Package: `cis-benchmark-cli` (PyPI)

- Hyphenated for pip
- Clear, descriptive name
- Not too long

### Module: `cis_bench` (Python)

- Underscore for Python import
- Short, memorable
- Professional

### CLI Command: `cis-bench`

- Hyphenated for CLI
- Tab-completable
- Clear namespace

### Commands:

- `cis-bench download` - Fetch benchmarks
- `cis-bench export` - Convert formats
- `cis-bench list` - Show downloaded benchmarks
- `cis-bench info` - Show benchmark details
- Future: `diff`, `analyze`, `validate`, etc.

## Next Steps

1. Review this architecture document
2. Get approval on:

 - Package name (`cis-benchmark-cli`)
 - CLI command (`cis-bench`)
 - Overall structure
3. Execute Phase 1 Phase 2 Phase 3 Phase 4
4. Ship v1.0

---

**Version**: 1.0.0
**Author**: MITRE SAF Team
**Last Updated**: December 2025
**Status**: Production Release
