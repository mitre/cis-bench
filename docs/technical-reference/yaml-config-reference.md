# MappingEngine YAML Configuration Reference

!!! info "Documentation Path"
**You are here:** Technical Reference > YAML Config Syntax

- **For practical guide:** See [MappingEngine User Guide](../developer-guide/mapping-engine-guide.md)
- **For how-to:** See [How To Add XCCDF Style](../developer-guide/how-to-add-xccdf-style.md)

## Overview

This document provides a complete reference for writing MappingEngine YAML configuration files. These files define how CIS Benchmark data is transformed into XCCDF format.

## Configuration Structure

```yaml
# Top-level structure
metadata: # Style metadata
style_name: "..."
description: "..."
xccdf_version: "..."

benchmark: # Benchmark-level mappings
id_template: "..."
title: {...}
description: {...}
version: {...}

rule_defaults: # Default rule attributes
severity: "..."
weight: "..."
selected: "..."

rule_id: # Rule ID generation
template: "..."
ref_normalized: "..."

field_mappings: # Field mapping definitions
field_name:
target_element: "..."
source_field: "..."
transform: "..."
# ... more options

transformations: # Transform definitions
transform_name:
description: "..."
function: "..."

cci_deduplication: # CCI/NIST deduplication config
enabled: true
algorithm: {...}

validation: # Validation rules
require_cci_for_cis_controls: false
```

## Metadata Section

Describes the export style:

```yaml
metadata:
style_name: "disa" # Unique identifier
description: "DISA/DoD STIG-compatible XCCDF export"
xccdf_version: "1.2" # Target XCCDF version
target_tools: # Compatible tools (optional)

- "DISA SCAP Compliance Checker (SCC)"
- "OpenSCAP (DoD configurations)"
conventions: "Follows DISA STIG XML structure" # Notes (optional)
```

## Benchmark Section

Benchmark-level field mappings:

```yaml
benchmark:
# ID template with variables
id_template: "xccdf_cis_{platform}_benchmark"

# Simple field mapping
title:
source: "title"
transform: "none"

description:
source: "title" # Can reuse other fields
transform: "none"

version:
source: "version"
transform: "none"
```

## Rule Defaults

Default attributes applied to all rules:

```yaml
rule_defaults:
severity: "medium" # CAT II equivalent
weight: "10.0" # DISA standard
selected: "true" # Rule enabled by default
role: "full" # Full rule (not snippet)
```

## Rule ID Generation

Template for generating rule IDs:

```yaml
rule_id:
template: "xccdf_cis_{platform}_rule_{ref_normalized}"
ref_normalized: "replace('.', '_')" # 3.1.1 3_1_1
```

## Field Mappings

Core of the configuration. Each field mapping defines how to map one field.

### Simple Field Mapping

Direct field copy with optional transform:

```yaml
field_mappings:
title:
target_element: "title" # XCCDF element name
source_field: "title" # Source field on Recommendation
transform: "strip_html" # Transform to apply
description: "Rule title" # Optional documentation
```

### Field with Attributes

Add attributes to XCCDF element:

```yaml
fixtext:
target_element: "fixtext"
source_field: "remediation"
transform: "strip_html_keep_code"
attributes:
fixref: "F-{ref_normalized}" # Variable substitution in attributes
```

### Static Content Field

Element with static content (no source):

```yaml
fix:
target_element: "fix"
content: "" # Empty element
attributes:
id: "F-{ref_normalized}"
```

### Composite Field

Multiple sources joined into one target:

```yaml
description:
target_element: "description"
structure: "composite"
sources:

- field: "description"
transform: "strip_html"

- field: "rationale"
transform: "strip_html"
separator: "\n\n"
```

### Embedded XML Structure

Build nested XML tags within element:

```yaml
description:
target_element: "description"
structure: "embedded_xml_tags"
components:
# Component with sources

- tag: "VulnDiscussion"
sources:

- field: "description"
transform: "strip_html"
separator: "\n\n"

- field: "rationale"
transform: "strip_html"
combine: "join"

# Component with static content

- tag: "FalsePositives"
content: ""

# Optional component (only if source present)

- tag: "Mitigations"
sources:

- field: "additional_info"
transform: "strip_html"
optional: true

# More components...

- tag: "IAControls"
content: ""
```

### Nested Structure

Nested XCCDF elements:

```yaml
check:
target_element: "check"
structure: "nested"
attributes:
system: "C-{ref_normalized}"
children:

- element: "check-content"
source_field: "audit"
transform: "strip_html_keep_code"
```

### Multiple Elements

Create multiple elements from array:

```yaml
ident:
target_element: "ident"
multiple: true # Create multiple <ident> elements
source_logic: "cci_lookup_with_deduplication"
cci_lookup:
enabled: true
mapping_file: "data/cis-cci-mapping.json"
source_field: "cis_controls"
extract: "all" # primary + supporting
deduplicate_nist: true
attributes:
system: "http://cyber.mil/cci"
```

### Custom Namespace Elements

Elements in custom namespace:

```yaml
metadata:
target_element: "metadata"
structure: "metadata_from_config"
namespace: "http://cisecurity.org/xccdf/metadata/1.0"
enabled: true
components:

- element: "cis-control"
source_field: "cis_controls"
multiple: true # Create multiple elements
attributes:
version: "{control.version}"
id: "{control.control}"
ig1: "{control.ig1}"
content: "{control.title}"

- element: "profile"
source_field: "profiles"
multiple: true
content: "{profile}"
```

## Component Mapping Options

Components are used in embedded XML and custom namespace structures:

```yaml
components:
# Component with multiple sources

- tag: "VulnDiscussion" # XML tag name
sources: # Multiple sources

- field: "description" # Source field
transform: "strip_html" # Transform to apply
separator: "\n\n" # Separator between sources

- field: "rationale"
transform: "strip_html"
combine: "join" # How to combine sources

# Component with static content

- tag: "FalsePositives"
content: "" # Static content

# Optional component (skip if source empty)

- tag: "Mitigations"
sources:

- field: "additional_info"
transform: "strip_html"
optional: true # Skip if source is None/empty

# Component with attributes

- element: "reference" # Element name (custom namespace)
source_field: "nist_controls"
multiple: true # Loop over array
attributes:
href: "https://csrc.nist.gov/..."
content: "{nist_control_id}" # Variable substitution
```

## Transformations Section

Define available transformations:

```yaml
transformations:
# Pass-through (no transformation)
none:
description: "Pass through unchanged"

# Strip all HTML
strip_html:
description: "Remove all HTML tags, return plain text"
function: "HTMLCleaner.strip_html"

# Strip HTML but keep code/lists
strip_html_keep_code:
description: "Strip HTML but preserve code blocks and lists"
function: "HTMLCleaner.strip_html_keep_code"
preserve_elements:

- "code"
- "pre"
- "ul"
- "ol"
- "li"

# Convert to Markdown
html_to_markdown:
description: "Convert HTML to Markdown"
function: "HTMLCleaner.html_to_markdown"
```

## Variables Reference

Available variables for substitution in templates:

### Benchmark-Level Variables

```yaml
# Available in benchmark mappings
{platform} # Extracted from title (e.g., "eks")
{benchmark_id} # CIS WorkBench ID (e.g., "22605")
```

### Rule-Level Variables

```yaml
# Available in rule mappings
{ref} # Original ref (e.g., "3.1.1")
{ref_normalized} # Normalized ref (e.g., "3_1_1")
{platform} # Same as benchmark level
```

### Nested Variables (in loops)

```yaml
# When iterating over CIS controls
{control.version} # CIS Control version (7 or 8)
{control.control} # Control ID (e.g., "4.8")
{control.title} # Control title
{control.ig1} # IG1 boolean
{control.ig2} # IG2 boolean
{control.ig3} # IG3 boolean

# When iterating over NIST controls
{nist_control_id} # NIST control (e.g., "CM-7")

# When iterating over MITRE mappings
{technique} # MITRE technique (e.g., "T1068")
{tactic} # MITRE tactic (e.g., "TA0001")
{mitigation} # MITRE mitigation (e.g., "M1022")

# When iterating over profiles
{profile} # Profile name (e.g., "Level 1 - Server")
```

## Source Field Reference

Available source fields from Recommendation model:

### Core Fields

```yaml
ref # Recommendation reference (e.g., "3.1.1")
title # Recommendation title
url # Direct URL to recommendation
assessment_status # "Automated" or "Manual"
```

### Classification and Mappings

