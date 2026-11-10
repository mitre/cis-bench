# CIS Benchmark CLI - Data Model and JSON Schema

!!! info "Documentation Path"
    **You are here:** Technical Reference > Data Model

    - **For architecture:** See [Architecture Overview](../developer-guide/architecture.md)
    - **For data flow:** See [Data Flow Pipeline](../developer-guide/data-flow-pipeline.md)

## Overview

This document defines our **canonical data format** for CIS benchmarks. All data flows through this format.

## Data Flow Architecture

```mermaid
flowchart LR
    subgraph Input["Input Sources"]
        WB["CIS WorkBench<br/>(text as Markdown)"]
        API["CIS API<br/>(JSON navtree)"]
        SCAP["Future: SCAP"]
        EXCEL["Future: Excel"]
        PDF["Future: PDF"]
    end

    subgraph Canonical["Canonical Format"]
        SCHEMA["JSON Schema<br/>(Our Format)<br/>VALIDATED"]
    end

    subgraph Output["Output Formats"]
        XCCDF["XCCDF XML"]
        YAML["YAML"]
        CSV["CSV"]
        MD["Markdown"]
        JSON["JSON"]
        FUTURE["Future formats"]
    end

    WB --> SCHEMA
    API --> SCHEMA
    SCAP --> SCHEMA
    EXCEL --> SCHEMA
    PDF --> SCHEMA

    SCHEMA --> XCCDF
    SCHEMA --> YAML
    SCHEMA --> CSV
    SCHEMA --> MD
    SCHEMA --> JSON
    SCHEMA --> FUTURE

    style SCHEMA fill:#90EE90,stroke:#006400,stroke-width:3px
    style Input fill:#E8F4F8,stroke:#0066CC
    style Output fill:#FFF4E6,stroke:#CC6600
```

**KEY PRINCIPLE:** All data MUST validate against our JSON Schema before it can be exported to any format.

## Why JSON Schema as Canonical Format?

### Benefits

**Single Source of Truth**

- All exporters map from ONE format
- No exporter-specific logic in scraper
- Clear contract between components

**Validation**

- Ensure scraped data is complete
- Catch extraction errors early
- Verify required fields present

**Documentation**

- Self-documenting data format
- Clear field definitions
- Type information

**Versioning**

- Schema v1.0, v2.0 as needs evolve
- Backward compatibility tracking
- Migration paths

**Code Generation**

- Can generate Python dataclasses from schema
- Type hints from schema
- Validation code auto-generated

**Testing**

- Validate test fixtures
- Ensure exporters get expected input
- Clear test assertions

## Our JSON Schema

### Location
`cis_bench/models/schema.json`

### Structure

