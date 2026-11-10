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
id_template: "xccdf_org.cisecurity.benchmarks_benchmark_{version}_{title_slug}"

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
template: "xccdf_org.cisecurity.benchmarks_rule_{ref_normalized}"
ref_normalized: "replace('.', '_')" # 3.1.1 3_1_1
```

The template sees two values made from the recommendation's ref: `{ref_normalized}`
(`3_1_1`) and `{stig_number}` (`030101`). The same id names the Rule and every Profile
`select` of it. A template that names any other variable, or gives no id (an empty
template, or a filter whose result is not text), stops the export with an error.

## Field Mappings

Core of the configuration. Each field mapping defines how to map one field.

### Simple Field Mapping

Direct field copy with optional transform:

```yaml
field_mappings:
title:
target_element: "title" # XCCDF element name
source_field: "title" # Source field on Recommendation
transform: "none" # Transform to apply
description: "Rule title" # Optional documentation
```

### Field with Attributes

Add attributes to XCCDF element:

```yaml
fixtext:
target_element: "fixtext"
source_field: "remediation"
transform: "none"
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

Multiple sources joined into one target: each source's text after its transform (`none` by
default), joined by `separator` (a blank line by default); a source with a `label` writes the
label, the separator and the text; a source without text adds nothing.

```yaml
description:
target_element: "description"
structure: "composite"
separator: "\n\n"
sources:

- field: "description"

- field: "default_value"
label: "Default Value:"
```

### Embedded XML Structure

Tags inside an element's text (a STIG rule description). Every component is one tag, written
in the order given and always present (empty when the rule has no text for it); its text is
`content`, or its `sources` joined (`field`, `transform` default `none`, and the `separator`
that follows a source's text when another's comes after it). Each tag is built and written by
the XML library (lxml), which escapes its text, so a reader that unescapes the element once and
parses the tags gets the stored text, placeholders included; a tag name that is no XML name is
refused when the style loads:

```yaml
description:
target_element: "description"
structure: "embedded_xml_tags"
components:
# Component with sources

- tag: "VulnDiscussion"
sources:

- field: "description"
transform: "none"
separator: "\n\n" # follows the description when the rationale has text

- field: "rationale"
transform: "none"

# Component with static content

- tag: "FalsePositives"
content: ""

# Component from one source (written empty when the field has no text)

- tag: "Mitigations"
sources:

- field: "additional_info"
transform: "none"

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
transform: "none"
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
cis_controls_version: 8 # the CIS Controls version the mapping file is keyed by
extract: "all" # every CCI of the safeguard, primary first ("primary": only the first)
deduplicate_nist: true
attributes:
system: "http://cyber.mil/cci"
```

`cis_controls_version` names the CIS Controls version the mapping file is keyed by (the
shipped `cis-cci-mapping.json` is keyed by v8). Only a rule's controls of that version are
looked up: v7 reuses the same numbers for unrelated safeguards. A rule with no control of
that version gets `fallback_cci`. Without the key, every control is looked up.

The NIST controls no CCI on the rule covers are written as references by a field with
`source_logic: "nist_after_cci_deduplication"` (the DISA style's `reference`, listed in its
`rule_elements`); each reference carries the `dc_elements` the field names (`dc:title`
"NIST SP 800-53" and `dc:identifier`). A `dublin_core` field with any other `source_logic`
stops the export with an error. The CCI lookup runs once per rule for both.

Each `dc_elements` entry becomes a child element of the reference: the engine builds an
xsdata `AnyElement` in the namespace the style declares for the element's prefix
(`benchmark.namespaces.dc`), with the filled `content` as its text, and puts it in the
reference's wildcard content, so xsdata writes it like any other element and a value may
contain any character. A prefix with no declared namespace stops the export. The same
applies to the Benchmark's own `reference` (`benchmark.reference.dc_elements`).

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
transform: "none" # Transform to apply (default none)
separator: "\n\n" # Follows this source's text when another source's text comes after it

- field: "rationale"
transform: "none"

# Component with static content