```yaml
profiles # List[str] - Applicable profiles
cis_controls # List[CISControl] - CIS Controls mappings
mitre_mapping # MITREMapping - MITRE ATT&CK mappings
nist_controls # List[str] - NIST control IDs
```

### Content Fields (HTML)

```yaml
description # Detailed description (HTML)
rationale # Rationale/justification (HTML)
impact # Impact statement (HTML)
audit # Audit procedure (HTML)
remediation # Remediation steps (HTML)
additional_info # Additional information (HTML)
default_value # Default config value (HTML)
artifact_equation # Artifact equation (HTML)
references # External references (HTML)
```

### Nested Field Access

Use dot notation for nested fields:

```yaml
# Access CIS Control attributes
source_field: "cis_controls[0].control" # First control ID
source_field: "cis_controls[0].version" # First control version

# Access MITRE mapping
source_field: "mitre_mapping.techniques" # List of techniques
source_field: "mitre_mapping.tactics" # List of tactics
source_field: "mitre_mapping.mitigations" # List of mitigations
```

## CCI Deduplication Configuration

Complex logic for CCI/NIST deduplication:

```yaml
cci_deduplication:
enabled: true
algorithm:
description: "Use CCIs where available, NIST references for extras"
steps:

- "Extract all CIS Controls from recommendation"
- "Look up CCIs for each CIS Control (primary + supporting)"
- "Determine which NIST controls are covered by those CCIs"
- "Add CCIs as <ident> elements"
- "Add uncovered NIST controls as <reference> elements"

matching_rules:
description: "How to determine if CCI covers a NIST citation"
hierarchical: true # CM-7.1 covers CM-7
examples:

- cci_maps_to: "CM-7.1"
cis_cites: "CM-7"
result: "covered" # CCI is more specific

- cci_maps_to: "CM-7"
cis_cites: "CM-7.1"
result: "not_covered" # CCI too broad

- cci_maps_to: "CM-7(5)"
cis_cites: "CM-7"
result: "covered" # Enhancement covers base
```

## Validation Section

Validation rules for export:

```yaml
validation:
require_cci_for_cis_controls: false # Warn if CCI missing
require_nist_controls: false # Warn if NIST missing
max_cci_per_rule: 50 # Sanity check limit
```

## Complete Example

Minimal working configuration:

```yaml
# minimal_style.yaml
metadata:
style_name: "minimal"
description: "Minimal XCCDF export"
xccdf_version: "1.2"

benchmark:
id_template: "xccdf_cis_{platform}_benchmark"
title:
source: "title"
transform: "none"
version:
source: "version"
transform: "none"

rule_defaults:
severity: "medium"
weight: "10.0"
selected: "true"

rule_id:
template: "xccdf_cis_{platform}_rule_{ref_normalized}"
ref_normalized: "replace('.', '_')"

field_mappings:
title:
target_element: "title"
source_field: "title"
transform: "strip_html"

description:
target_element: "description"
source_field: "description"
transform: "strip_html"

rationale:
target_element: "rationale"
source_field: "rationale"
transform: "strip_html"

transformations:
none:
description: "Pass through unchanged"

strip_html:
description: "Remove all HTML tags"
function: "HTMLCleaner.strip_html"
```

## Best Practices

### 1. Use Descriptive Names

```yaml
# Good
field_mappings:
vuln_discussion:
target_element: "VulnDiscussion"
description: "Combined description and rationale for DISA compliance"

# Bad
field_mappings:
field1:
target_element: "VulnDiscussion"
```

### 2. Document Complex Mappings

```yaml
# Add comments for complex logic
field_mappings:
description:
target_element: "description"
structure: "embedded_xml_tags"
# This builds DISA STIG-compatible description with nested XML tags.
# VulnDiscussion combines description + rationale per DISA requirements.
components:

- tag: "VulnDiscussion"
# ... more config
```

### 3. Group Related Fields

```yaml
field_mappings:
# === CORE IDENTIFICATION ===
version:
# ...
title:
# ...

# === DESCRIPTION (Complex - Embedded XML Tags) ===
description:
# ...

# === CCI IDENTIFIERS ===
ident:
# ...
```

### 4. Use Consistent Naming

```yaml
# Be consistent with ID templates
rule_id:
template: "xccdf_cis_{platform}_rule_{ref_normalized}"

# Use same pattern for other IDs
check:
attributes:
system: "C-{ref_normalized}"

fix:
attributes:
id: "F-{ref_normalized}"

fixtext:
attributes:
fixref: "F-{ref_normalized}"
```