```json
{
"$schema": "http://json-schema.org/draft-07/schema#",
"$id": "https://github.com/yourusername/cis-benchmark-cli/schemas/benchmark-v1.0.json",
"title": "CIS Benchmark",
"description": "Canonical data format for CIS Benchmark downloaded from CIS WorkBench",
"type": "object",
"required": ["title", "benchmark_id", "url", "version", "recommendations"],
"properties": {
"title": {
"type": "string",
"description": "Full benchmark title (e.g., 'CIS Amazon EKS Benchmark v1.8.0')",
"examples": ["CIS Amazon EKS Benchmark v1.8.0", "CIS NGINX Benchmark vNEXT"]
},
"benchmark_id": {
"type": "string",
"description": "CIS WorkBench benchmark ID",
"pattern": "^[0-9]+$",
"examples": ["22605", "18528"]
},
"url": {
"type": "string",
"format": "uri",
"description": "Source URL of the benchmark"
},
"version": {
"type": "string",
"description": "Benchmark version (extracted from title or metadata)",
"examples": ["v1.8.0", "vNEXT", "v1.0.0"]
},
"published_date": {
"type": ["string", "null"],
"format": "date",
"description": "The date WorkBench shows this release as published, read from the benchmark's page",
"examples": ["2025-08-28"]
},
"description": {
"type": ["string", "null"],
"description": "The benchmark's overview, as the Markdown its page gives"
},
"downloaded_at": {
"type": "string",
"format": "date-time",
"description": "ISO 8601 timestamp when benchmark was downloaded"
},
"scraper_version": {
"type": "string",
"description": "Scraper strategy version used",
"examples": ["v1_2025_10", "v2_2026_01"]
},
"text_format": {
"type": "string",
"enum": ["html", "markdown"],
"description": "The form of the recommendation text fields as written; a copy saved before this field existed is 'html' when its scraper_version is v1_2025_10"
},
"total_recommendations": {
"type": "integer",
"minimum": 0,
"description": "Total number of recommendations in benchmark"
},
"recommendations": {
"type": "array",
"description": "Array of benchmark recommendations",
"items": {
"$ref": "#/$defs/recommendation"
}
}
},

"$defs": {
"recommendation": {
"type": "object",
"required": ["ref", "title", "url"],
"properties": {
"ref": {
"type": "string",
"description": "Recommendation reference number",
"pattern": "^[0-9]+(\\.[0-9]+)*$",
"examples": ["3.1.1", "5.2.3"]
},
"title": {
"type": "string",
"description": "Recommendation title",
"minLength": 1
},
"url": {
"type": "string",
"format": "uri",
"description": "Direct URL to recommendation page"
},
"assessment_status": {
"type": "string",
"description": "Assessment type: 'Automated' or 'Manual'"
},
"description": {
"type": ["string", "null"],
"description": "Detailed description of the recommendation (Markdown)"
},
"rationale": {
"type": ["string", "null"],
"description": "Rationale/justification for the recommendation (Markdown)"
},
"impact": {
"type": ["string", "null"],
"description": "Impact statement (Markdown)"
},
"audit": {
"type": ["string", "null"],
"description": "Audit procedure to verify compliance (Markdown)"
},
"remediation": {
"type": ["string", "null"],
"description": "Remediation steps to achieve compliance (Markdown)"
},
"additional_info": {
"type": ["string", "null"],
"description": "Additional information and notes (Markdown)"
},
"default_value": {
"type": ["string", "null"],
"description": "Default configuration value (Markdown)"
},
"artifact_equation": {
"type": ["string", "null"],
"description": "Artifact equation logic (Markdown)"
},
"mitre_mapping": {
"type": ["object", "null"],
"description": "MITRE ATT&CK mapping: techniques, tactics, mitigations (lists of IDs)"
},
"references": {
"type": ["string", "null"],
"description": "External references and citations (Markdown)"
}
},
"additionalProperties": false
}
}
}
```

## Using JSON Schema

### Validation

```python
import json
import jsonschema

# Load schema
with open('cis_bench/models/schema.json') as f:
schema = json.load(f)

# Validate scraped data
try:
jsonschema.validate(instance=benchmark_data, schema=schema)
print(" Data is valid")
except jsonschema.ValidationError as e:
print(f" Validation failed: {e.message}")
print(f" Path: {' '.join(str(p) for p in e.path)}")
```

### Data Generation from Schema

We can also use tools like `datamodel-code-generator` to create Python dataclasses from our schema:

```bash
pip install datamodel-code-generator

datamodel-codegen \
--input cis_bench/models/schema.json \
--output cis_bench/models/benchmark.py \
--input-file-type jsonschema
```

This generates type-safe Python classes that match our schema exactly!

## Exporter Mapping

Each exporter knows how to map from our canonical format to its target format:

### JSON Exporter
```python
# Simple pass-through (already in our format)
def export(self, data, output_path):
with open(output_path, 'w') as f:
json.dump(data, f, indent=2)
```

### YAML Exporter
```python
# Direct mapping (structure is the same)
def export(self, data, output_path):
with open(output_path, 'w') as f:
yaml.dump(data, f)
```