- tag: "FalsePositives"
content: "" # Static content

# Component from one source (written empty when the field has no text)

- tag: "Mitigations"
sources:

- field: "additional_info"
transform: "none"

# Component with attributes

- element: "reference" # Element name (custom namespace)
source_field: "nist_controls"
multiple: true # Loop over array
attributes:
href: "https://csrc.nist.gov/..."
content: "{nist_control_id}" # Variable substitution
```

## Transformations Section

A benchmark's text fields hold Markdown (see the [data model](data-model.md)) and every export
writes the text as it is, so the styles name `none` for every text field: the CIS style for
each rule text field (title, description, rationale, warning, fixtext, check-content) and the
profile descriptions, the DISA style for its text fields and the description's embedded tags.
There is no HTML conversion: a text parsed as HTML would read a placeholder such as `<user>` as
a tag. The transforms are registered in `mapping_engine.py` (`TransformRegistry.register`);
this section only documents them, and a style that names a transform that is not registered is
refused when it loads.

```yaml
transformations:
# Pass-through (no transformation)
none:
description: "Pass through unchanged"
```

## Variables Reference

Every template is filled by one strict substituter. A variable the template's context
does not have, an attribute or key a value does not have, or a stray or unclosed brace
stops the export with an error naming the template and the variable, so a typo in a style
cannot write an empty part; an empty name in a path (`{item..control}`) is refused too. A
known variable whose value is empty substitutes as empty
text; a `None` value, met along a dotted path or at its end (a recommendation without a
MITRE mapping, say), reads as empty text too. `{{` and `}}` write a literal brace. Each template sees the
variables of its own context:

### Benchmark-Level Variables

```yaml
# Available in benchmark.id_template
{benchmark_id} # CIS WorkBench ID (e.g., "22605")
{version} # Benchmark version, NCName-safe (e.g., "v1.0.0")
{title_slug} # Benchmark title, NCName-safe (e.g., "CIS_Ubuntu_Linux_22.04_LTS_Benchmark")
```

### Rule-Level Variables

```yaml
# In rule templates: rule_id and group_id templates, and the attribute templates of a
# rule's field mappings (fixref, system, id)
{ref} # Original ref (e.g., "3.1.1")
{ref_normalized} # Normalized ref (e.g., "3_1_1")
{stig_number} # Zero-padded ref for DISA ids (e.g., "030101")
{rec.title} # Any field of the recommendation, in attribute templates (rec.<field>)
{benchmark.title} # Any field of the benchmark, in attribute templates (benchmark.<field>)
```

### Per-Item Variables (ident_from_list, metadata_from_config)

```yaml
# Each item of the source list, e.g. a CISControl or a MITRE technique string
{item} # The item itself, for a list of strings (e.g., "T1068")
{item.version} # A field of the item (e.g., CIS Controls version 7 or 8)
{item.control} # Control ID (e.g., "4.8"); filters apply: {item.control|dotted_number_path:subcontrol}
{item.title} # Control title
{group_key} # In a metadata group's attributes: the value the items were grouped by

# In a dublin_core field's dc_elements, one reference per NIST control
{nist_control_id} # NIST control (e.g., "CM-7")

# In benchmark.profiles.id_template
{profile.title} # Profile title (e.g., "Level 1 - Server"); e.g. {profile.title|slug:-}