### 5. Handle Optional Fields Gracefully

```yaml
# Mark optional fields explicitly
components:

- tag: "Mitigations"
sources:

- field: "additional_info"
transform: "strip_html"
optional: true # Skip if field is empty

- tag: "PotentialImpacts"
sources:

- field: "impact"
transform: "strip_html"
optional: true # Skip if field is empty
```

### 6. Validate Your Config

Before using in production:

1. **Syntax check**: Ensure valid YAML
```bash
python -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

2. **Schema validation**: Use ConfigLoader to validate
```python
from cis_bench.exporters.mapping import ConfigLoader
config = ConfigLoader.load('your_config.yaml')
```

3. **Test with sample data**: Run on small benchmark first

4. **Validate XCCDF output**: Check against NIST schema
```bash
xmllint --schema xccdf_1.2.xsd output.xml --noout
```

## Common Patterns

### Pattern 1: Simple Field with Transform

```yaml
title:
target_element: "title"
source_field: "title"
transform: "strip_html"
```

### Pattern 2: Field with Static Attributes

```yaml
fixtext:
target_element: "fixtext"
source_field: "remediation"
transform: "strip_html_keep_code"
attributes:
fixref: "F-{ref_normalized}"
```

### Pattern 3: Empty Element with ID

```yaml
fix:
target_element: "fix"
content: ""
attributes:
id: "F-{ref_normalized}"
```

### Pattern 4: Composite Field (Join Multiple Sources)

```yaml
combined_description:
target_element: "description"
structure: "composite"
sources:

- field: "description"
transform: "strip_html"

- field: "rationale"
transform: "strip_html"
separator: "\n\n"
```

### Pattern 5: Embedded XML (DISA STIG Description)

```yaml
description:
target_element: "description"
structure: "embedded_xml_tags"
components:

- tag: "VulnDiscussion"
sources:

- field: "description"
transform: "strip_html"

- field: "rationale"
transform: "strip_html"
separator: "\n\n"

- tag: "FalsePositives"
content: ""

- tag: "Mitigations"
sources:

- field: "additional_info"
transform: "strip_html"
optional: true
```

### Pattern 6: Multiple Elements from Array

```yaml
reference:
target_element: "reference"
multiple: true
source_field: "nist_controls"
attributes:
href: "https://csrc.nist.gov/Projects/risk-management/sp800-53-controls"
content: "{nist_control_id}"
```

### Pattern 7: Custom Namespace Metadata

```yaml
metadata:
target_element: "metadata"
structure: "metadata_from_config"
namespace: "http://cisecurity.org/xccdf/metadata/1.0"
components:

- element: "cis-control"
source_field: "cis_controls"
multiple: true
attributes:
version: "{control.version}"
id: "{control.control}"
content: "{control.title}"
```

## Troubleshooting

### Issue: Transform Not Found

```yaml
Error: Transform 'unknown_transform' not found
```

**Solution**: Check `transformations` section. Available transforms:

- none
- strip_html
- strip_html_keep_code
- html_to_markdown

### Issue: Source Field Not Found

```yaml
Error: Source field 'nonexistent_field' not found on Recommendation
```

**Solution**: Check field name spelling. Available fields:

- ref, title, url, assessment_status
- description, rationale, impact, audit, remediation
- cis_controls, mitre_mapping, nist_controls
- See "Source Field Reference" section

### Issue: Variable Not Resolved

```yaml
Error: Variable 'unknown_var' not found in template
```

**Solution**: Check variable name. Available variables:

- {ref}, {ref_normalized}, {platform}
- {control.version}, {control.control}
- {nist_control_id}, {technique}, {tactic}
- See "Variables Reference" section

### Issue: Invalid YAML Syntax

```yaml
Error: YAML parsing failed
```

**Solution**: Validate YAML syntax:

- Consistent indentation (spaces, not tabs)
- Proper quoting of strings with special characters
- Valid list and dict syntax

## Related Documents

- [Mapping Engine Design](mapping-engine-design.md) - Complete design
- [DISA Style Example](https://github.com/aaronlippold/cis-benchmark-cli/blob/main/src/cis_bench/exporters/configs/disa_style.yaml) - Complete YAML example

---

**Version**: 1.0.0
**Date**: 2025-10-18