### CSV Exporter
```python
# Flatten recommendations array
def export(self, data, output_path):
rows = []
for rec in data['recommendations']:
row = {
'benchmark_title': data['title'],
'benchmark_id': data['benchmark_id'],
'ref': rec['ref'],
'title': rec['title'],
# ... flatten all fields
}
rows.append(row)

# Write CSV
with open(output_path, 'w') as f:
writer = csv.DictWriter(f, fieldnames=row.keys())
writer.writeheader()
writer.writerows(rows)
```

### XCCDF Exporter
```python
# Map to xsdata XCCDF models
def export(self, data, output_path):
from cis_bench.models.xccdf import Benchmark, Rule, Status

# Create XCCDF Benchmark
xccdf_benchmark = Benchmark(
id=f"cis_benchmark_{data['benchmark_id']}",
status=[Status(value="draft")],
title=data['title'],
version=data['version']
)

# Map each recommendation XCCDF Rule
for rec in data['recommendations']:
rule = Rule(
id=f"rule_{rec['ref'].replace('.', '_')}",
title=rec['title'],
description=rec['description'], # Markdown, written as stored
# ... map other fields per XCCDF spec
)
xccdf_benchmark.rule.append(rule)

# Serialize to XML
xml_output = xccdf_benchmark.to_xml(pretty_print=True)
with open(output_path, 'w') as f:
f.write(xml_output)
```

## Field Definitions

### Benchmark Level

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | | Full benchmark title |
| `benchmark_id` | string | | CIS WorkBench ID |
| `url` | string (URI) | | Source URL |
| `version` | string | | Benchmark version |
| `published_date` | string (ISO 8601 date) or null | | The date WorkBench shows the release as published, read from the benchmark's page |
| `description` | string or null | | The benchmark's overview, as the Markdown its page gives |
| `profile_definitions` | array | | The benchmark's profiles as its page defines them: `title`, `description` (Markdown; the page gives it as HTML and it is converted as the page is read), `parent` (the title of the profile it extends, or null); each title once; empty for copies saved before they were read |
| `downloaded_at` | string (ISO 8601) | | When it was downloaded, in UTC with its offset (`Z`); files from earlier versions carry no offset |
| `scraper_version` | string | | Strategy version used |
| `text_format` | `"html"` or `"markdown"` | | The form of the recommendation text fields as written. Every loaded copy holds `markdown`; a copy saved without this field is `html` when its `scraper_version` is `v1_2025_10` (the strategy that saved rendered HTML) and `markdown` otherwise |
| `total_recommendations` | integer | | Count of recommendations |
| `recommendations` | array | | Array of recommendation objects |

### Recommendation Level

| Field | Type | Required | Description | Markdown text |
|-------|------|----------|-------------|---------------|
| `ref` | string | | Reference number (e.g., "3.1.1") | No |
| `title` | string | | Recommendation title | No |
| `url` | string (URI) | | Direct link to recommendation | No |
| `assessment_status` | string | | "Automated" or "Manual" | No |
| `profiles` | array of string | | Profiles the rule belongs to | No |
| `cis_controls` | array of object | | CIS Controls v7/v8 mappings with Implementation Groups | No |
| `mitre_mapping` | object/null | | MITRE ATT&CK techniques, tactics, mitigations (lists of IDs) | No |
| `nist_controls` | array of string | | NIST SP 800-53 control IDs | No |
| `parent` | object/null | | Parent recommendation (url, title) | No |
| `artifacts` | array of object | | Test artifacts: `id`, `view_level`, `title` (Markdown: the payload gives some titles as HTML, converted as the artifact is built, from the payload or from a stored copy), `status`, `artifact_type` | No |
| `description` | string/null | | Detailed description | Yes |
| `rationale` | string/null | | Justification | Yes |
| `impact` | string/null | | Impact statement | Yes |
| `audit` | string/null | | Audit procedure | Yes |
| `remediation` | string/null | | Remediation steps | Yes |
| `additional_info` | string/null | | Additional information and notes | Yes |
| `default_value` | string/null | | Default config value | Yes |
| `artifact_equation` | string/null | | Artifact equation logic | Yes |
| `references` | string/null | | External references | Yes |