# In benchmark.reference, benchmark.notice and benchmark.plain_text
{benchmark.title} # Any field of the benchmark (benchmark.<field>)
{benchmark.url}
{download_date} # plain_text only: the download date ("07 Nov 2026")
```

### Filters

A variable can be passed through a registered transform: write the transform's name after
`|`, and its arguments, if any, after `:` separated by commas. A `|` with no transform name,
an unknown transform, arguments the transform does not take, or a value the transform
refuses, stops the export with an error naming it.

```yaml
# CIS Controls ident in the CIS-CAT form: "8.5" -> control/8/subcontrol/5, "13" -> control/13
template: "http://cisecurity.org/20-cc/v{item.version}.0/control/{item.control|dotted_number_path:subcontrol}"
```

`dotted_number_path` turns a dotted number into a path, putting each argument before the
level after it (`1.2.3` with `section, item` is `1/section/2/item/3`); a value that is not a
dotted number (ASCII digits between dots), that has more levels than labels, or an empty
label, is refused.

### Profiles

`benchmark.profiles` writes XCCDF `<Profile>` elements at Benchmark level, each with an
explicit `<select>` for every rule it contains.

```yaml
benchmark:
  profiles:
    generate_from_rules: true
    id_template: "{profile.title|slug:-}"   # every Profile id, from its title
    description_transform: "none"                # the stored Markdown, written as it is
    profile_mappings:

      - match: "Level 1 - Server"            # a profile name as recommendations give it
        title: "Level 1 - Server"
        description: "CIS Level 1 recommendations for server environments"

      - match: "Level 2 - Server"
        title: "Level 2 - Server"
        includes: ["Level 1 - Server"]        # also select the rules of these profiles
```

A download reads the benchmark's profile definitions from its WorkBench page: each profile's
title, description and the profile it extends (`parent`). With those, there is one Profile
per definition; it selects the rules that name it or any ancestor, and takes its title and
description from the page (the description through `description_transform`). A definition
that selects no rule is left out, and the export logs a warning naming it. A copy saved
before definitions were read has one Profile per profile name its rules use; a mapping for
that name gives the title, description and the profiles it `includes` (directly or through
another mapping), and a name with no mapping gets a Profile with its own rules. A mapping
that no rule names writes no Profile.

Every Profile id comes from `id_template` (the `slug` filter drops accents, then turns
"Level 1 - Server" into `level-1-server` with `-`, `level_1_server` with `_`); a mapping
does not set its own `id`. A recommendation's `profiles` holds one name per entry;
WorkBench's one-text form ("Level 1 - Server" and "Level 1 - Workstation" on two lines) is
split when the recommendation is loaded. A parent or `includes` entry that names no
profile, profiles that include each other, two mappings for one `match`, two profiles that
get one id, a mapping without `match` or with an `id`, or no `id_template` stops the export
with an error. Every mapping is checked, whether or not the benchmark's rules use it.

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
profiles # List[str] - Applicable profiles, one name per entry
cis_controls # List[CISControl] - CIS Controls mappings
mitre_mapping # MITREMapping - MITRE ATT&CK mappings
nist_controls # List[str] - NIST control IDs
```

### Content Fields (Markdown)

```yaml
description # Detailed description (Markdown)
rationale # Rationale/justification (Markdown)
impact # Impact statement (Markdown)
audit # Audit procedure (Markdown)
remediation # Remediation steps (Markdown)
additional_info # Additional information (Markdown)
default_value # Default config value (Markdown)
artifact_equation # Artifact equation (Markdown)
references # External references (Markdown)
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
- "Look up every CCI of each CIS Controls v8 safeguard (extract: all)"
- "Note the control and enhancement each CCI sits under"
- "Add CCIs as <ident> elements"
- "Add every cited NIST control as a <reference>, except one a CCI restates exactly"

matching_rules:
description: "A CCI restates only the control and enhancement it sits under"
hierarchical: false # CM-7 (1) (b) does not stand for CM-7 or CM-7(2)
examples:

- cci_maps_to: "CM-7 (1) (b)"
cis_cites: "CM-7(1)"
result: "restated" # same control and enhancement; not written again

- cci_maps_to: "CM-7 (1) (b)"
cis_cites: "CM-7"
result: "written" # the base control is a broader requirement

- cci_maps_to: "CM-7 b"
cis_cites: "CM-7(5)"
result: "written" # a different enhancement
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
id_template: "xccdf_org.cisecurity.benchmarks_benchmark_{version}_{title_slug}"
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
template: "xccdf_org.cisecurity.benchmarks_rule_{ref_normalized}"
ref_normalized: "replace('.', '_')"

field_mappings:
title:
target_element: "title"
source_field: "title"
transform: "none"

description:
target_element: "description"
source_field: "description"
transform: "none"

rationale:
target_element: "rationale"
source_field: "rationale"
transform: "none"

transformations:
none:
description: "Pass through unchanged"
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
template: "xccdf_org.cisecurity.benchmarks_rule_{ref_normalized}"

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

### 5. Write Every Embedded Tag

```yaml
# Every component is written, in order, empty when the rule has no text for it
# (official STIGs write all eleven tags of a description)
components:

- tag: "Mitigations"
sources:

- field: "additional_info"

- tag: "PotentialImpacts"
sources:

- field: "impact"
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
cis-bench validate output.xml
```

## Common Patterns

### Pattern 1: Simple Field with Transform

```yaml
title:
target_element: "title"
source_field: "title"
transform: "none"
```

### Pattern 2: Field with Static Attributes

```yaml
fixtext:
target_element: "fixtext"
source_field: "remediation"
transform: "none"
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
transform: "none"

- field: "rationale"
transform: "none"
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
separator: "\n\n" # follows the description when the rationale has text

- field: "rationale"

- tag: "FalsePositives"
content: ""

- tag: "Mitigations" # written empty when the rule has no additional_info
sources:

- field: "additional_info"
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

```text
ValueError: Unknown transformation: unknown_transform
```

**Solution**: Use a transform registered in `mapping_engine.py` (`TransformRegistry.register`):

- none
- strip_version_prefix
- lines (a text field as its non-empty stripped lines; an `ident_from_list` mapping with `transform: "lines"` writes one ident per line)
- dotted_number_path (with arguments; see [Filters](#filters))
- slug (with the separator as argument; see [Profiles](#profiles))

### Issue: Source Field Not Found

Loading a style refuses a `source_field` (in `field_mappings` and their `children`) or a
`source` (in `group_elements` and the benchmark elements) that names no field:

```text
ValueError: field_mappings.title names 'titel', which is not a field of Recommendation
```

A dotted path (`mitre_mapping.techniques`) is read only by the `ident_from_list` and
`metadata_from_config` structures; anywhere else the name must be one field.

**Solution**: Check the name against the available fields:

- ref, title, url, assessment_status
- description, rationale, impact, audit, remediation
- cis_controls, mitre_mapping, nist_controls
- See "Source Field Reference" section

### Issue: Variable Not Resolved

Any template naming a variable its context does not have, or an attribute a value does
not have, stops the export; so does a stray brace:

```text
ValueError: template 'SV-{platform}-{stig_number}' names 'platform'; 'platform' is not a value this template can use (it can use ref, ref_normalized, stig_number)
ValueError: template 'SV-{stig_number_rule': expected '}' before end of string
```

Check the variable against the context of that template (see "Variables Reference"):

- rule id and group id templates: {ref}, {ref_normalized}, {stig_number}
- a rule's attribute templates: those three, {rec.<field>} and {benchmark.<field>}
- ident_from_list and metadata_from_config: {item}, {item.<field>}; group attributes: {group_key}
- dublin_core dc_elements: {nist_control_id}
- benchmark.profiles.id_template: {profile.title}
- benchmark.id_template: {benchmark_id}, {version}, {title_slug}
- benchmark.reference, notice and plain_text: {benchmark.<field>}; plain_text also {download_date}

### Issue: Invalid YAML Syntax

PyYAML's error names the file, line and column:

```text
yaml.scanner.ScannerError: while scanning a quoted scalar
  in "my-style.yaml", line 2, column 13
found unexpected end of stream
```

**Solution**: Check the YAML syntax at that line:

- Consistent indentation (spaces, not tabs)
- Proper quoting of strings with special characters
- Valid list and dict syntax

## Related Documents

- [Mapping Engine Design](mapping-engine-design.md) - Complete design
- [DISA Style Example](https://github.com/mitre/cis-bench/blob/main/src/cis_bench/exporters/configs/styles/disa.yaml) - Complete YAML example

---

**Version**: 1.0.0
**Date**: 2025-10-18