**Markdown text**: these fields hold the Markdown WorkBench gives, with `\n` line breaks,
whichever scraper saved the copy. A copy saved by the v1 scraper (`scraper_version`
`v1_2025_10`) holds the page's rendered HTML instead; `Benchmark` converts it to Markdown as
the copy loads (`cis_bench.utils.markdown_text`, on markdownify), keeping the words,
paragraphs, code blocks, lists, tables, links and placeholders such as `<user>`. The stored
copy is left as it was. Which form a copy holds is read from `text_format` (or, for a copy
saved without that field, from `scraper_version`), never from the text itself: a placeholder
looks like a tag. In exports the text is:

- Preserved in JSON/YAML export
- Written as the cell text in CSV export
- Written as it is in Markdown export, with two document-level adjustments: a placeholder in
  prose (outside code) is written `&lt;user>` so a renderer with raw HTML on (GitHub, MkDocs)
  shows it as text instead of reading it as a tag, and a fence a field leaves open is closed
  at the field's end so it cannot swallow the fields after it; both decided by the CommonMark
  parser (markdown-it-py), never by matching the text

- Written as the stored Markdown in the CIS and DISA XCCDF exports (see the style configs)

## Validation Strategy

### When to Validate

1. **After scraping** - Before saving JSON
2. **Before exporting** - Ensure input is valid
3. **In tests** - Validate all fixtures

### Validation Levels

**Strict** (for our saved JSON):

- All required fields present
- Types match schema
- Additional properties not allowed

**Lenient** (for backward compatibility):

- Required fields present
- Types match when present
- Additional properties allowed (ignore)

## Schema Evolution

### Version 1.0.0 (Current)

- Initial schema
- Based on current CIS WorkBench fields
- Includes all 10 recommendation fields

### Version 1.1.0 (Future)

- Add new fields as CIS WorkBench evolves
- Maintain backward compatibility
- Use `oneOf` for version-specific fields

### Version 2.0.0 (Future)

- Breaking changes if needed
- Migration guide provided
- Tool supports both v1 and v2

## Tools and Libraries

**JSON Schema Validation**:
```bash
pip install jsonschema
```

**Code Generation from Schema**:
```bash
pip install datamodel-code-generator
```

**Schema Documentation**:
```bash
pip install json-schema-for-humans
json-schema-for-humans cis_bench/models/schema.json docs/schema.html
```

## Example: Complete Benchmark

```json
{
"title": "CIS Amazon Elastic Kubernetes Service (EKS) Benchmark",
"benchmark_id": "22605",
"url": "https://workbench.cisecurity.org/benchmarks/22605",
"version": "v1.8.0",
"published_date": "2025-08-28",
"description": "This document provides prescriptive guidance for establishing a secure configuration posture for Amazon EKS.",
"downloaded_at": "2025-10-17T21:48:00Z",
"scraper_version": "v1_2025_10",
"total_recommendations": 50,
"recommendations": [
{
"ref": "3.1.1",
"title": "Ensure that the kubeconfig file permissions are set to 644 or more restrictive",
"url": "https://workbench.cisecurity.org/sections/3511915/recommendations/5772605",
"assessment": "<p>Automated assessment available</p>",
"description": "<p>If kubelet is running, and if it is configured by a kubeconfig file...</p>",
"rationale": "<p>Improper access permissions could allow...</p>",
"impact": "<p>None expected</p>",
"audit": "<p>Run the following command: <code>stat -c %a /var/lib/kubelet/kubeconfig</code></p>",
"remediation": "<p>Run: <code>chmod 644 /var/lib/kubelet/kubeconfig</code></p>",
"default_value": null,
"artifact_eq": null,
"mitre_mapping": "<p>T1574.006 - Hijack Execution Flow: Dynamic Linker Hijacking</p>",
"references": "<ul><li>Kubernetes documentation</li></ul>"
}
// ... 49 more recommendations
]
}
```

## Integration with Exporters

### BaseExporter Contract

```python
class BaseExporter(ABC):
@abstractmethod
def export(self, data: dict, output_path: str) -> str:
"""Export benchmark data.

Args:
data: Dictionary matching cis_bench/models/schema.json
output_path: Where to write output

Returns:
Path to created file

Raises:
jsonschema.ValidationError: If data doesn't match schema
IOError: If file cannot be written
"""
# All exporters should validate input first
self._validate_input(data)

# Then perform export
# ...
```

### Mapping Examples

**JSON Schema Field XCCDF Field**

| Our Schema | XCCDF Element | Notes |
|------------|---------------|-------|
| `ref` | `Rule/@id` | Convert "3.1.1" "rule_3_1_1" |
| `title` | `Rule/title` | Direct mapping |
| `description` | `Rule/description` | The stored Markdown, written as it is; in the CIS style the default value and the additional information follow it as labelled sections |
| `rationale` | `Rule/rationale` | The stored Markdown, written as it is |
| `audit` | `Rule/check/check-content` | The stored Markdown, inside the check element |
| `remediation` | `Rule/fixtext` | The stored Markdown, written as it is |
| `references` | `Rule/ident[@system="URL"]` | CIS style: one ident per non-empty line, as stored |
| `mitre_mapping` | `Rule/reference` | Parse and map to reference elements |

**JSON Schema Field CSV Column**

All fields flattened to single row:
```csv
benchmark_title,benchmark_id,ref,title,description,audit,...
"CIS Amazon EKS","22605","3.1.1","Ensure...","If kubelet...","Run...",...
```

## Validation Implementation

### In WorkbenchScraper

```python
import jsonschema

class WorkbenchScraper:
def __init__(self, session, schema_path='cis_bench/models/schema.json'):
self.session = session

# Load schema
with open(schema_path) as f:
self.schema = json.load(f)

def download_benchmark(self, benchmark_url):
# ... scraping logic ...

benchmark_data = {
'title': title,
'benchmark_id': benchmark_id,
'recommendations': recommendations,
# ...
}

# VALIDATE before returning
try:
jsonschema.validate(instance=benchmark_data, schema=self.schema)
except jsonschema.ValidationError as e:
raise ValueError(f"Scraped data validation failed: {e.message}")

return benchmark_data
```

### In Exporters

```python
class BaseExporter(ABC):
def _validate_input(self, data: dict):
"""Validate input data against schema."""
with open('cis_bench/models/schema.json') as f:
schema = json.load(f)

jsonschema.validate(instance=data, schema=schema)
```

## Schema Files

We'll maintain multiple schema versions:

```
cis_bench/models/
├── schema.json # Current schema (symlink to v1.0.0)
├── schemas/
│ ├── v1.0.0.json # Version 1.0.0
│ ├── v1.1.0.json # Version 1.1.0 (future)
│ └── v2.0.0.json # Version 2.0.0 (future)
└── schema_validator.py # Validation utilities
```

## Benefits in Practice

### Before (No Schema)

```mermaid
flowchart LR
    A[Scraper extracts data] --> B[Export to XCCDF]
    B --> C[❌ Missing field!<br/>XCCDF invalid!<br/>Debug for hours...]

    style C fill:#FFE0E0,stroke:#CC0000,stroke-width:2px
```

### After (With Schema)

```mermaid
flowchart LR
    A[Scraper extracts data] --> B{Validate against schema}
    B -->|Invalid| C[❌ Missing 'title' field!<br/>Validation fails immediately<br/>Fix scraper in minutes]
    C --> D[Re-scrape]
    D --> E{Validates}
    E -->|Valid| F[Export to XCCDF]
    F --> G[✅ Valid XCCDF]

    style C fill:#FFE0E0,stroke:#CC0000,stroke-width:2px
    style G fill:#E0FFE0,stroke:#00CC00,stroke-width:2px
    style E fill:#E8F4F8,stroke:#0066CC,stroke-width:2px
    style B fill:#E8F4F8,stroke:#0066CC,stroke-width:2px
```

---
